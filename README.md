# SkyNet Airspace Analytics

## 📡 Overview

`skynet-airspace-analytics` is a **real‑time flight‑tracking and airspace‑congestion dashboard** built with Python. It pulls live state vectors from the [OpenSky Network API](https://opensky-network.org) and presents them in an interactive Streamlit UI backed by a fast in‑memory DuckDB analytics engine.

### Key Features
- **Live streaming** of aircraft positions worldwide (refreshes every 15–30 seconds).
- **Geospatial heat‑map** of congestion using 2° × 2° sectors.
- **Rich analytics** – KPIs, altitude distribution, top origin countries, rapid climb/descend detection.
- **Fully containerised** – run locally or in Docker with a single command.
- **Modular pipeline** – clear separation of ingestion, analytics, and configuration.

---

## 🏗️ Architecture (ASCII Diagram)

```
+----------------+      +-------------------+      +---------------------+
|  Streamlit UI  | ---> |   analytics.py    | ---> |   DuckDB (in‑mem)   |
+----------------+      +-------------------+      +---------------------+
        ^                         ^                         ^
        |                         |                         |
        |                 +-----------------+                |
        |                 | ingestion.py    |                |
        |                 +-----------------+                |
        |                         ^                         |
        |                         |                         |
        +-------------------------+-------------------------+
                                   |
                                   v
                           OpenSky Network API
```

---

## 📦 Local Development Setup

### Prerequisites
- **Python 3.11+**
- **Docker** (optional, for containerised execution)
- **Git** (to clone the repo)

### Clone & Install
```bash
git clone https://github.com/ajaypreenal/skynet-airspace-analytics.git
cd skynet-airspace-analytics
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Running the Dashboard
```bash
streamlit run app.py
```
The app will be available at `http://localhost:8501`.

---

## 🐳 Docker Deployment

### Build Image
```bash
docker build -t skynet-airspace-analytics:latest .
```
### Run Container
```bash
docker run -p 8501:8501 skynet-airspace-analytics:latest
```
The Streamlit UI will be exposed on port **8501**.

---

## 📂 Project Structure
```
skynet-airspace-analytics/
├─ README.md                # ← you are here
├─ requirements.txt          # Python dependencies
├─ Dockerfile                # Multi‑stage build for Streamlit
├─ config.py                 # API URLs, bounding boxes, thresholds
├─ pipeline/
│   ├─ __init__.py          # package marker
│   ├─ ingestion.py          # fetch & clean live data
│   └─ analytics.py          # DuckDB storage & KPI calculations
└─ app.py                    # Streamlit front‑end
```

---

## 🤝 Contributing
1. Fork the repository.
2. Create a feature branch (`git checkout -b feat/awesome-feature`).
3. Ensure the code passes `flake8` and the UI works locally.
4. Open a Pull Request.

---

## 📜 License
MIT License – see the `LICENSE` file for details.

---

## 📞 Contact
Created by **Ajay Preenal** – feel free to open an issue for bugs or feature requests.
