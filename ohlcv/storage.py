"""Storage utilities for OHLCV data."""

from __future__ import annotations
from pathlib import Path
import sqlite3
import pandas as pd


def sanitize_filename(symbol: str, timeframe: str, ext: str) -> str:
    """Creates a clean filename from symbol and timeframe."""
    clean_sym = symbol.replace("/", "_").replace(":", "_").replace("-", "_")
    return f"{clean_sym}_{timeframe}.{ext}"


def save_ohlcv(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    output_dir: str | Path = "data",
    format: str = "csv",
    sqlite_db_name: str = "ohlcv.db",
    append_mode: bool = True,
) -> Path:
    """
    Save OHLCV DataFrame to disk in the desired format (csv, parquet, or sqlite).
    If append_mode is True and the file exists, merges and deduplicates timestamps.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if df.empty:
        return output_path

    # Ensure timestamp is datetime and sorted
    working_df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(working_df["timestamp"]):
        working_df["timestamp"] = pd.to_datetime(working_df["timestamp"], utc=True)
    working_df = working_df.sort_values("timestamp").reset_index(drop=True)

    format = format.lower()
    if format == "csv":
        file_path = output_path / sanitize_filename(symbol, timeframe, "csv")
        if append_mode and file_path.exists():
            existing = pd.read_csv(file_path)
            existing["timestamp"] = pd.to_datetime(existing["timestamp"], utc=True)
            combined = pd.concat([existing, working_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
            combined.to_csv(file_path, index=False)
        else:
            working_df.to_csv(file_path, index=False)
        return file_path

    elif format == "parquet":
        file_path = output_path / sanitize_filename(symbol, timeframe, "parquet")
        if append_mode and file_path.exists():
            existing = pd.read_parquet(file_path)
            if not pd.api.types.is_datetime64_any_dtype(existing["timestamp"]):
                existing["timestamp"] = pd.to_datetime(existing["timestamp"], utc=True)
            combined = pd.concat([existing, working_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
            combined.to_parquet(file_path, index=False)
        else:
            working_df.to_parquet(file_path, index=False)
        return file_path

    elif format in ("sqlite", "sqlite3", "db"):
        db_path = output_path / sqlite_db_name
        table_name = sanitize_filename(symbol, timeframe, "").rstrip(".")
        
        # Format timestamp to ISO string for sqlite compatibility
        sqlite_df = working_df.copy()
        sqlite_df["timestamp"] = sqlite_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S%z")

        with sqlite3.connect(db_path) as conn:
            # Create table with PRIMARY KEY on timestamp to prevent duplicates
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS "{table_name}" (
                    timestamp TEXT PRIMARY KEY,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL
                )
            """)
            # Upsert
            sqlite_df.to_sql("temp_stage", conn, if_exists="replace", index=False)
            conn.execute(f"""
                INSERT OR REPLACE INTO "{table_name}" (timestamp, open, high, low, close, volume)
                SELECT timestamp, open, high, low, close, volume FROM temp_stage
            """)
            conn.execute("DROP TABLE IF EXISTS temp_stage")
            conn.commit()

        return db_path

    else:
        raise ValueError(f"Unsupported format: {format}. Supported: csv, parquet, sqlite")


def load_ohlcv(
    symbol: str,
    timeframe: str,
    data_dir: str | Path = "data",
    format: str = "csv",
    sqlite_db_name: str = "ohlcv.db",
) -> pd.DataFrame:
    """Load previously saved OHLCV data."""
    data_path = Path(data_dir)
    format = format.lower()

    if format == "csv":
        file_path = data_path / sanitize_filename(symbol, timeframe, "csv")
        if not file_path.exists():
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = pd.read_csv(file_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    elif format == "parquet":
        file_path = data_path / sanitize_filename(symbol, timeframe, "parquet")
        if not file_path.exists():
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = pd.read_parquet(file_path)
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    elif format in ("sqlite", "sqlite3", "db"):
        db_path = data_path / sqlite_db_name
        if not db_path.exists():
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        table_name = sanitize_filename(symbol, timeframe, "").rstrip(".")
        with sqlite3.connect(db_path) as conn:
            try:
                df = pd.read_sql_query(f'SELECT * FROM "{table_name}" ORDER BY timestamp ASC', conn)
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                return df
            except Exception:
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    else:
        raise ValueError(f"Unsupported format: {format}")
