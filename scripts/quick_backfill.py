#!/usr/bin/env python3
"""
Quick backfill script to populate market_features table with forex data.
Run this directly with: python scripts/quick_backfill.py
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

# Forex pairs to backfill
FOREX_PAIRS = [
    'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD'
]

# Interval and period
INTERVAL = '1h'  # 1 hour candles
PERIOD = '30d'   # Last 30 days


def get_db_connection():
    """Create database connection."""
    return psycopg2.connect(**DB_CONFIG)


def backfill_data():
    """Backfill forex data into TimescaleDB."""
    print("Starting backfill...")

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        total_rows = 0
        start_time = time.time()

        for symbol in FOREX_PAIRS:
            print(f"\nFetching data for {symbol}...")

            # Fetch data from YFinance
            ticker = yf.Ticker(f"{symbol}=X")
            data = ticker.history(interval=INTERVAL, period=PERIOD)

            if data.empty:
                print(f"  No data returned for {symbol}")
                continue

            print(f"  Retrieved {len(data)} candles")

            # Prepare data for insertion
            rows_to_insert = []
            for timestamp, row in data.iterrows():
                # Convert timezone-aware timestamp to UTC if needed
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.tz_convert('UTC').tz_localize(None)

                rows_to_insert.append((
                    timestamp,
                    symbol,
                    INTERVAL,
                    float(row.get('Open', 0)),
                    float(row.get('High', 0)),
                    float(row.get('Low', 0)),
                    float(row.get('Close', 0)),
                    int(row.get('Volume', 0)),
                    # Generate timekey (YYYYMMDDHH format for hourly data)
                    int(timestamp.strftime('%Y%m%d%H'))
                ))

            # Insert data in batches
            if rows_to_insert:
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
                """
                cur.executemany(insert_sql, rows_to_insert)
                conn.commit()
                print(f"  ✓ Inserted {len(rows_to_insert)} rows for {symbol}")
                total_rows += len(rows_to_insert)

        elapsed = time.time() - start_time
        print(f"\n✅ Backfill complete! Total rows inserted: {total_rows}")
        print(f"   Time elapsed: {elapsed:.2f} seconds")

        # Verify data
        cur.execute("SELECT COUNT(*) FROM public.market_features")
        result = cur.fetchone()[0]
        print(f"Total rows in market_features table: {result}")

        # Show sample data
        cur.execute(
            "SELECT * FROM public.market_features ORDER BY time DESC LIMIT 5"
        )
        sample = cur.fetchall()

        # Get column names from cursor description
        col_names = [desc[0] for desc in cur.description]
        print("\nLatest 5 rows:")
        for row in sample:
            row_dict = dict(zip(col_names, row))
            print(f"  {row_dict['time']}: {row_dict['symbol']} - "
                  f"O:{row_dict['open']:.5f} H:{row_dict['high']:.5f} "
                  f"L:{row_dict['low']:.5f} C:{row_dict['close']:.5f}")

    except Exception as e:
        print(f"Error during backfill: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def check_table_exists():
    """Check if market_features table exists and show info."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Check if table exists
        cur.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'market_features'
            )
            """
        )
        exists = cur.fetchone()[0]

        if exists:
            print("✓ market_features table exists")

            # Check row count
            cur.execute("SELECT COUNT(*) FROM public.market_features")
            count = cur.fetchone()[0]
            print(f"  Current row count: {count}")

            # Check for each symbol
            cur.execute(
                """
                SELECT symbol, COUNT(*) as count,
                       MIN(time) as earliest, MAX(time) as latest
                FROM public.market_features
                GROUP BY symbol
                ORDER BY symbol
                """
            )
            symbols = cur.fetchall()

            if symbols:
                print("\n  Data by symbol:")
                for row in symbols:
                    print(f"    {row[0]}: {row[1]} rows, "
                          f"from {row[2]} to {row[3]}")
            else:
                print("  No data found in table")
        else:
            print("✗ market_features table does not exist")
            print("  Please ensure the database schema is initialized.")

    except Exception as e:
        print(f"Error checking table: {e}")
    finally:
        cur.close()
        conn.close()


def main():
    """Main entry point."""
    print("=" * 60)
    print("Quick Backfill for Tradebase Market Data")
    print("=" * 60)

    # Test connection first
    print("\nTesting database connection...")
    try:
        conn = get_db_connection()
        print("✓ Database connection successful")
        conn.close()
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("\nPlease ensure TimescaleDB is running:")
        print("  docker-compose ps timescaledb")
        return

    # Check current state
    print("\nChecking current database state...")
    check_table_exists()

    # Perform backfill
    print("\n" + "=" * 60)
    backfill_data()

    print("\n" + "=" * 60)
    print("Done! Check your data in pgAdmin at http://localhost:5050")
    print("=" * 60)


if __name__ == "__main__":
    main()
