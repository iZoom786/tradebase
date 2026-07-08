#!/usr/bin/env python3
"""
Incremental 1-minute fetch for EURUSD.

This script runs continuously, fetching the 3 most recent 1-minute candles
every minute and upserting them to the database.

Features:
- Fetches 3 recent rows (previous minute, current minute forming, next minute)
- Upserts to avoid duplicates
- Tracks last fetch time
- Graceful shutdown on Ctrl+C

Usage:
    python scripts/incremental_fetch_1m.py
"""

import psycopg2
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import time
import signal
import sys

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'tradebase',
    'user': 'postgres',
    'password': 'postgres'
}

SYMBOL = 'EURUSD'
INTERVAL = '1m'
FETCH_COUNT = 3  # Fetch 3 most recent candles

# Global flag for graceful shutdown
running = True


def signal_handler(signum, frame):
    """Handle interrupt signals for graceful shutdown."""
    global running
    print("\n\nShutdown signal received. Finishing current cycle...")
    running = False


def get_db_connection():
    """Create database connection."""
    return psycopg2.connect(**DB_CONFIG)


def generate_timekey(timestamp):
    """Generate timekey in YYYYMMDDHHMM format for 1-minute data."""
    return int(timestamp.strftime('%Y%m%d%H%M'))


def fetch_latest_n_candles(symbol, n=3, interval='1m'):
    """
    Fetch the N most recent candles from YFinance.

    Returns DataFrame with n candles sorted by time (oldest to newest).
    The candles represent:
    - Candle T-2 (2 minutes ago - completed)
    - Candle T-1 (1 minute ago - completed)
    - Candle T (current minute - still forming)
    """
    try:
        ticker = yf.Ticker(f"{symbol}=X")

        # Fetch last N+1 candles to ensure we have N complete ones
        # Period "1d" gives us intraday data for today
        data = ticker.history(interval=interval, period="1d")

        if data.empty:
            print("  [WARNING] No data returned")
            return None

        # Get the N most recent candles
        # We get the last N rows, which include the current forming candle
        recent = data.tail(n).copy()

        return recent

    except Exception as e:
        print(f"  [ERROR] Error fetching data: {e}")
        return None


def upsert_candles(cursor, conn, candles, symbol, interval):
    """
    Upsert candles to database.

    Returns: (inserted_count, updated_count)
    """
    if candles is None or candles.empty:
        return (0, 0)

    insert_sql = """
        INSERT INTO public.market_features
        (time, symbol, interval, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """

    rows_to_insert = []
    skipped_forming = 0

    for timestamp, row in candles.iterrows():
        # Convert to UTC if timezone-aware
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert('UTC').tz_localize(None)

        # Skip the current forming candle (last incomplete minute)
        # We only want completed candles
        now = datetime.now()
        if timestamp >= now.replace(second=0, microsecond=0):
            skipped_forming += 1
            continue

        rows_to_insert.append((
            timestamp,
            symbol,
            interval,
            float(row.get('Open', 0)),
            float(row.get('High', 0)),
            float(row.get('Low', 0)),
            float(row.get('Close', 0)),
            int(row.get('Volume', 0))
        ))

    if not rows_to_insert:
        return (0, 0)

    # Execute batch upsert
    cursor.executemany(insert_sql, rows_to_insert)
    conn.commit()

    return (len(rows_to_insert), 0)


def get_db_stats(cursor, symbol):
    """Get current database statistics for the symbol."""
    # Total count
    cursor.execute(
        "SELECT COUNT(*) FROM public.market_features WHERE symbol = %s",
        (symbol,)
    )
    total = cursor.fetchone()[0]

    # Latest row
    cursor.execute(
        "SELECT MAX(time) FROM public.market_features WHERE symbol = %s",
        (symbol,)
    )
    latest = cursor.fetchone()[0]

    return {'total': total, 'latest': latest}


def incremental_fetch_loop():
    """Main incremental fetch loop."""
    global running

    print("=" * 60)
    print(f"Incremental 1-Minute Fetch for {SYMBOL}")
    print("=" * 60)
    print(f"Fetching {FETCH_COUNT} recent candles every ~60 seconds")
    print(f"Interval: {INTERVAL}")
    print(f"Press Ctrl+C to stop\n")

    # Test connection first
    print("Testing database connection...")
    try:
        conn = get_db_connection()
        print("[OK] Database connected\n")
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        print("\nEnsure TimescaleDB is running:")
        print("  docker ps | grep timescaledb")
        return

    cursor = conn.cursor()

    # Show initial stats
    stats = get_db_stats(cursor, SYMBOL)
    print(f"Initial DB stats:")
    print(f"  Total rows: {stats['total']:,}")
    print(f"  Latest candle: {stats['latest']}\n")

    cycle_count = 0
    total_inserted = 0

    try:
        while running:
            cycle_count += 1
            cycle_start = time.time()

            print(f"\n[{'=' * 56}]")
            print(f"Cycle {cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"[{'=' * 56}]")

            # Fetch latest N candles
            candles = fetch_latest_n_candles(SYMBOL, n=FETCH_COUNT, interval=INTERVAL)

            if candles is not None and not candles.empty:
                print(f"  Fetched {len(candles)} candles from YFinance")

                # Show the candles
                print("\n  Latest candles:")
                for ts, row in candles.iterrows():
                    ts_str = ts.strftime('%H:%M') if ts.tzinfo is None else ts.strftime('%H:%M %Z')
                    print(f"    {ts_str}: O={row['Open']:.5f} H={row['High']:.5f} "
                          f"L={row['Low']:.5f} C={row['Close']:.5f}")

                # Upsert to database
                inserted, updated = upsert_candles(cursor, conn, candles, SYMBOL, INTERVAL)

                if inserted > 0:
                    total_inserted += inserted
                    print(f"\n  [OK] Upserted {inserted} candles to database")
                else:
                    print(f"\n  - No new candles (all duplicates or still forming)")

            # Calculate sleep time to run approximately every minute
            elapsed = time.time() - cycle_start
            sleep_time = max(0, 60 - elapsed)

            if running:
                print(f"\n  Waiting {sleep_time:.1f} seconds until next fetch...")
                print(f"  Total inserted so far: {total_inserted:,}")

                # Sleep in small increments to allow quick shutdown
                sleep_start = time.time()
                while time.time() - sleep_start < sleep_time and running:
                    time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Final stats
        print("\n" + "=" * 60)
        print("SHUTDOWN SUMMARY")
        print("=" * 60)
        print(f"Total cycles completed: {cycle_count}")
        print(f"Total candles inserted: {total_inserted:,}")

        stats = get_db_stats(cursor, SYMBOL)
        print(f"Final DB stats:")
        print(f"  Total rows: {stats['total']:,}")
        print(f"  Latest candle: {stats['latest']}")

        cursor.close()
        conn.close()

        print("\n[OK] Database connection closed")


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    incremental_fetch_loop()
