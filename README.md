# CogniCNC

**An Industry 4.0 Smart CNC Monitoring, Predictive Maintenance and Explainable AI Platform.**

CogniCNC is a software-based Industry 4.0 smart manufacturing platform combining
virtual CNC telemetry, industrial predictive-maintenance models (trained on the
UCI AI4I 2020 dataset), anomaly detection, explainable AI and production analytics
in an interactive control-center interface.

> This is a research/educational project. It is **not** a validated industrial
> deployment or a fully connected digital twin. Real-sensor integration can later
> be added through the telemetry interface, with appropriate calibration and
> validation required before industrial use.

---

# CogniCNC: Industry 4.0 Smart CNC Monitoring, Predictive Maintenance & Explainable AI Platform

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40-FF4B4B.svg)](https://streamlit.io/)
[![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-1.5-F7931E.svg)](https://scikit-learn.org/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL--Mode-003B57.svg)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/Tests-53%20Passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

> **Live Demo:** [CogniCNC on Streamlit Cloud](https://your-app-name.streamlit.app) *(update after deployment)*

---

## Overview

CogniCNC is an end-to-end **Industry 4.0 Smart Manufacturing Platform** that combines virtual CNC machine telemetry simulation, dual-layer predictive maintenance machine learning, unsupervised anomaly detection, automated industrial decision support, and real-time Overall Equipment Effectiveness (OEE) analytics — all presented through an interactive dark-themed control-room dashboard.

Built as a B.Tech AI & Data Science capstone project, CogniCNC demonstrates how modern AI/ML pipelines can be integrated into smart factory environments for proactive maintenance and production optimization.

---

## System Architecture

┌─────────────────────────────┐     ┌──────────────────────────────┐
│   VIRTUAL FACTORY SIMULATOR │     │   UCI AI4I 2020 DATASET      │
│   5 CNC Stations (Physics)  │     │   10,000 Records, 14 Columns │
└──────────────┬──────────────┘     └──────────────┬───────────────┘
               │ 16-field TelemetrySample          │ 6 ML Features
               ▼                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                  DUAL-LAYER ML INFERENCE ENGINE                  │
│  Layer A: Random Forest Failure Classifier (Supervised)          │
│  Layer C: Isolation Forest Anomaly Detector (Unsupervised)       │
└──────────────────────────────┬───────────────────────────────────┘
                               │ Failure Prob + Anomaly Score
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   RULE-BASED DECISION ENGINE                     │
│  Urgency: LOW → MEDIUM → HIGH → CRITICAL                        │
│  Actions: Monitor / Schedule / Inspect / Emergency Shutdown      │
└──────────────────────────────┬───────────────────────────────────┘
                               │ Action Plans
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   ALERT DEDUPLICATION SERVICE                    │
│  30-second cooldown window per (machine_id, category) pair       │
│  Prevents alarm flooding in continuous telemetry loops            │
└──────────────────────────────┬───────────────────────────────────┘
                               │
          ┌────────────────────┴────────────────────┐
          ▼                                         ▼
┌─────────────────────────┐             ┌──────────────────────────┐
│   SQLITE WAL DATABASE   │             │   STREAMLIT DASHBOARD    │
│  • Telemetry Logs       │             │  • Factory Line Overview │
│  • ML Predictions       │             │  • Live Telemetry Gauges │
│  • Alerts & Events      │             │  • Predictive Maint/XAI  │
│  • Maintenance History  │             │  • OEE & Bottleneck      │
│  • Production Metrics   │             │  • Alert Dispatch Center │
└─────────────────────────┘             │  • What-If Scenarios     │
                                        └──────────────────────────┘




---

## Key Features

### Virtual Factory Simulation
- **5 CNC Manufacturing Stations** with independent physics-based telemetry:
  - `TC-01` CNC Turning Center (Medium variant)
  - `MC-01` CNC Milling Center (Heavy Duty variant)
  - `DR-01` CNC Drilling Station (Light variant)
  - `GR-01` Industrial Grinding Machine (Medium variant)
  - `VIS-01` Automated Visual Inspection Station (Light variant)
- **8 Injectable Scenarios**: Normal, Temperature Increase, High Tool Wear, High Torque, Vibration Increase, RPM Drop, Machine Breakdown, High Demand
- Stateful machine lifecycle: `IDLE → RUNNING → WARNING → FAULT → MAINTENANCE`

### Dual-Layer Machine Learning
- **Layer A — Supervised Failure Classifier**: Random Forest trained on UCI AI4I 2020 dataset with class-weight balancing for the 3.4% minority failure class
- **Layer C — Unsupervised Anomaly Detector**: Isolation Forest (contamination=5%) detecting out-of-distribution operating regimes without labeled examples
- **Explainable Diagnostics**: Feature attribution comparing live sensor values against training dataset percentiles

### Production Analytics
- **OEE Engine**: Real-time Overall Equipment Effectiveness calculation following SEMI E10 / ISO 22400 standards
  - Availability = Uptime / (Uptime + Downtime)
  - Performance = (Parts × Ideal Cycle Time) / Operating Time
  - Quality = Health-state heuristic (99% normal, 95% warning, 0% fault)
- **Bottleneck Detection**: Theory of Constraints identification of the lowest-throughput station

### Industrial Decision & Alert System
- Rule-based urgency classification from ML probabilities
- Intelligent alert deduplication with configurable cooldown windows
- Categorized alerts: Machine Fault, Anomaly, Tool Wear, Overheating, High Torque, Failure Risk

### Interactive Control-Room Dashboard
- Dark industrial theme with gradient KPI cards and animated status badges
- Plotly circular gauges for failure risk and OEE metrics
- Real-time time-series telemetry charts
- Interactive scenario injection sandbox

---

## ML Feature Schema

Models are strictly trained and inferred on the **UCI AI4I 2020** feature space:

| # | Feature | Type | Range |
|:-:|:---|:---:|:---|
| 1 | `Type` | Categorical | L (Low), M (Medium), H (High) |
| 2 | `Air temperature [K]` | Continuous | 295 – 305 K |
| 3 | `Process temperature [K]` | Continuous | 305 – 315 K |
| 4 | `Rotational speed [rpm]` | Continuous | 1168 – 2886 RPM |
| 5 | `Torque [Nm]` | Continuous | 3.8 – 76.6 Nm |
| 6 | `Tool wear [min]` | Continuous | 0 – 253 min |

> **Important**: Simulator-only fields (vibration, power, coolant) are displayed on the dashboard for operator monitoring but are **never fed into the ML pipeline**, preserving feature schema integrity between training and inference.

---

## Quickstart (Local)

### Prerequisites
- Windows 10/11, macOS, or Linux
- Python 3.11 or 3.12
- Git (for cloning)

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/CogniCNC.git
cd CogniCNC

# Create and activate virtual environment
python -m venv smartfactory_env

# Windows PowerShell:
.\smartfactory_env\Scripts\Activate.ps1

# macOS/Linux:
source smartfactory_env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Validate dataset integrity
python scripts/validate_dataset.py

# Train Random Forest + Isolation Forest
python scripts/train_models.py


# Smoke test (verifies all services initialize correctly)
python app.py --smoke-test

# Launch interactive dashboard
streamlit run app.py

# Full test suite (53 tests across 6 phases)
pytest -v

# End-to-end performance benchmark
python scripts/run_e2e_benchmark.py