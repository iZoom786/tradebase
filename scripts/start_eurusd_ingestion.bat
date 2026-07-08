@echo off
REM EURUSD Data Ingestion - 1 Year Backfill + Incremental Fetch
REM
REM This script first loads 1 year of historical 1-minute EURUSD data,
REM then starts incremental fetching every minute.

echo ============================================================
echo EURUSD 1-Minute Data Ingestion
echo ============================================================
echo.

echo Step 1: Initial 1-year backfill (this will take 10-15 minutes)
echo ------------------------------------------------------------
python scripts\backfill_eurusd_1y_1m.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Backfill failed. Please check the error above.
    echo Ensure TimescaleDB is running: docker ps ^| findstr timescaledb
    pause
    exit /b 1
)

echo.
echo Step 2: Starting incremental fetch (runs continuously)
echo ------------------------------------------------------------
echo Press Ctrl+C to stop the incremental fetch
echo.

python scripts\incremental_fetch_1m.py
