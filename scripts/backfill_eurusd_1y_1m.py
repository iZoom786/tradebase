#!/usr/bin/env python3
"""
Initial 1-year backfill for EURUSD 1-minute data.

This script loads historical 1-minute data for the past year
in batches to avoid API rate limits.

Usage:
    python scripts/backfill_eurusd_1y_1m.py
"""

import psycopg2
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import time

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'tradebase',
    'user': 'postgres',
    'password': 'postgres'
}

SYMBOL = 'EURUSD'
INTERVAL = '1m'  # 1 minute candles


def get_db_connection():
    """Create database connection."""
    return psycopg2.connect(**DB_CONFIG)


def fetch_data_in_chunks(symbol, start_date, end_date, interval='1m', chunk_days=7):
    """
    Fetch data in chunks to avoid API limits.
    YFinance has limits on how much data can be fetched at once.
    """
    chunks = []
    current_start = start_date

    while current_start < end_date:
        current_end = min(current_start + timedelta(days=chunk_days), end_date)

        print(f"  Fetching {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}...")

        try:
            ticker = yf.Ticker(f"{symbol}=X")
            data = ticker.history(
                interval=interval,
                start=current_start.strftime('%Y-%m-%d'),
                end=current_end.strftime('%Y-%m-%d')
            )

            if not data.empty:
                chunks.append(data)
                print(f"    [OK] Got {len(data)} candles")
            else:
                print(f"    [WARNING] No data for this period")

            # Small delay to avoid rate limits
            time.sleep(0.5)

        except Exception as e:
            print(f"    [ERROR] Error: {e}")

        current_start = current_end + timedelta(days=1)

    # Combine all chunks
    if chunks:
        return pd.concat(chunks).sort_index()
    return pd.DataFrame()


def generate_timekey(timestamp):
    """Generate timekey in YYYYMMDDHHMM format for 1-minute data."""
    return int(timestamp.strftime('%Y%m%d%H%M'))


def backfill_1y_1m():
    """Backfill 1 year of 1-minute data for EURUSD."""
    print("=" * 60)
    print("EURUSD 1-Year 1-Minute Backfill")
    print("=" * 60)

    # Calculate date range (1 year back from now)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    print(f"\nSymbol: {SYMBOL}")
    print(f"Interval: {INTERVAL}")
    print(f"Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Expected candles: ~525,600 (365 days × 24 hours × 60 minutes)")
    print()

    # Test connection
    print("Testing database connection...")
    try:
        conn = get_db_connection()
        print("[OK] Database connected\n")
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        print("\nEnsure TimescaleDB is running:")
        print("  docker ps | grep timescaledb")
        return

    # Fetch data in chunks (30 days at a time)
    print("Fetching historical data from YFinance...")
    print("(This may take 10-15 minutes due to rate limits...)\n")

    data = fetch_data_in_chunks(
        symbol=SYMBOL,
        start_date=start_date,
        end_date=end_date,
        interval=INTERVAL,
        chunk_days=30
    )

    if data.empty:
        print("[ERROR] No data retrieved from YFinance")
        return

    print(f"\n[OK] Total candles retrieved: {len(data)}")

    # Prepare and insert data
    print("\nPreparing data for insertion...")

    cursor = conn.cursor()
    total_inserted = 0
    total_skipped = 0
    batch_size = 5000

    try:
        rows_to_insert = []

        for timestamp, row in data.iterrows():
            # Convert to UTC if timezone-aware
            if timestamp.tzinfo is not None:
                timestamp = timestamp.tz_convert('UTC').tz_localize(None)

            timekey = generate_timekey(timestamp)

            rows_to_insert.append((
                timestamp,
                SYMBOL,
                INTERVAL,
                float(row.get('Open', 0)),
                float(row.get('High', 0)),
                float(row.get('Low', 0)),
                float(row.get('Close', 0)),
                int(row.get('Volume', 0)),
                timekey
            ))

            # Insert in batches
            if len(rows_to_insert) >= batch_size:
                inserted, skipped = insert_batch(cursor, conn, rows_to_insert)
                total_inserted += inserted
                total_skipped += skipped
                print(f"  Progress: {total_inserted} inserted, {total_skipped} skipped...")
                rows_to_insert = []

        # Insert remaining rows
        if rows_to_insert:
            inserted, skipped = insert_batch(cursor, conn, rows_to_insert)
            total_inserted += inserted
            total_skipped += skipped

        print(f"\n[OK] Backfill Complete!")
        print(f"   Total inserted: {total_inserted}")
        print(f"   Total skipped (duplicates): {total_skipped}")

        # Verify data
        cursor.execute("SELECT COUNT(*) FROM public.market_features WHERE symbol = %s", (SYMBOL,))
        count = cursor.fetchone()[0]
        print(f"   Total rows in DB for {SYMBOL}: {count}")

        # Get date range
        cursor.execute(
            "SELECT MIN(time), MAX(time) FROM public.market_features WHERE symbol = %s",
            (SYMBOL,)
        )
        min_time, max_time = cursor.fetchone()
        print(f"   Data range: {min_time} to {max_time}")

    except Exception as e:
        print(f"\n[ERROR] Error during backfill: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def insert_batch(cursor, conn, rows):
    """Insert a batch of rows and return (inserted, skipped) counts."""
    insert_sql = """
        INSERT INTO public.market_features
        (time, symbol, interval, open, high, low, close, volume, timekey)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (time, timekey, symbol)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume
        RETURNING (xmax = 0) AS inserted
    """

    cursor.executemany(insert_sql, rows)
    conn.commit()

    # Count how many were inserts vs updates
    # xmax = 0 means it was an insert (new row)
    inserted = sum(1 for r in cursor.fetchall() if r[0])
    skipped = len(rows) - inserted

    return (inserted, skipped)


if __name__ == "__main__":
    backfill_1y_1m()
