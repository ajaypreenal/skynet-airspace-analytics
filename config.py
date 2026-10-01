# config.py
"""Configuration constants for SkyNet Airspace Analytics.

All values are kept simple and immutable. If you need to override any
parameter at runtime, consider using environment variables or a separate
configuration file.
"""

# OpenSky Network public API endpoint
OPENSKY_API_URL = "https://opensky-network.org/api/states/all"

# Pre‑defined bounding boxes (min_lon, max_lon, min_lat, max_lat)
# Values are in decimal degrees.
BOUNDING_BOXES = {
    "Global": (-180.0, 180.0, -90.0, 90.0),
    "North America": (-170.0, -50.0, 15.0, 80.0),
    "Europe": (-25.0, 45.0, 35.0, 71.0),
    "Asia‑Pacific": (60.0, 180.0, -10.0, 60.0),
}

# Congestion density thresholds (aircraft per 2°×2° sector)
CONGESTION_THRESHOLDS = {
    "High": 50,   # > 50 aircraft -> high congestion
    "Medium": 20, # > 20 aircraft -> medium congestion
    "Low": 0,     # otherwise low
}
