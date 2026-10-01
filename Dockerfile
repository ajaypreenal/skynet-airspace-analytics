# Dockerfile for SkyNet Airspace Analytics
# -------------------------------------------------
# Multi‑stage build using Python 3.11 slim image
# -------------------------------------------------
# ---------- Builder Stage ----------
FROM python:3.11-slim AS builder

# Set a deterministic working directory
WORKDIR /app

# Install build dependencies (if any) – minimal for this project
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy only requirements first for caching
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---------- Runtime Stage ----------
FROM python:3.11-slim AS runtime
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY . /app

# Expose Streamlit default port
EXPOSE 8501

# Run Streamlit app
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.enableCORS", "false"]
