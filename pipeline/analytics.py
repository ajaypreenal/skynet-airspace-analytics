# pipeline/analytics.py
"""Analytics module for SkyNet Airspace Analytics.

This module holds a lightweight DuckDB in‑memory database that is populated
with the cleaned flight data from :pymod:`pipeline.ingestion`. It provides
functions for spatial aggregation, KPI calculation and anomaly detection.
All public functions are pure – they accept inputs and return pandas objects
or Python primitives; the internal DuckDB connection is hidden from callers.
"""

import logging
from typing import Dict, List, Tuple

import duckdb
import numpy as np
import pandas as pd

from ..config import CONGESTION_THRESHOLDS

# Configure module‑level logger
_logger = logging.getLogger(__name__)
if not _logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# DuckDB connection – one in‑memory instance that lives for the lifetime of the
# Python process. Using ``:memory:`` ensures the database disappears when the
# app restarts (which is fine for a real‑time dashboard).
# ---------------------------------------------------------------------------
_CONN = duckdb.connect(database=':memory:')

# Create a table schema matching the columns emitted by ``pipeline.ingestion``.
_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS flights (
    icao24 VARCHAR,
    callsign VARCHAR,
    origin_country VARCHAR,
    time_position BIGINT,
    last_contact BIGINT,
    longitude DOUBLE,
    latitude DOUBLE,
    baro_altitude DOUBLE,
    on_ground BOOLEAN,
    velocity DOUBLE,
    true_track DOUBLE,
    vertical_rate DOUBLE,
    sensors VARCHAR,
    geo_altitude DOUBLE,
    squawk VARCHAR,
    spi BOOLEAN,
    position_source BIGINT
);
"""
_CONN.execute(_TABLE_SCHEMA)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _to_duckdf(df: pd.DataFrame) -> duckdb.DuckDBPyRelation:
    """Conveniently convert a pandas DataFrame to a DuckDB relation.

    DuckDB can ingest a pandas DataFrame directly via ``from_df`` – this helper
    abstracts that call and makes the intent explicit.
    """
    return duckdb.from_df(df)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def store_flights(df: pd.DataFrame) -> None:
    """Replace the content of the ``flights`` table with a fresh DataFrame.

    The dashboard works in a *replace‑on‑refresh* fashion – each tick we fetch a
    new snapshot from OpenSky and completely overwrite the previous data. This
    is efficient for an in‑memory store and avoids dealing with incremental
    updates.
    """
    # Clear existing rows first.
    _CONN.execute("DELETE FROM flights")
    if df.empty:
        _logger.warning("Attempted to store an empty DataFrame – table cleared.")
        return
    # Register temporary relation and insert.
    rel = _to_duckdf(df)
    _CONN.register("tmp_flights", rel)
    _CONN.execute("INSERT INTO flights SELECT * FROM tmp_flights")
    _CONN.unregister("tmp_flights")
    _logger.info("Stored %s flight records into DuckDB.", len(df))

def _bin_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """Add integer latitude/longitude bin columns (2° × 2° grid)."""
    df = df.copy()
    # Floor division works with negative numbers as expected for geographic bins.
    df["lat_bin"] = (np.floor(df["latitude"] / 2) * 2).astype(int)
    df["lon_bin"] = (np.floor(df["longitude"] / 2) * 2).astype(int)
    return df

def compute_density_grid(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with flight counts per 2°×2° sector.

    The result contains columns ``lat_bin``, ``lon_bin`` and ``flight_count``.
    """
    binned = _bin_coordinates(df)
    grid = (
        binned.groupby(["lat_bin", "lon_bin"], as_index=False)
        .size()
        .rename(columns={"size": "flight_count"})
    )
    return grid

def classify_congestion(flight_count: int) -> str:
    """Map a flight count to a congestion level using ``CONGESTION_THRESHOLDS``."""
    if flight_count > CONGESTION_THRESHOLDS["High"]:
        return "High"
    if flight_count > CONGESTION_THRESHOLDS["Medium"]:
        return "Medium"
    return "Low"

def enrich_grid_with_congestion(grid: pd.DataFrame) -> pd.DataFrame:
    """Add a ``congestion`` column to the density grid DataFrame."""
    grid = grid.copy()
    grid["congestion"] = grid["flight_count"].apply(classify_congestion)
    return grid

def compute_kpis(df: pd.DataFrame) -> Dict[str, any]:
    """Calculate high‑level KPIs needed for the dashboard.

    Returns a dictionary with keys:
    - ``total_flights`` (int)
    - ``avg_speed_mps`` (float)
    - ``avg_speed_knots`` (float)
    - ``altitude_distribution`` (list of tuples ``(bucket, count)``)
    - ``top_countries`` (list of tuples ``(country, count)``)
    """
    total = len(df)
    avg_speed_mps = df["velocity"].mean() if total else 0.0
    # 1 knot = 0.514444 m/s
    avg_speed_knots = avg_speed_mps / 0.514444 if avg_speed_mps else 0.0

    # Altitude buckets (in metres). Adjust ranges to typical commercial flight
    # altitudes for better visualisation.
    bins = [-1, 1000, 5000, 10000, 20000, np.inf]
    labels = ["<1 km", "1‑5 km", "5‑10 km", "10‑20 km", ">20 km"]
    altitude_bins = pd.cut(df["baro_altitude"], bins=bins, labels=labels)
    altitude_distribution = (
        altitude_bins.value_counts()
        .reindex(labels)  # ensure missing categories appear as zero
        .fillna(0)
        .astype(int)
        .items()
    )
    altitude_distribution = list(altitude_distribution)

    top_countries_series = (
        df["origin_country"]
        .value_counts()
        .head(5)
    )
    top_countries = list(top_countries_series.items())

    return {
        "total_flights": total,
        "avg_speed_mps": round(avg_speed_mps, 2),
        "avg_speed_knots": round(avg_speed_knots, 2),
        "altitude_distribution": altitude_distribution,
        "top_countries": top_countries,
    }

def detect_anomalies(df: pd.DataFrame, vertical_rate_threshold: float = 10.0) -> pd.DataFrame:
    """Return rows where ``|vertical_rate|`` exceeds ``threshold`` (m/s).

    The returned DataFrame contains the original columns plus a calculated
    ``abs_vertical_rate`` column for convenience.
    """
    anomalies = df.copy()
    anomalies["abs_vertical_rate"] = anomalies["vertical_rate"].abs()
    anomalies = anomalies[anomalies["abs_vertical_rate"] > vertical_rate_threshold]
    return anomalies

# Exported symbols for ``from pipeline.analytics import *`` convenience.
__all__ = [
    "store_flights",
    "compute_density_grid",
    "enrich_grid_with_congestion",
    "compute_kpis",
    "detect_anomalies",
]
