"""
Example script demonstrating programmatic usage of OHLCVDownloader.
"""

from ohlcv import OHLCVDownloader, save_ohlcv, load_ohlcv

def main():
    # 1. Initialize downloader with CCXT exchange
    downloader = OHLCVDownloader(exchange_id="binance")

    symbol = "BTC/USDT"
    timeframes = ["4h", "1d", "1w"]
    # If since=None (or omitted), it automatically defaults to "from beginning" (listing date)
    # You can also pass an explicit ISO timestamp like "2024-01-01T00:00:00Z"
    since = None

    print(f"Fetching {symbol} for timeframes {timeframes} (since={since or 'FROM BEGINNING'})...")
    data = downloader.fetch_multiple(
        symbol=symbol,
        timeframes=timeframes,
        since=since,
        drop_unclosed=True,  # Discards the in-progress candle to prevent lookahead bias
    )

    # 2. Inspect and save DataFrames
    for tf, df in data.items():
        print(f"\n--- {symbol} [{tf}] ---")
        print(df.tail())
        
        # Save to CSV
        csv_file = save_ohlcv(df, symbol=symbol, timeframe=tf, output_dir="data", format="csv")
        print(f"Saved CSV: {csv_file}")

        # Save to Parquet
        parquet_file = save_ohlcv(df, symbol=symbol, timeframe=tf, output_dir="data", format="parquet")
        print(f"Saved Parquet: {parquet_file}")

        # Save to SQLite
        sqlite_file = save_ohlcv(df, symbol=symbol, timeframe=tf, output_dir="data", format="sqlite")
        print(f"Saved SQLite: {sqlite_file}")

    # 3. Reload from disk to verify
    loaded_df = load_ohlcv(symbol, "1d", data_dir="data", format="parquet")
    print(f"\nLoaded {len(loaded_df)} daily candles from Parquet:")
    print(loaded_df.head(2))

if __name__ == "__main__":
    main()
