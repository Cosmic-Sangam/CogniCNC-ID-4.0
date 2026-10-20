"""Polished dark industrial CSS theme for the CogniCNC dashboard."""

DARK_THEME_CSS = """
<style>
/* ============================================================
   GLOBAL
   ============================================================ */
[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #0a0e14 0%, #0d1117 50%, #0a0e14 100%);
    color: #c9d1d9;
}
[data-testid="stHeader"] { background: transparent; }

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f1419 0%, #161b22 100%);
    border-right: 1px solid #30363d;
}
[data-testid="stSidebar"] * { color: #c9d1d9 !important; }
[data-testid="stSidebar"] h1 {
    background: linear-gradient(90deg, #58a6ff 0%, #bc8cff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800 !important;
}

h1, h2, h3 { color: #e6edf3 !important; letter-spacing: 0.3px; }
h2 { border-bottom: 1px solid #30363d; padding-bottom: 8px; }

/* ============================================================
   GRADIENT KPI CARDS
   ============================================================ */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin: 10px 0 20px 0;
}
.kpi-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2129 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 18px 20px;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, border-color 0.2s;
}
.kpi-card:hover {
    transform: translateY(-2px);
    border-color: #58a6ff;
}
.kpi-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 3px;
    background: linear-gradient(90deg, var(--accent, #58a6ff), transparent);
}
.kpi-label {
    color: #8b949e;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 1.9rem;
    font-weight: 700;
    color: #e6edf3;
    line-height: 1.1;
}
.kpi-delta {
    font-size: 0.8rem;
    color: #8b949e;
    margin-top: 4px;
}
.kpi-blue   { --accent: #58a6ff; }
.kpi-green  { --accent: #3fb950; }
.kpi-amber  { --accent: #d29922; }
.kpi-red    { --accent: #f85149; }
.kpi-purple { --accent: #bc8cff; }

/* ============================================================
   MACHINE CARDS
   ============================================================ */
.machine-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin: 12px 0;
}
.machine-card {
    background: linear-gradient(145deg, #161b22 0%, #1c2129 100%);
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 14px;
    position: relative;
    transition: all 0.25s;
}
.machine-card:hover {
    border-color: #58a6ff;
    box-shadow: 0 0 20px rgba(88,166,255,0.15);
    transform: translateY(-2px);
}
.machine-card::after {
    content: "";
    position: absolute;
    top: 0; left: 0;
    width: 5px; height: 100%;
    border-radius: 10px 0 0 10px;
}
.machine-card.running::after { background: linear-gradient(180deg, #3fb950, #238636); }
.machine-card.warning::after { background: linear-gradient(180deg, #d29922, #9e6a03); }
.machine-card.fault::after   { background: linear-gradient(180deg, #f85149, #a40e26); animation: pulse 1.5s infinite; }
.machine-card.idle::after    { background: linear-gradient(180deg, #8b949e, #484f58); }
.machine-card.maintenance::after { background: linear-gradient(180deg, #d29922, #9e6a03); }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

.machine-id {
    font-size: 1.1rem;
    font-weight: 700;
    color: #58a6ff;
    margin: 0;
}
.machine-name {
    color: #8b949e;
    font-size: 0.75rem;
    margin: 2px 0 10px 0;
}
.machine-metric-row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    border-top: 1px solid #21262d;
    font-size: 0.8rem;
}
.machine-metric-row:first-of-type { border-top: none; }
.machine-metric-label { color: #8b949e; }
.machine-metric-value { color: #e6edf3; font-weight: 600; }

/* ============================================================
   STATUS BADGES
   ============================================================ */
.status-badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 12px;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin: 4px 0;
}
.status-running     { background: rgba(63,185,80,0.15);  color: #3fb950; border: 1px solid #238636; }
.status-warning     { background: rgba(210,153,34,0.15); color: #d29922; border: 1px solid #9e6a03; }
.status-fault       { background: rgba(248,81,73,0.15);  color: #f85149; border: 1px solid #a40e26; }
.status-idle        { background: rgba(139,148,158,0.15);color: #8b949e; border: 1px solid #484f58; }
.status-maintenance { background: rgba(210,153,34,0.15); color: #d29922; border: 1px solid #9e6a03; }

/* ============================================================
   RISK BADGES
   ============================================================ */
.risk-pill {
    display: inline-block;
    padding: 6px 18px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 0.9rem;
    letter-spacing: 0.5px;
}
.risk-low      { background: rgba(63,185,80,0.2);  color: #3fb950; border: 1px solid #3fb950; }
.risk-warning  { background: rgba(210,153,34,0.2); color: #d29922; border: 1px solid #d29922; }
.risk-critical { background: rgba(248,81,73,0.2);  color: #f85149; border: 1px solid #f85149; animation: pulse 1.5s infinite; }

/* ============================================================
   PROGRESS BARS
   ============================================================ */
.progress-wrap { margin: 8px 0; }
.progress-label {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    color: #8b949e;
    margin-bottom: 4px;
}
.progress-value { color: #e6edf3; font-weight: 600; }
.progress-bar {
    width: 100%;
    height: 8px;
    background: #21262d;
    border-radius: 4px;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.4s;
}
.progress-good     { background: linear-gradient(90deg, #238636, #3fb950); }
.progress-warning  { background: linear-gradient(90deg, #9e6a03, #d29922); }
.progress-critical { background: linear-gradient(90deg, #a40e26, #f85149); }
.progress-info     { background: linear-gradient(90deg, #0969da, #58a6ff); }

/* ============================================================
   PROCESS FLOW
   ============================================================ */
.process-flow {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20px 10px;
    background: linear-gradient(135deg, #161b22 0%, #1c2129 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    margin: 12px 0;
    flex-wrap: wrap;
    gap: 8px;
}
.process-step {
    flex: 1;
    min-width: 110px;
    background: #0d1117;
    border: 2px solid #30363d;
    border-radius: 10px;
    padding: 12px 8px;
    text-align: center;
    position: relative;
    transition: all 0.3s;
}
.process-step.active {
    border-color: #3fb950;
    box-shadow: 0 0 15px rgba(63,185,80,0.3);
}
.process-step.warn {
    border-color: #d29922;
    box-shadow: 0 0 15px rgba(210,153,34,0.3);
}
.process-step.fault {
    border-color: #f85149;
    box-shadow: 0 0 15px rgba(248,81,73,0.4);
    animation: pulse 1.5s infinite;
}
.process-step-id {
    font-weight: 700;
    color: #58a6ff;
    font-size: 0.95rem;
}
.process-step-name {
    color: #8b949e;
    font-size: 0.7rem;
    margin-top: 4px;
}
.process-connector {
    color: #58a6ff;
    font-size: 1.5rem;
    font-weight: 700;
}

/* ============================================================
   SECTION CARDS
   ============================================================ */
.section-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2129 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 18px;
    margin: 10px 0;
}
.section-title {
    color: #58a6ff;
    font-size: 0.95rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid #30363d;
}

/* ============================================================
   ALERT ITEMS
   ============================================================ */
.alert-item {
    background: linear-gradient(90deg, #161b22 0%, #1c2129 100%);
    border-left: 4px solid var(--sev-color, #58a6ff);
    border-radius: 6px;
    padding: 10px 14px;
    margin: 6px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.alert-item.critical { --sev-color: #f85149; }
.alert-item.warning  { --sev-color: #d29922; }
.alert-item.info     { --sev-color: #58a6ff; }
.alert-text { color: #c9d1d9; font-size: 0.85rem; }
.alert-time { color: #8b949e; font-size: 0.75rem; }

/* ============================================================
   SCENARIO CHIP
   ============================================================ */
.scenario-chip {
    display: inline-block;
    padding: 6px 14px;
    border-radius: 16px;
    background: linear-gradient(90deg, rgba(188,140,255,0.15), rgba(88,166,255,0.15));
    border: 1px solid #bc8cff;
    color: #bc8cff;
    font-size: 0.8rem;
    font-weight: 600;
    margin: 4px 0;
}

/* ============================================================
   STREAMLIT COMPONENT OVERRIDES
   ============================================================ */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #161b22 0%, #1c2129 100%);
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 14px 16px;
}
[data-testid="stMetricValue"] { color: #e6edf3 !important; font-size: 1.6rem !important; }
[data-testid="stMetricLabel"] { color: #8b949e !important; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 1px; }

.stButton > button {
    background: linear-gradient(135deg, #21262d 0%, #30363d 100%);
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #0d419d 0%, #1f6feb 100%);
    border-color: #58a6ff;
    color: #ffffff;
    box-shadow: 0 0 15px rgba(88,166,255,0.3);
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0969da 0%, #58a6ff 100%);
    border: none;
    color: #ffffff;
}

[data-testid="stDataFrame"] { border: 1px solid #30363d; border-radius: 8px; }

hr { border-color: #30363d !important; }

/* ============================================================
   TABS
   ============================================================ */
[data-testid="stTabs"] button {
    background: transparent;
    color: #8b949e;
    border: none;
    border-bottom: 2px solid transparent;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #58a6ff;
    border-bottom: 2px solid #58a6ff;
    background: transparent;
}
</style>
"""


# ---------------------------------------------------------------------------
# HTML component helpers
# ---------------------------------------------------------------------------

def get_status_class(state: str) -> str:
    return {
        "RUNNING": "running", "WARNING": "warning", "FAULT": "fault",
        "IDLE": "idle", "MAINTENANCE": "maintenance",
    }.get(state.upper(), "idle")


def get_status_badge(state: str) -> str:
    return f'<span class="status-badge status-{state.lower()}">{state}</span>'


def get_risk_badge(risk: str) -> str:
    return f'<span class="risk-pill risk-{risk.lower()}">{risk}</span>'


def kpi_card(label: str, value: str, color: str = "blue", delta: str = "") -> str:
    """Return HTML for a gradient KPI card."""
    delta_html = f'<div class="kpi-delta">{delta}</div>' if delta else ""
    return (
        f'<div class="kpi-card kpi-{color}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{delta_html}'
        f'</div>'
    )


def progress_bar(label: str, value: float, max_value: float, unit: str = "",
                 thresholds: tuple = (0.5, 0.8)) -> str:
    """Horizontal progress bar with threshold-based color.

    thresholds: (warn_frac, crit_frac) relative to max_value.
    """
    pct = min(100, (value / max_value * 100) if max_value > 0 else 0)
    frac = value / max_value if max_value > 0 else 0
    if frac >= thresholds[1]:
        css = "progress-critical"
    elif frac >= thresholds[0]:
        css = "progress-warning"
    else:
        css = "progress-good"
    return (
        f'<div class="progress-wrap">'
        f'<div class="progress-label">'
        f'<span>{label}</span>'
        f'<span class="progress-value">{value:.1f} {unit}</span>'
        f'</div>'
        f'<div class="progress-bar">'
        f'<div class="progress-fill {css}" style="width:{pct:.1f}%"></div>'
        f'</div>'
        f'</div>'
    )


def machine_card_html(machine_id: str, machine_name: str, state: str,
                      metrics: dict) -> str:
    """Return HTML for a machine status card."""
    rows = ""
    for label, value in metrics.items():
        rows += (
            f'<div class="machine-metric-row">'
            f'<span class="machine-metric-label">{label}</span>'
            f'<span class="machine-metric-value">{value}</span>'
            f'</div>'
        )
    return (
        f'<div class="machine-card {get_status_class(state)}">'
        f'<p class="machine-id">{machine_id}</p>'
        f'<p class="machine-name">{machine_name}</p>'
        f'{get_status_badge(state)}'
        f'<div style="margin-top:10px">{rows}</div>'
        f'</div>'
    )


def process_flow_html(steps: list) -> str:
    """Return HTML for the production line flow.

    steps: list of dicts with keys: id, name, state.
    """
    html = '<div class="process-flow">'
    for i, step in enumerate(steps):
        state = step["state"].upper()
        css = ""
        if state == "RUNNING":
            css = "active"
        elif state == "WARNING":
            css = "warn"
        elif state == "FAULT":
            css = "fault"
        html += (
            f'<div class="process-step {css}">'
            f'<div class="process-step-id">{step["id"]}</div>'
            f'<div class="process-step-name">{step["name"]}</div>'
            f'</div>'
        )
        if i < len(steps) - 1:
            html += '<span class="process-connector">▶</span>'
    html += '</div>'
    return html