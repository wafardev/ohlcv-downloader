#!/usr/bin/env python3
"""
OHLCV Downloader CLI
Fetch historical candlestick data for any cryptocurrency pair across 4h, 1d, 1w (or any timeframe).
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path
from ohlcv.downloader import OHLCVDownloader
from ohlcv.storage import save_ohlcv


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download historical OHLCV data using CCXT with automatic pagination and storage."
    )
    parser.add_argument(
        "-s", "--symbol",
        type=str,
        default="BTC/USDT",
        help="Trading pair symbol (default: BTC/USDT)",
    )
    parser.add_argument(
        "-t", "--timeframes",
        nargs="+",
        default=["4h", "1d", "1w"],
        help="List of candle timeframes to download (default: 4h 1d 1w)",
    )
    parser.add_argument(
        "--exchange",
        type=str,
        default="binance",
        help="Exchange ID supported by CCXT (default: binance)",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Start date/time in ISO format (e.g. 2024-01-01T00:00:00Z). If omitted or 'from beginning', defaults to the earliest available data on the exchange.",
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        help="Optional end date/time in ISO format (default: current time)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default="data",
        help="Output directory to save downloaded data (default: data/)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["csv", "parquet", "sqlite", "all"],
        default="csv",
        help="Storage format: csv, parquet, sqlite, or all (default: csv)",
    )
    parser.add_argument(
        "--keep-unclosed",
        action="store_true",
        default=False,
        help="Keep the current in-progress candle (by default, incomplete active candle is dropped to prevent lookahead bias)",
    )
    parser.add_argument(
        "--list-exchanges",
        action="store_true",
        default=False,
        help="List all CCXT exchanges that support OHLCV fetching and exit",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.list_exchanges:
        print("Discovering exchanges supporting OHLCV in CCXT...")
        supported = OHLCVDownloader.list_supported_exchanges()
        print(f"\nSupported Exchanges ({len(supported)} total):")
        print("-" * 50)
        # Print nicely formatted in columns of 4
        col_width = 22
        for i in range(0, len(supported), 3):
            row = supported[i:i+3]
            print("".join(s.ljust(col_width) for s in row))
        print("-" * 50)
        sys.exit(0)

    drop_unclosed = not args.keep_unclosed

    since_display = args.since if args.since is not None else "FROM BEGINNING (earliest available)"

    print("=" * 65)
    print("                OHLCV CANDLESTICK DOWNLOADER")
    print("=" * 65)
    print(f"Exchange:       {args.exchange.upper()}")
    print(f"Symbol:         {args.symbol}")
    print(f"Timeframes:     {', '.join(args.timeframes)}")
    print(f"Start (Since):  {since_display}")
    print(f"End (Until):    {args.until or 'NOW'}")
    print(f"Drop Unclosed:  {drop_unclosed}")
    print(f"Save Format:    {args.format}")
    print(f"Destination:    {args.output_dir}/")
    print("=" * 65 + "\n")

    try:
        downloader = OHLCVDownloader(exchange_id=args.exchange)
    except Exception as e:
        print(f"Error initializing exchange '{args.exchange}': {e}", file=sys.stderr)
        sys.exit(1)

    formats = ["csv", "parquet", "sqlite"] if args.format == "all" else [args.format]

    for tf in args.timeframes:
        print(f"\n>>> Processing timeframe: [{tf}] for {args.symbol}...")
        try:
            df = downloader.fetch_timeframe(
                symbol=args.symbol,
                timeframe=tf,
                since=args.since,
                until=args.until,
                drop_unclosed=drop_unclosed,
            )

            if df.empty:
                print(f"No candles found for {args.symbol} [{tf}].")
                continue

            for fmt in formats:
                saved_path = save_ohlcv(
                    df=df,
                    symbol=args.symbol,
                    timeframe=tf,
                    output_dir=args.output_dir,
                    format=fmt,
                )
                print(f"[{fmt.upper()}] Saved {len(df)} candles to: {saved_path}")

            print(f"Summary for {args.symbol} [{tf}]:")
            print(f"  First candle: {df['timestamp'].min()}")
            print(f"  Last candle:  {df['timestamp'].max()}")
            print(f"  Total bars:   {len(df):,}")
            print(f"  Columns:      {list(df.columns)}")

        except Exception as e:
            print(f"Failed to fetch timeframe {tf}: {e}", file=sys.stderr)

    print("\n" + "=" * 65)
    print("Download completed!")
    print("=" * 65)


if __name__ == "__main__":
    main()
