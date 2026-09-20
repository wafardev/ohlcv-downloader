import unittest
from unittest.mock import MagicMock
import tempfile
import shutil
from pathlib import Path
import pandas as pd
from ohlcv.downloader import OHLCVDownloader
from ohlcv.storage import save_ohlcv, load_ohlcv, sanitize_filename


class TestOHLCVDownloader(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("BTC/USDT", "4h", "csv"), "BTC_USDT_4h.csv")
        self.assertEqual(sanitize_filename("ETH-USDT:USDT", "1d", "parquet"), "ETH_USDT_USDT_1d.parquet")

    def test_storage_csv_parquet_sqlite(self):
        data = {
            "timestamp": pd.to_datetime(["2024-01-01 00:00:00", "2024-01-02 00:00:00"], utc=True),
            "open": [42000.0, 42500.0],
            "high": [43000.0, 43500.0],
            "low": [41500.0, 42000.0],
            "close": [42500.0, 43200.0],
            "volume": [1200.5, 1450.2],
        }
        df = pd.DataFrame(data)

        # CSV test
        csv_path = save_ohlcv(df, "BTC/USDT", "1d", output_dir=self.temp_dir, format="csv")
        self.assertTrue(csv_path.exists())
        loaded_csv = load_ohlcv("BTC/USDT", "1d", data_dir=self.temp_dir, format="csv")
        self.assertEqual(len(loaded_csv), 2)
        self.assertEqual(loaded_csv["close"].iloc[1], 43200.0)

        # Parquet test
        parquet_path = save_ohlcv(df, "BTC/USDT", "1d", output_dir=self.temp_dir, format="parquet")
        self.assertTrue(parquet_path.exists())
        loaded_parquet = load_ohlcv("BTC/USDT", "1d", data_dir=self.temp_dir, format="parquet")
        self.assertEqual(len(loaded_parquet), 2)

        # SQLite test
        sqlite_path = save_ohlcv(df, "BTC/USDT", "1d", output_dir=self.temp_dir, format="sqlite")
        self.assertTrue(sqlite_path.exists())
        loaded_sqlite = load_ohlcv("BTC/USDT", "1d", data_dir=self.temp_dir, format="sqlite")
        self.assertEqual(len(loaded_sqlite), 2)

        # Test deduplication on append
        new_data = {
            "timestamp": pd.to_datetime(["2024-01-02 00:00:00", "2024-01-03 00:00:00"], utc=True),
            "open": [42500.0, 43200.0],
            "high": [43500.0, 44000.0],
            "low": [42000.0, 43000.0],
            "close": [43200.0, 43800.0],
            "volume": [1450.2, 1600.0],
        }
        df_new = pd.DataFrame(new_data)
        save_ohlcv(df_new, "BTC/USDT", "1d", output_dir=self.temp_dir, format="csv", append_mode=True)
        deduped = load_ohlcv("BTC/USDT", "1d", data_dir=self.temp_dir, format="csv")
        self.assertEqual(len(deduped), 3)  # 2 original + 1 unique new row

    def test_mock_pagination_and_drop_unclosed(self):
        downloader = OHLCVDownloader(exchange_id="binance")

        mock_candles_batch1 = [
            [1704067200000, 100, 105, 99, 104, 10],   # Jan 1 00:00
            [1704081600000, 104, 108, 103, 107, 12],  # Jan 1 04:00
        ]
        mock_candles_batch2 = [
            [1704096000000, 107, 110, 106, 109, 15],  # Jan 1 08:00 (active unclosed)
        ]

        mock_fetch = MagicMock(side_effect=[mock_candles_batch1, mock_candles_batch2, []])
        downloader.exchange.fetch_ohlcv = mock_fetch

        # With drop_unclosed=True
        df = downloader.fetch_timeframe(
            symbol="BTC/USDT",
            timeframe="4h",
            since=1704067200000,
            until=1704100000000,
            limit_per_call=2,
            drop_unclosed=True,
        )
        self.assertEqual(len(df), 2)  # 3 total fetched - 1 unclosed dropped = 2

        # With drop_unclosed=False
        downloader.exchange.fetch_ohlcv = MagicMock(side_effect=[mock_candles_batch1, mock_candles_batch2, []])
        df_keep = downloader.fetch_timeframe(
            symbol="BTC/USDT",
            timeframe="4h",
            since=1704067200000,
            until=1704100000000,
            limit_per_call=2,
            drop_unclosed=False,
        )
        self.assertEqual(len(df_keep), 3)

    def test_since_defaults_to_from_beginning(self):
        downloader = OHLCVDownloader(exchange_id="binance")

        # Mock earliest candle detection via since=0
        mock_earliest = [[1502928000000, 4261.48, 4485.39, 4200.74, 4285.08, 795.15]]
        mock_batch = [[1502928000000, 4261.48, 4485.39, 4200.74, 4285.08, 795.15]]

        downloader.exchange.fetch_ohlcv = MagicMock(side_effect=[mock_earliest, mock_batch, []])

        # When since=None
        df = downloader.fetch_timeframe(
            symbol="BTC/USDT",
            timeframe="1d",
            since=None,
            drop_unclosed=False,
        )
        self.assertEqual(len(df), 1)
        self.assertEqual(df["timestamp"].iloc[0], pd.to_datetime(1502928000000, unit="ms", utc=True))

        # When since="from beginning"
        downloader.exchange.fetch_ohlcv = MagicMock(side_effect=[mock_earliest, mock_batch, []])
        df_str = downloader.fetch_timeframe(
            symbol="BTC/USDT",
            timeframe="1d",
            since="from beginning",
            drop_unclosed=False,
        )
        self.assertEqual(len(df_str), 1)


if __name__ == "__main__":
    unittest.main()
