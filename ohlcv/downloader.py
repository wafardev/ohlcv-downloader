"""
OHLCV Data Downloader using CCXT with robust pagination, rate-limiting,
and unclosed candle handling.
"""

from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union
import ccxt
import pandas as pd

logger = logging.getLogger("ohlcv_downloader")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class OHLCVDownloader:
    """
    Downloads historical OHLCV candlestick data from crypto exchanges via CCXT.
    Handles rate-limits, automated timestamp pagination forward in time,
    retries on network dropouts, and options to drop incomplete active candles.
    """

    @staticmethod
    def list_supported_exchanges(require_ohlcv: bool = True) -> List[str]:
        """Return a sorted list of CCXT exchange IDs that support OHLCV fetching."""
        exchanges = []
        for ex_id in ccxt.exchanges:
            if not require_ohlcv:
                exchanges.append(ex_id)
                continue
            try:
                ex = getattr(ccxt, ex_id)()
                if ex.has.get("fetchOHLCV", False):
                    exchanges.append(ex_id)
            except Exception:
                pass
        return sorted(exchanges)

    def __init__(
        self,
        exchange_id: str = "binance",
        exchange_params: Optional[dict] = None,
        max_retries: int = 5,
        retry_delay_seconds: float = 2.0,
    ):
        params = {"enableRateLimit": True, "timeout": 30000}
        if exchange_params:
            params.update(exchange_params)

        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"Exchange '{exchange_id}' is not supported by CCXT.")

        exchange_class = getattr(ccxt, exchange_id)
        self.exchange: ccxt.Exchange = exchange_class(params)
        self.exchange_id = exchange_id
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def parse_datetime_to_ms(self, dt_val: Optional[Union[int, str, datetime]]) -> Optional[int]:
        """Convert string ISO8601, datetime object, or ms int to epoch milliseconds."""
        if dt_val is None:
            return None
        if isinstance(dt_val, str) and dt_val.strip().lower() in (
            "from beginning",
            "beginning",
            "start",
            "earliest",
            "all",
            "0",
        ):
            return None
        if isinstance(dt_val, int):
            return dt_val
        if isinstance(dt_val, str):
            # Parse via CCXT or standard datetime
            try:
                parsed = self.exchange.parse8601(dt_val)
                if parsed is not None:
                    return parsed
            except Exception:
                pass
            dt = datetime.fromisoformat(dt_val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        if isinstance(dt_val, datetime):
            if dt_val.tzinfo is None:
                dt_val = dt_val.replace(tzinfo=timezone.utc)
            return int(dt_val.timestamp() * 1000)
        raise ValueError(f"Unable to parse datetime: {dt_val}")

    def get_earliest_timestamp(self, symbol: str, timeframe: str = "1d") -> Optional[int]:
        """
        Discover the earliest recorded timestamp for this symbol and timeframe.
        Attempts since=0 first (works for Binance, Coinbase, Bybit, etc.),
        and falls back to since=None.
        """
        try:
            candles = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=0, limit=2)
            if candles and len(candles) > 0:
                return candles[0][0]
        except Exception:
            pass

        try:
            candles = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=None, limit=1000)
            if candles and len(candles) > 0:
                return candles[0][0]
        except Exception:
            pass

        return None

    def fetch_timeframe(
        self,
        symbol: str,
        timeframe: str = "1d",
        since: Optional[Union[int, str, datetime]] = None,
        until: Optional[Union[int, str, datetime]] = None,
        limit_per_call: int = 1000,
        drop_unclosed: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch full historical OHLCV data for a single timeframe using pagination.

        :param symbol: Trading pair, e.g. 'BTC/USDT'
        :param timeframe: Candle timeframe, e.g. '4h', '1d', '1w'
        :param since: Start timestamp in ms, ISO string, datetime, or None / "from beginning" (earliest available)
        :param until: End timestamp in ms, ISO string, or datetime (defaults to current time)
        :param limit_per_call: Number of candles per request (exchange max, usually 500-1000)
        :param drop_unclosed: Whether to drop the last in-progress (unclosed) candle
        :return: pandas.DataFrame with columns: timestamp, open, high, low, close, volume
        """
        if not self.exchange.has.get("fetchOHLCV", False):
            raise NotImplementedError(f"Exchange {self.exchange_id} does not support fetchOHLCV.")

        start_ms = self.parse_datetime_to_ms(since)
        end_ms = self.parse_datetime_to_ms(until) or self.exchange.milliseconds()

        # If since is None, default to "from beginning" (earliest available on exchange)
        if start_ms is None:
            logger.info(
                f"No 'since' parameter provided (or 'from beginning'); discovering earliest available candle "
                f"for {symbol} [{timeframe}] on {self.exchange_id}..."
            )
            earliest_found = self.get_earliest_timestamp(symbol, timeframe)
            if earliest_found is not None:
                start_ms = earliest_found
                logger.info(
                    f"Earliest candle for {symbol} [{timeframe}] found at "
                    f"{pd.to_datetime(start_ms, unit='ms', utc=True)}."
                )
            else:
                start_ms = 0

        current_since = start_ms

        logger.info(
            f"Fetching '{symbol}' [{timeframe}] from {self.exchange_id} "
            f"(since={pd.to_datetime(start_ms, unit='ms', utc=True)} / until={pd.to_datetime(end_ms, unit='ms', utc=True)})..."
        )

        all_candles: List[list] = []
        batch_count = 0

        while current_since < end_ms:
            batch = self._fetch_ohlcv_with_retry(
                symbol=symbol,
                timeframe=timeframe,
                since=current_since,
                limit=limit_per_call,
            )

            if not batch:
                logger.info(f"No further candles returned for {symbol} [{timeframe}].")
                break

            # Filter candles that exceed 'until'
            filtered_batch = [c for c in batch if c[0] <= end_ms]
            all_candles.extend(filtered_batch)
            batch_count += 1

            last_candle_ts = batch[-1][0]
            first_candle_ts = batch[0][0]

            logger.info(
                f"Batch {batch_count}: received {len(batch)} candles "
                f"({pd.to_datetime(first_candle_ts, unit='ms', utc=True)} -> "
                f"{pd.to_datetime(last_candle_ts, unit='ms', utc=True)}) | Total: {len(all_candles)}"
            )

            # Prevent infinite loop if exchange returns same timestamp
            next_since = last_candle_ts + 1
            if next_since <= current_since:
                logger.warning("Timestamp did not advance; breaking pagination loop to prevent infinite cycle.")
                break

            current_since = next_since

            # If the batch returned fewer than requested, we have caught up with current time
            if len(batch) < limit_per_call:
                logger.info("Batch size less than limit; reached latest available candle.")
                break

            # Respect rate limit
            rate_limit_sec = (getattr(self.exchange, "rateLimit", 200) or 200) / 1000.0
            time.sleep(rate_limit_sec)

        if not all_candles:
            logger.warning(f"No candles collected for {symbol} [{timeframe}].")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        
        # Deduplicate and sort
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        # Convert timestamp to UTC datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

        # Drop the last unclosed candle if requested
        if drop_unclosed and len(df) > 0:
            last_candle_time = df["timestamp"].iloc[-1]
            logger.info(f"Dropping active in-progress candle at {last_candle_time} to prevent lookahead bias.")
            df = df.iloc[:-1].reset_index(drop=True)

        logger.info(
            f"Successfully collected {len(df)} candles for {symbol} [{timeframe}] "
            f"({df['timestamp'].min()} to {df['timestamp'].max() if len(df) > 0 else 'N/A'})."
        )
        return df

    def fetch_multiple(
        self,
        symbol: str,
        timeframes: Optional[List[str]] = None,
        since: Optional[Union[int, str, datetime]] = None,
        until: Optional[Union[int, str, datetime]] = None,
        drop_unclosed: bool = True,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch OHLCV data across multiple timeframes (default: ['4h', '1d', '1w']).

        :param symbol: Trading pair, e.g. 'BTC/USDT'
        :param timeframes: List of timeframes (defaults to ['4h', '1d', '1w'])
        :param since: Start timestamp
        :param until: End timestamp
        :param drop_unclosed: Whether to drop currently forming active candle
        :return: Dictionary mapping timeframe to DataFrame
        """
        if timeframes is None:
            timeframes = ["4h", "1d", "1w"]

        results = {}
        for tf in timeframes:
            results[tf] = self.fetch_timeframe(
                symbol=symbol,
                timeframe=tf,
                since=since,
                until=until,
                drop_unclosed=drop_unclosed,
            )
        return results

    def _fetch_ohlcv_with_retry(
        self,
        symbol: str,
        timeframe: str,
        since: int,
        limit: int,
    ) -> List[list]:
        """Fetch a single batch with exponential backoff on network or rate limit errors."""
        retries = 0
        while retries < self.max_retries:
            try:
                candles = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
                return candles or []
            except (ccxt.NetworkError, ccxt.RateLimitExceeded) as e:
                retries += 1
                backoff = self.retry_delay_seconds * (2 ** (retries - 1))
                logger.warning(
                    f"Transient error on {self.exchange_id} ({e.__class__.__name__}: {e}). "
                    f"Retrying in {backoff:.1f}s (attempt {retries}/{self.max_retries})..."
                )
                time.sleep(backoff)
            except ccxt.BaseError as e:
                logger.error(f"CCXT error when fetching {symbol} {timeframe}: {e}")
                raise

        raise RuntimeError(f"Failed to fetch {symbol} [{timeframe}] after {self.max_retries} retries.")
