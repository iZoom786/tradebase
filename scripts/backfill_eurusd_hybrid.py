#!/usr/bin/env python3
"""
Hybrid backfill for EURUSD:
- Last 7 days: 1-minute data
- 7 days to 1 year: Hourly data

YFinance only provides 1-minute intraday data for the last 7 days.
For historical data beyond 7 days, we use hourly candles.

Usage:
    python scripts/backfill_eurusd_hybrid.py
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

def get_db_connection():
    """Create database connection."""
    return psycopg2.connect(**DB_CONFIG)


def generate_timekey(timestamp, interval):
    """Generate timekey based on interval."""
    if interval == '1m':
        return int(timestamp.strftime('%Y%m%d%H%M'))
    elif interval == '1h':
        return int(timestamp.strftime('%Y%m%d%H'))
    elif interval == '1d':
        return int(timestamp.strftime('%Y%m%d'))
    else:
        return int(timestamp.strftime('%Y%m%d%H%M'))


def fetch_1m_data_last_7_days(symbol):
    """Fetch 1-minute data for the last 7 days."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    print(f"\n[1m] Fetching last 7 days of 1-minute data...")
    print(f"     Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    try:
        ticker = yf.Ticker(f"{symbol}=X")
        data = ticker.history(interval='1m', period='7d')

        if data.empty:
            print("     [WARNING] No 1m data available")
            return pd.DataFrame()

        print(f"     [OK] Got {len(data)} candles")
        return data

    except Exception as e:
        print(f"     [ERROR] {e}")
        return pd.DataFrame()


def fetch_1h_data_historical(symbol, days=365):
    """Fetch hourly data for the specified period."""
    end_date = datetime.now() - timedelta(days=7)  # Start from 7 days ago
    start_date = end_date - timedelta(days=days)

    print(f"\n[1h] Fetching hourly data for {days} days...")
    print(f"     Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    chunks = []
    current_start = start_date
    chunk_days = 30  # 30-day chunks for hourly data

    while current_start < end_date:
        current_end = min(current_start + timedelta(days=chunk_days), end_date)

        print(f"     Fetching {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}...")

        try:
            ticker = yf.Ticker(f"{symbol}=X")
            data = ticker.history(
                interval='1h',
                start=current_start.strftime('%Y-%m-%d'),
                end=current_end.strftime('%Y-%m-%d')
            )

            if not data.empty:
                chunks.append(data)
                print(f"       [OK] Got {len(data)} candles")
            else:
                print(f"       [WARNING] No data for this period")

            time.sleep(0.3)  # Small delay to avoid rate limits

        except Exception as e:
            print(f"       [ERROR] {e}")

        current_start = current_end + timedelta(days=1)

    if chunks:
        combined = pd.concat(chunks).sort_index()
        print(f"     [OK] Total hourly candles: {len(combined)}")
        return combined
    return pd.DataFrame()


def insert_data(cursor, conn, data, symbol, interval):
    """Insert data into database."""
    if data.empty:
        return 0

    insert_sql = """
        INSERT INTO public.market_features
        (time, symbol, interval, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """

    rows_to_insert = []
    batch_size = 5000
    total_inserted = 0

    for timestamp, row in data.iterrows():
        # Convert to UTC if timezone-aware
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert('UTC').tz_localize(None)

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

        # Insert in batches
        if len(rows_to_insert) >= batch_size:
            cursor.executemany(insert_sql, rows_to_insert)
            conn.commit()
            total_inserted += len(rows_to_insert)
            print(f"       Progress: {total_inserted} inserted...")
            rows_to_insert = []

    # Insert remaining
    if rows_to_insert:
        cursor.executemany(insert_sql, rows_to_insert)
        conn.commit()
        total_inserted += len(rows_to_insert)

    return total_inserted


def main():
    """Main backfill function."""
    print("=" * 60)
    print("EURUSD Hybrid Backfill (1m + 1h)")
    print("=" * 60)
    print("\nStrategy:")
    print("  - Last 7 days: 1-minute data")
    print("  - 7 days to 1 year: Hourly data")

    # Test connection
    print("\nTesting database connection...")
    try:
        conn = get_db_connection()
        print("[OK] Database connected\n")
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        return

    cursor = conn.cursor()
    total_1m = 0
    total_1h = 0

    try:
        # Step 1: Fetch 1-minute data for last 7 days
        data_1m = fetch_1m_data_last_7_days(SYMBOL)
        if not data_1m.empty:
            print("\n[1m] Inserting data...")
            total_1m = insert_data(cursor, conn, data_1m, SYMBOL, '1m')
            print(f"[OK] Inserted {total_1m:,} 1-minute candles")

        # Step 2: Fetch hourly data for the rest of the year
        data_1h = fetch_1h_data_historical(SYMBOL, days=365)
        if not data_1h.empty:
            print("\n[1h] Inserting data...")
            total_1h = insert_data(cursor, conn, data_1h, SYMBOL, '1h')
            print(f"[OK] Inserted {total_1h:,} hourly candles")

        # Summary
        print("\n" + "=" * 60)
        print("BACKFILL SUMMARY")
        print("=" * 60)
        print(f"1-minute candles (last 7 days): {total_1m:,}")
        print(f"Hourly candles (rest of year): {total_1h:,}")
        print(f"Total candles inserted: {total_1m + total_1h:,}")

        # Verify
        cursor.execute("SELECT COUNT(*) FROM public.market_features WHERE symbol = %s", (SYMBOL,))
        count = cursor.fetchone()[0]
        print(f"Total rows in DB for {SYMBOL}: {count:,}")

        cursor.execute(
            "SELECT MIN(time), MAX(time) FROM public.market_features WHERE symbol = %s",
            (SYMBOL,)
        )
        min_time, max_time = cursor.fetchone()
        print(f"Data range: {min_time} to {max_time}")

        # Show breakdown by interval
        cursor.execute(
            "SELECT interval, COUNT(*) FROM public.market_features WHERE symbol = %s GROUP BY interval",
            (SYMBOL,)
        )
        print("\nData by interval:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]:,} candles")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
