# pipeline/ingestion.py
"""Data ingestion module for SkyNet Airspace Analytics.

Responsible for fetching live flight state vectors from the OpenSky Network
API, normalising the response into a tidy ``pandas.DataFrame`` and performing
basic cleaning steps required by downstream analytics.

All public functions are deliberately pure – they accept inputs and return a
``DataFrame`` without holding any global mutable state.
"""

import os
import time
import logging
from typing import Optional, Tuple, Dict, Any

import requests
import pandas as pd

from ..config import OPENSKY_API_URL, BOUNDING_BOXES

# Configure module‑level logger
_logger = logging.getLogger(__name__)
if not _logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)

# Columns defined by the OpenSky "states" payload – see the official API
_STATE_COLUMNS = [
    "icao24",
    "callsign",
    "origin_country",
    "time_position",
    "last_contact",
    "longitude",
    "latitude",
    "baro_altitude",
    "on_ground",
    "velocity",
    "true_track",
    "vertical_rate",
    "sensors",
    "geo_altitude",
    "squawk",
    "spi",
    "position_source",
]


def _build_bbox_params(region: Optional[str] = None) -> Dict[str, Any]:
    """Return ``requests`` query parameters for a given region.

    The OpenSky API accepts ``lamin``, ``lamax``, ``lomin`` and ``lomax`` to
    restrict the geographic envelope. ``region`` must be a key from
    :data:`BOUNDING_BOXES`. If ``region`` is ``None`` or not present, the caller
    receives an empty dict – meaning *no* geographic filter (global request).
    """
    if region is None or region not in BOUNDING_BOXES:
        return {}
    min_lon, max_lon, min_lat, max_lat = BOUNDING_BOXES[region]
    return {
        "lamin": min_lat,
        "lamax": max_lat,
        "lomin": min_lon,
        "lomax": max_lon,
    }


def _request_with_backoff(url: str, params: Dict[str, Any], retries: int = 3, backoff_factor: float = 1.5) -> Optional[dict]:
    """Perform a ``GET`` request with exponential back‑off.

    The OpenSky public endpoint is rate‑limited. If we receive a ``429`` we
    pause and retry. After ``retries`` attempts the function returns ``None``
    and logs an error – callers can decide whether to use stale data or abort.
    """
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                # Rate limit – honour ``Retry-After`` if present.
                retry_after = int(response.headers.get("Retry-After", backoff_factor * attempt))
                _logger.warning(
                    "OpenSky API rate limited (attempt %s). Back‑off %s seconds.",
                    attempt,
                    retry_after,
                )
                time.sleep(retry_after)
                continue
            # Any other non‑200 is considered fatal for this call.
            _logger.error(
                "Unexpected response %s from OpenSky API: %s", response.status_code, response.text
            )
            break
        except requests.RequestException as exc:
            _logger.exception("Network error on attempt %s: %s", attempt, exc)
            time.sleep(backoff_factor * attempt)
    return None


def fetch_flight_states(region: Optional[str] = None) -> pd.DataFrame:
    """Fetch live flight state vectors from OpenSky and return a cleaned DataFrame.

    Parameters
    ----------
    region: Optional[str]
        Human‑readable region name (e.g. ``"Europe"``). If ``None`` the request is
        global. The name must exist in :data:`BOUNDING_BOXES`.

    Returns
    -------
    pandas.DataFrame
        Normalised columns matching ``_STATE_COLUMNS``. Rows with missing
        ``latitude`` or ``longitude`` are dropped because they cannot be plotted.
        ``callsign`` values are stripped of surrounding whitespace. Numeric
        columns that are ``None`` are filled with sensible defaults:

        * ``baro_altitude`` → ``0`` (ground level)
        * ``velocity`` → ``0`` (stationary)
        * ``true_track`` → ``0``
        * ``vertical_rate`` → ``0``
    """
    params = _build_bbox_params(region)
    json_payload = _request_with_backoff(OPENSKY_API_URL, params)
    if json_payload is None:
        _logger.error("Failed to retrieve flight data – returning empty DataFrame.")
        return pd.DataFrame(columns=_STATE_COLUMNS)

    states = json_payload.get("states", [])
    # ``states`` is a list of lists; we convert directly to a DataFrame.
    df = pd.DataFrame(states, columns=_STATE_COLUMNS)

    # ----- Cleaning steps -------------------------------------------------
    # 1. Drop rows without geographic coordinates – they cannot be visualised.
    df = df.dropna(subset=["latitude", "longitude"])

    # 2. Normalise string fields.
    if "callsign" in df.columns:
        df["callsign"] = df["callsign"].fillna("").str.strip()

    # 3. Fill missing numeric fields with defaults.
    numeric_defaults = {
        "baro_altitude": 0.0,
        "velocity": 0.0,
        "true_track": 0.0,
        "vertical_rate": 0.0,
    }
    for col, default in numeric_defaults.items():
        if col in df.columns:
            df[col] = df[col].fillna(default).astype(float)

    # Ensure correct dtypes for downstream DuckDB ingestion.
    df = df.astype({
        "icao24": "string",
        "callsign": "string",
        "origin_country": "string",
        "longitude": "float64",
        "latitude": "float64",
        "baro_altitude": "float64",
        "velocity": "float64",
        "true_track": "float64",
        "vertical_rate": "float64",
        "on_ground": "bool",
    })

    _logger.info("Fetched %s flight records (region=%s)", len(df), region or "global")
    return df


def get_available_regions() -> Tuple[str, ...]:
    """Utility to expose region keys for UI selections.

    Returns a tuple ordered alphabetically with ``"Global"`` first – the
    consumer (Streamlit sidebar) can iterate directly.
    """
    regions = tuple(sorted(BOUNDING_BOXES.keys()))
    # Ensure ``Global`` is always the first entry.
    if "Global" in regions:
        regions = ("Global",) + tuple(r for r in regions if r != "Global")
    return regions

# Exported symbols for ``from pipeline.ingestion import *`` convenience.
__all__ = [
    "fetch_flight_states",
    "get_available_regions",
]
