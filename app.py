"""Streamlit application for SkyNet Airspace Analytics.

The UI is split into a sidebar (controls) and several dashboard sections:

1️⃣ Live flight map (PyDeck 3‑D scatter plot)
2️⃣ Congestion heat‑map (PyDeck GridLayer)
3️⃣ KPI visualisations (Plotly charts)
4️⃣ Detailed table of the latest flight snapshot

All heavy‑lifting – data fetching, cleaning and analytics – lives in the
``pipeline`` package. The app merely orchestrates calls and displays the
results.
"""

import os
import time
from typing import Tuple, List

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import pydeck as pdk

# Load configuration and pipeline utilities
from config import BOUNDING_BOXES, CONGESTION_THRESHOLDS
from pipeline.ingestion import fetch_flight_states, get_available_regions
from pipeline.analytics import (
    store_flights,
    compute_density_grid,
    enrich_grid_with_congestion,
    compute_kpis,
    detect_anomalies,
)

# ---------------------------------------------------------------------------
# Streamlit page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SkyNet Airspace Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
st.sidebar.title("🛫 Controls")
region = st.sidebar.selectbox("Region", get_available_regions())
auto_refresh = st.sidebar.checkbox("Auto‑refresh (every 30 s)", value=True)
refresh_interval = st.sidebar.slider("Refresh interval (seconds)", min_value=15, max_value=60, value=30, step=5)
min_altitude = st.sidebar.slider("Minimum altitude (m)", min_value=0, max_value=20000, value=0, step=500)

# ---------------------------------------------------------------------------
# Data loading – cached to avoid re‑fetching on every UI interaction
# ---------------------------------------------------------------------------
@st.cache_data(ttl=refresh_interval if auto_refresh else None, show_spinner=False)
def load_data(selected_region: str) -> Tuple[pd.DataFrame, pd.DataFrame, dict, pd.DataFrame]:
    """Fetch raw flight data, store it in DuckDB and return analytics objects.
    Returns a tuple of ``(raw_df, density_grid_df, kpi_dict, anomalies_df)``.
    """
    raw_df = fetch_flight_states(selected_region)
    # Apply altitude filter early to reduce downstream volume
    raw_df = raw_df[raw_df["baro_altitude"] >= min_altitude]
    store_flights(raw_df)
    density_grid = compute_density_grid(raw_df)
    density_grid = enrich_grid_with_congestion(density_grid)
    kpis = compute_kpis(raw_df)
    anomalies = detect_anomalies(raw_df)
    return raw_df, density_grid, kpis, anomalies

# ---------------------------------------------------------------------------
# Trigger data reload (auto‑refresh handled by cache TTL)
# ---------------------------------------------------------------------------
# Auto‑refresh is handled by the cache TTL; no explicit rerun needed.
# The Streamlit script will automatically re‑execute when the cached data expires.

raw_df, density_grid, kpis, anomalies = load_data(region)

# ---------------------------------------------------------------------------
# Dashboard – Metrics summary cards
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("Total Flights", kpis["total_flights"])
col2.metric("Avg Speed (m/s)", kpis["avg_speed_mps"])
col3.metric("Avg Speed (knots)", kpis["avg_speed_knots"])

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 1 – 3D Flight map (PyDeck ScatterplotLayer)
# ---------------------------------------------------------------------------
st.subheader("🗺️ Live Flights Map")
if not raw_df.empty:
    # Map centre – average lat/lon of current data (fallback to 0,0)
    centre_lat = raw_df["latitude"].mean()
    centre_lon = raw_df["longitude"].mean()

    # Colour map based on altitude – low = blue, high = red
    altitude = raw_df["baro_altitude"].fillna(0)
    # Normalise to [0,1] for colour scale
    norm_alt = (altitude - altitude.min()) / (altitude.max() - altitude.min() + 1e-6)
    colors = (norm_alt * 255).astype(int)
    # PyDeck expects RGBA hex integers
    colors_rgba = [int(f"0x{c:02x}{255-c:02x}ff", 16) for c in colors]

    scatter = pdk.Layer(
        "ScatterplotLayer",
        data=raw_df,
        get_position="[longitude, latitude]",
        get_fill_color=colors_rgba,
        get_radius=5000,  # 5 km visual radius
        get_elevation="baro_altitude",
        elevation_scale=0.001,
        pickable=True,
        auto_highlight=True,
    )

    view_state = pdk.ViewState(
        latitude=centre_lat,
        longitude=centre_lon,
        zoom=3,
        pitch=45,
    )

    r = pdk.Deck(layers=[scatter], initial_view_state=view_state, tooltip={"text": "{callsign}\nAlt: {baro_altitude} m"})
    st.pydeck_chart(r)
else:
    st.info("No flight data available for the selected region/filters.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 2 – Congestion heat‑map (GridLayer)
# ---------------------------------------------------------------------------
st.subheader("🔥 Congestion Heat‑Map")
if not density_grid.empty:
    # Use GridLayer where each cell colour encodes congestion level
    # Map colour palette: Low=green, Medium=orange, High=red
    congestion_color = {
        "Low": [0, 255, 0, 80],
        "Medium": [255, 165, 0, 120],
        "High": [255, 0, 0, 180],
    }
    # Build a dataframe suitable for GridLayer
    grid_df = density_grid.copy()
    grid_df["color"] = grid_df["congestion"].apply(lambda c: congestion_color[c])

    grid_layer = pdk.Layer(
        "GridLayer",
        data=grid_df,
        get_position="[lon_bin, lat_bin]",
        cell_size=200000,  # roughly 2° at the equator (in metres)
        get_fill_color="color",
        pickable=True,
        extruded=False,
    )

    view_state = pdk.ViewState(
        latitude=raw_df["latitude"].mean() if not raw_df.empty else 0,
        longitude=raw_df["longitude"].mean() if not raw_df.empty else 0,
        zoom=2,
        pitch=0,
    )

    deck = pdk.Deck(layers=[grid_layer], initial_view_state=view_state, tooltip={"text": "Flights: {flight_count}\nCongestion: {congestion}"})
    st.pydeck_chart(deck)
else:
    st.info("No congestion data to display.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 3 – Plotly analytics charts
# ---------------------------------------------------------------------------
st.subheader("📊 Analytics Charts")
col_a, col_b = st.columns(2)

# Altitude distribution histogram
if not raw_df.empty:
    fig_alt = px.histogram(
        raw_df,
        x="baro_altitude",
        nbins=30,
        title="Altitude Distribution (metres)",
        labels={"baro_altitude": "Altitude (m)"},
    )
    col_a.plotly_chart(fig_alt, use_container_width=True)
else:
    col_a.info("No altitude data.")

# Top origin countries bar chart
if kpis["top_countries"]:
    top_countries_df = pd.DataFrame(kpis["top_countries"], columns=["country", "count"])
    fig_countries = px.bar(
        top_countries_df,
        x="country",
        y="count",
        title="Top 5 Origin Countries",
    )
    col_b.plotly_chart(fig_countries, use_container_width=True)
else:
    col_b.info("No country data.")

# Vertical speed distribution (absolute vertical_rate)
if not raw_df.empty:
    fig_vs = px.histogram(
        raw_df.assign(abs_vr=raw_df["vertical_rate"].abs()),
        x="abs_vr",
        nbins=30,
        title="Vertical Speed Distribution (|m/s|)",
        labels={"abs_vr": "|Vertical Rate| (m/s)"},
    )
    st.plotly_chart(fig_vs, use_container_width=True)
else:
    st.info("No vertical speed data.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 4 – Data table (DuckDB query output)
# ---------------------------------------------------------------------------
st.subheader("🗒️ Flight Data Table")
if not raw_df.empty:
    # Show a trimmed view – limit to 100 rows for performance.
    st.dataframe(raw_df.head(100), use_container_width=True)
else:
    st.info("No flight records to display.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.caption("Data source: OpenSky Network public API – refreshed every {} seconds".format(refresh_interval))
