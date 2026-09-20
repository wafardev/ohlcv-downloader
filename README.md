# OHLCV Downloader

A high-performance, production-ready cryptocurrency OHLCV (Open, High, Low, Close, Volume) candlestick downloader built on top of [CCXT](https://github.com/ccxt/ccxt) and [Pandas](https://pandas.pydata.org/).

Designed specifically for backtesting, machine learning, and algorithmic trading with full support for deep historical backfills across **4h**, **1d**, **1w**, or any arbitrary timeframe.

---

## Key Features

- ⚡ **Multi-Timeframe Support**: Seamlessly fetch multiple timeframes at once (defaults to `4h`, `1d`, `1w`).
- 🔄 **Automated Forward Pagination**: Transparently handles batch limits (500–1,000 candles per API call) and paginates forward using the timestamp cursor (`since = last_timestamp + 1`).
- ⏱️ **Rate-Limit & Anti-Ban Safety**: Automatically respects exchange rate limits (`enableRateLimit: True`) with exponential backoff and retries on transient network errors or HTTP 429s.
- 🚫 **Unclosed Candle Protection**: Automatically drops the currently forming active candle (`drop_unclosed=True`) to avoid lookahead bias and incomplete volume in backtests.
- 💾 **Multiple Storage Formats**: Export directly to **CSV**, **Parquet** (fast columnar storage), or **SQLite** database with automatic timestamp deduplication.
- 📅 **Custom Date Ranges**: Specify start (`--since`) and end (`--until`) dates in ISO 8601 format (e.g. `2017-08-01T00:00:00Z`).
- 🔌 **Exchange Agnostic**: Connects to Binance by default, but supports 100+ exchanges available in CCXT (Coinbase, Kraken, Bybit, OKX, etc.).

---

## Installation

```bash
pip install -r requirements.txt
```

Required packages:
- `ccxt>=4.0.0`
- `pandas>=2.0.0`
- `pyarrow>=14.0.0`

---

## Quick Start (CLI)

### 1. Download Full History from Beginning (Default)
When `--since` is omitted (or set to `from beginning`), the downloader automatically discovers the pair's initial listing date / earliest available candle on the exchange and downloads all historical data up to now:
```bash
python main.py --symbol BTC/USDT --timeframes 4h 1d 1w --format all
```

### 2. Download from a Specific Date
```bash
python main.py --symbol BTC/USDT --timeframes 4h 1d 1w --since 2024-01-01T00:00:00Z --format csv
```

### 3. Command-Line Arguments Reference

| Argument | Description | Default |
|---|---|---|
| `-s`, `--symbol` | Trading pair symbol (e.g., `BTC/USDT`, `ETH/USDT`) | `BTC/USDT` |
| `-t`, `--timeframes` | One or more timeframes (e.g. `4h 1d 1w`) | `4h 1d 1w` |
| `--exchange` | CCXT exchange identifier (see full list below) | `binance` |
| `--since` | Starting ISO timestamp or omit for earliest | `None` ("from beginning") |
| `--until` | Ending ISO timestamp (optional) | Current Time |
| `-o`, `--output-dir` | Target folder for saved files | `data/` |
| `-f`, `--format` | Storage format: `csv`, `parquet`, `sqlite`, or `all` | `csv` |
| `--keep-unclosed` | Keep active in-progress candle | `False` (dropped by default) |
| `--list-exchanges` | Print all exchanges supporting OHLCV and exit | `False` |

---

### Supported Values for `--exchange`

You can also run `python main.py --list-exchanges` at any time to display this list from the CLI.

All **89 exchanges** supported for OHLCV downloading via CCXT:

| Popular Categories | Exchange IDs |
|---|---|
| **Tier 1 Spot & Derivatives** | `binance`, `bybit`, `okx`, `coinbase`, `kraken`, `kucoin`, `gate`, `bitfinex`, `bitget`, `mexc`, `htx` |
| **DEXs & Perpetual Contracts** | `hyperliquid`, `dydx`, `deribit`, `bitmex`, `paradex`, `krakenfutures`, `kucoinfutures`, `binanceusdm`, `binancecoinm` |
| **US & Regulated Regional** | `coinbaseexchange`, `binanceus`, `gemini`, `bitstamp`, `bitvavo`, `cex`, `upbit`, `bithumb`, `indodax` |

<details open>
<summary><strong>Full Alphabetical List (89 exchanges)</strong></summary>

```
alpaca                 apex                   aster                  backpack
bequant                bigone                 binance                binancecoinm
binanceus              binanceusdm            bingx                  bitbank
bitfinex               bitget                 bithumb                bitmex
bitopro                bitrue                 bitso                  bitstamp
bitteam                bittrade               bitvavo                blofin
btcmarkets             btcturk                btse                   bullish
bybit                  bybiteu                bydfi                  cex
coinbase               coinbaseexchange       coinbaseinternational  coinex
coinsph                cryptocom              deepcoin               delta
deribit                digifinex              dydx                   extended
fmfwio                 foxbit                 gate                   gateeu
gemini                 grvt                   hashkey                hibachi
hitbtc                 hollaex                htx                    hyperliquid
indodax                kraken                 krakenfutures          kucoin
kucoinfutures          lbank                  lighter                luno
mercado                mexc                   modetrade              mudrex
myokx                  nado                   ndax                   okx
okxus                  onetrading             p2b                    pacifica
paradex                phemex                 poloniex               revolutx
tokocrypto             toobit                 upbit                  weex
whitebit               woo                    woofipro               xt
zebpay
```

</details>

---

## Python API Usage

You can also use the downloader directly inside your Python scripts or Jupyter notebooks:

```python
from ohlcv import OHLCVDownloader, save_ohlcv, load_ohlcv

# 1. Initialize downloader
downloader = OHLCVDownloader(exchange_id="binance")

# 2. Fetch multiple timeframes
data = downloader.fetch_multiple(
    symbol="BTC/USDT",
    timeframes=["4h", "1d", "1w"],
    since="2024-01-01T00:00:00Z",
    drop_unclosed=True,  # Discards forming candle to prevent lookahead bias
)

# 3. Access pandas DataFrames
df_4h = data["4h"]
df_1d = data["1d"]
df_1w = data["1w"]

print(df_1d.tail())

# 4. Save to Parquet or CSV
save_ohlcv(df_1d, symbol="BTC/USDT", timeframe="1d", output_dir="data", format="parquet")

# 5. Reload later
loaded_df = load_ohlcv("BTC/USDT", "1d", data_dir="data", format="parquet")
```

---

## Important Practical Notes

1. **In-Progress (Unclosed) Candles**:
   The most recent candle returned by the exchange is actively forming (e.g. today's daily candle or the current 4-hour bar). By default, the downloader automatically removes this row so backtests and models aren't corrupted by partial volume or intra-candle price swings. Use `--keep-unclosed` if you need the live candle.

2. **Weekly Candle Anchoring**:
   Most crypto exchanges (including Binance) anchor weekly candles (`1w`) to **Monday 00:00:00 UTC**.

3. **Timeframe Coverage per 1,000-candle Batch**:
   - **4h**: 1,000 candles ≈ 5.5 months (~20 requests for entire Binance history).
   - **1d**: 1,000 candles ≈ 2.7 years (~3–4 requests for entire history).
   - **1w**: 1,000 candles ≈ 19.2 years (retrieved in a single request).

4. **Rate Limits**:
   Because higher timeframes (`4h`, `1d`, `1w`) require very few HTTP calls, full historical downloads complete in seconds without triggering exchange rate bans.

---

## Running Tests

Run the test suite with:

```bash
python3 -m unittest discover -s tests
```
