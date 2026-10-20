"""Dashboard page renderers for CogniCNC — polished edition."""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cognicnc.dashboard.styles import (
    get_status_badge, get_risk_badge, kpi_card, progress_bar,
    machine_card_html, process_flow_html,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(13,17,23,0.6)",
    font=dict(color="#c9d1d9", size=12, family="Segoe UI, sans-serif"),
    xaxis=dict(gridcolor="#21262d", zerolinecolor="#30363d"),
    yaxis=dict(gridcolor="#21262d", zerolinecolor="#30363d"),
    margin=dict(l=40, r=20, t=40, b=40),
    height=320,
)


def _get(key: str):
    return st.session_state.get(key)


def _gauge(value: float, title: str, max_val: float = 1.0,
           thresholds: tuple = (0.35, 0.65), unit: str = "") -> go.Figure:
    """Create a circular gauge indicator."""
    if value < thresholds[0]:
        color = "#3fb950"
    elif value < thresholds[1]:
        color = "#d29922"
    else:
        color = "#f85149"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": unit, "font": {"color": "#e6edf3", "size": 32}},
        title={"text": title, "font": {"color": "#8b949e", "size": 13}},
        gauge={
            "axis": {"range": [0, max_val], "tickcolor": "#30363d", "tickfont": {"color": "#8b949e"}},
            "bar": {"color": color, "thickness": 0.3},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 1,
            "bordercolor": "#30363d",
            "steps": [
                {"range": [0, max_val * thresholds[0]], "color": "rgba(63,185,80,0.1)"},
                {"range": [max_val * thresholds[0], max_val * thresholds[1]], "color": "rgba(210,153,34,0.1)"},
                {"range": [max_val * thresholds[1], max_val], "color": "rgba(248,81,73,0.1)"},
            ],
        },
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#c9d1d9"},
        margin=dict(l=20, r=20, t=40, b=20),
        height=220,
    )
    return fig


# ---------------------------------------------------------------------------
# Page A: Factory Overview
# ---------------------------------------------------------------------------

def render_overview() -> None:
    st.markdown("## 🏭 Factory Control Center")
    st.caption("Real-time view of the virtual CNC production line.")

    factory = _get("factory")
    repo = _get("repo")
    analytics = _get("analytics")
    if factory is None:
        st.warning("Factory not initialized.")
        return

    summary = analytics.compute_factory_summary() if analytics else {}
    active_alerts = repo.get_active_alert_count() if repo else 0

    # --- KPI grid -------------------------------------------------------
    kpi_html = '<div class="kpi-grid">'
    kpi_html += kpi_card("Total Produced", str(summary.get("total_produced", 0)), "blue", "parts manufactured")
    kpi_html += kpi_card("Accepted", str(summary.get("total_accepted", 0)), "green", "pass inspection")
    kpi_html += kpi_card("Factory OEE", f"{summary.get('factory_oee', 0):.1%}", "purple", "overall effectiveness")
    kpi_html += kpi_card("Downtime", f"{summary.get('total_downtime_min', 0):.0f} min", "amber", "cumulative")
    kpi_html += kpi_card("Active Alerts", str(active_alerts), "red" if active_alerts else "blue", "unacknowledged")
    kpi_html += '</div>'
    st.markdown(kpi_html, unsafe_allow_html=True)

    # --- Status summary strip -------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("🟢 Running", str(factory.get_running_count()), "green"), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("🟡 Warning", str(factory.get_warning_count()), "amber"), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("🔴 Fault", str(factory.get_fault_count()), "red"), unsafe_allow_html=True)
    with c4:
        scn = factory.active_scenario_name or "Normal"
        st.markdown(kpi_card("Scenario", scn.replace("_", " ").title(), "purple"), unsafe_allow_html=True)

    # --- Process flow ---------------------------------------------------
    st.markdown('<div class="section-title">Production Line Flow</div>', unsafe_allow_html=True)
    steps = [
        {"id": m.machine_id, "name": m.machine_type.title(), "state": m.state.value}
        for m in factory.line_order
    ]
    st.markdown(process_flow_html(steps), unsafe_allow_html=True)

    # --- Machine grid ---------------------------------------------------
    st.markdown('<div class="section-title">Machine Status</div>', unsafe_allow_html=True)
    grid_html = '<div class="machine-grid">'
    for m in factory.line_order:
        metrics = {
            "RPM": f"{m.current_rpm:.0f}",
            "Torque": f"{m.current_torque:.1f} Nm",
            "Temp": f"{m.process_temp_k - 273.15:.1f} °C",
            "Wear": f"{m.tool_wear_min:.0f} min",
            "Parts": str(m.production_count),
        }
        grid_html += machine_card_html(m.machine_id, m.machine_name, m.state.value, metrics)
    grid_html += '</div>'
    st.markdown(grid_html, unsafe_allow_html=True)

    # --- Recent alerts --------------------------------------------------
    if repo:
        st.markdown('<div class="section-title">Recent Alerts</div>', unsafe_allow_html=True)
        alerts = repo.get_alerts(limit=5)
        if alerts:
            for a in alerts:
                sev_class = a["severity"].lower()
                st.markdown(
                    f'<div class="alert-item {sev_class}">'
                    f'<div><b>{a["machine_id"]}</b> · {a["category"]}  '
                    f'<span class="alert-text">— {a["message"][:70]}</span></div>'
                    f'<div class="alert-time">{a["timestamp"][:19]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No alerts. All systems nominal.")


# ---------------------------------------------------------------------------
# Page B: Machine Monitoring
# ---------------------------------------------------------------------------

def render_monitoring() -> None:
    st.markdown("## 📊 Machine Monitoring")

    factory = _get("factory")
    repo = _get("repo")
    if factory is None:
        st.warning("Factory not initialized.")
        return

    machine_id = st.selectbox(
        "Select Machine",
        options=list(factory.machines.keys()),
        format_func=lambda mid: f"{mid} — {factory.machines[mid].machine_name}",
    )
    machine = factory.machines[machine_id]
    state = machine.state.value

    # --- Header ---------------------------------------------------------
    st.markdown(
        f'<div class="section-card">'
        f'<h3 style="margin:0">{machine_id} — {machine.machine_name}</h3>'
        f'<div style="margin-top:8px">{get_status_badge(state)} '
        f'<span class="scenario-chip">Type: {machine.machine_type.title()}</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # --- Live metrics with progress bars --------------------------------
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Thermal & Mechanical</div>', unsafe_allow_html=True)
        process_c = machine.process_temp_k - 273.15
        air_c = machine.air_temp_k - 273.15
        st.markdown(progress_bar("Process Temperature", process_c, 80, "°C", (0.5, 0.75)), unsafe_allow_html=True)
        st.markdown(progress_bar("Air Temperature", air_c, 60, "°C", (0.5, 0.8)), unsafe_allow_html=True)
        st.markdown(progress_bar("Torque", machine.current_torque, 80, "Nm", (0.5, 0.75)), unsafe_allow_html=True)
        st.markdown(progress_bar("Vibration", machine.vibration, 10, "mm/s", (0.5, 0.75)), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Operational</div>', unsafe_allow_html=True)
        max_rpm = max(machine.base_rpm, 100)
        st.markdown(progress_bar("Spindle Speed", machine.current_rpm, max_rpm * 1.2, "RPM", (0.8, 0.95)), unsafe_allow_html=True)
        st.markdown(progress_bar("Tool Wear", machine.tool_wear_min, 240, "min", (0.6, 0.85)), unsafe_allow_html=True)
        st.markdown(progress_bar("Power", machine.power_kw, 15, "kW", (0.6, 0.85)), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- KPI row --------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("Production", f"{machine.production_count}", "green", "parts"), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Uptime", f"{machine.uptime_min:.0f}", "blue", "minutes"), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Downtime", f"{machine.downtime_min:.0f}", "amber", "minutes"), unsafe_allow_html=True)
    with c4:
        cycle = (120 * machine.base_rpm / max(machine.current_rpm, 1)) if machine.current_rpm > 0 else 0
        st.markdown(kpi_card("Cycle Time", f"{cycle:.1f} s", "purple", "per part"), unsafe_allow_html=True)

    # --- Historical charts ---------------------------------------------
    if repo:
        history = repo.get_telemetry_history(machine_id, limit=80)
        if history:
            df = pd.DataFrame(history)
            st.markdown('<div class="section-title">Telemetry History</div>', unsafe_allow_html=True)

            tab1, tab2, tab3 = st.tabs(["🌡️ Temperature", "⚙️ RPM & Torque", "🔧 Wear & Vibration"])

            with tab1:
                fig = go.Figure(layout=PLOTLY_LAYOUT)
                fig.add_trace(go.Scatter(
                    x=df["timestamp"], y=df["air_temperature_k"] - 273.15,
                    name="Air °C", line=dict(color="#58a6ff", width=2),
                    fill="tozeroy", fillcolor="rgba(88,166,255,0.1)",
                ))
                fig.add_trace(go.Scatter(
                    x=df["timestamp"], y=df["process_temperature_k"] - 273.15,
                    name="Process °C", line=dict(color="#f85149", width=2),
                ))
                fig.update_layout(title="Temperature Trend", yaxis_title="°C")
                st.plotly_chart(fig, use_container_width=True)

            with tab2:
                fig = go.Figure(layout=PLOTLY_LAYOUT)
                fig.add_trace(go.Scatter(
                    x=df["timestamp"], y=df["rotational_speed_rpm"],
                    name="RPM", line=dict(color="#3fb950", width=2),
                    fill="tozeroy", fillcolor="rgba(63,185,80,0.08)",
                ))
                fig.add_trace(go.Scatter(
                    x=df["timestamp"], y=df["torque_nm"],
                    name="Torque Nm", yaxis="y2", line=dict(color="#d29922", width=2),
                ))
                fig.update_layout(
                    title="Spindle Speed & Torque",
                    yaxis=dict(title="RPM"),
                    yaxis2=dict(title="Nm", overlaying="y", side="right"),
                )
                st.plotly_chart(fig, use_container_width=True)

            with tab3:
                fig = go.Figure(layout=PLOTLY_LAYOUT)
                fig.add_trace(go.Scatter(
                    x=df["timestamp"], y=df["tool_wear_min"],
                    name="Tool Wear", line=dict(color="#d29922", width=2),
                    fill="tozeroy", fillcolor="rgba(210,153,34,0.1)",
                ))
                fig.add_trace(go.Scatter(
                    x=df["timestamp"], y=df["vibration_mm_s"],
                    name="Vibration", yaxis="y2", line=dict(color="#bc8cff", width=2),
                ))
                fig.update_layout(
                    title="Tool Wear & Vibration",
                    yaxis=dict(title="min"),
                    yaxis2=dict(title="mm/s", overlaying="y", side="right"),
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No telemetry history yet. Run the simulation to populate charts.")


# ---------------------------------------------------------------------------
# Page C: Predictive Maintenance
# ---------------------------------------------------------------------------

def render_maintenance() -> None:
    st.markdown("## 🔧 Predictive Maintenance")

    factory = _get("factory")
    inference = _get("inference")
    decision_engine = _get("decision_engine")

    if factory is None or inference is None:
        st.warning("Factory or inference service not initialized.")
        return

    machine_id = st.selectbox(
        "Select Machine", options=list(factory.machines.keys()), key="maint_machine",
    )
    machine = factory.machines[machine_id]

    sample = machine._make_sample("now")
    pred = inference.predict(sample)
    decision = decision_engine.evaluate(sample, pred) if decision_engine else None

    # --- Risk gauge + info card ----------------------------------------
    c1, c2 = st.columns([1, 2])
    with c1:
        st.plotly_chart(
            _gauge(pred["failure_probability"], "Failure Probability",
                   max_val=1.0, thresholds=(0.35, 0.65), unit=""),
            use_container_width=True,
        )

    with c2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown(f'<h3 style="margin-top:0">{machine_id} — {machine.machine_name}</h3>', unsafe_allow_html=True)
        if decision:
            st.markdown(f'**Risk Level:** {get_risk_badge(decision.risk_level)}', unsafe_allow_html=True)
            st.markdown(f'**Explanation:** {decision.explanation}')
            st.markdown(f'**Recommended Action:** {decision.recommended_action}')
        st.markdown('</div>', unsafe_allow_html=True)

    # --- Secondary metrics ----------------------------------------------
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(kpi_card("Anomaly Score", f"{pred['anomaly_score']:.3f}", "purple", "lower = more anomalous"), unsafe_allow_html=True)
    with c2:
        anom_val = "⚠️ YES" if pred["is_anomaly"] else "✅ NO"
        anom_color = "red" if pred["is_anomaly"] else "green"
        st.markdown(kpi_card("Anomaly Flag", anom_val, anom_color, "isolation forest"), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Model", pred.get("model_type", "N/A"), "blue", "classifier"), unsafe_allow_html=True)

    # --- Model info card ------------------------------------------------
    st.markdown('<div class="section-title">Model Information</div>', unsafe_allow_html=True)
    meta = inference.failure_model_info
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("Model Type", meta.get("model_type", "N/A"), "blue"), unsafe_allow_html=True)
    if "metrics" in meta:
        m = meta["metrics"]
        with c2:
            st.markdown(kpi_card("F1 Score", f"{m.get('f1', 0):.3f}", "green", "training"), unsafe_allow_html=True)
        with c3:
            st.markdown(kpi_card("Precision", f"{m.get('precision', 0):.3f}", "blue", "training"), unsafe_allow_html=True)
        with c4:
            st.markdown(kpi_card("Recall", f"{m.get('recall', 0):.3f}", "amber", "training"), unsafe_allow_html=True)

    st.caption(
        "⚠️ Predictions are model estimates based on simulated telemetry. "
        "They are not confirmed future failures. The AI4I 2020 dataset is synthetic."
    )

    # --- Features sent to model ----------------------------------------
    st.markdown('<div class="section-title">Features Sent to Model</div>', unsafe_allow_html=True)
    features = pred.get("feature_values", {})
    if features:
        feat_df = pd.DataFrame({
            "Feature": list(features.keys()),
            "Value": [str(v) for v in features.values()],
        })
        st.dataframe(feat_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Page D: Production Analytics
# ---------------------------------------------------------------------------

def render_analytics() -> None:
    st.markdown("## 📈 Production Analytics")

    analytics = _get("analytics")
    repo = _get("repo")
    if analytics is None or repo is None:
        st.warning("Analytics not available.")
        return

    summary = analytics.compute_factory_summary()

    # --- Factory OEE gauge ----------------------------------------------
    c1, c2 = st.columns([1, 2])
    with c1:
        st.plotly_chart(
            _gauge(summary["factory_oee"], "Factory OEE",
                   max_val=1.0, thresholds=(0.4, 0.75), unit=""),
            use_container_width=True,
        )
    with c2:
        kpi_html = '<div class="kpi-grid" style="grid-template-columns:repeat(2,1fr)">'
        kpi_html += kpi_card("Total Produced", str(summary["total_produced"]), "blue")
        kpi_html += kpi_card("Accepted", str(summary["total_accepted"]), "green")
        kpi_html += kpi_card("Rejected", str(summary["total_rejected"]), "red")
        kpi_html += kpi_card("Yield", f"{(summary['total_accepted']/max(summary['total_produced'],1)):.1%}", "purple")
        kpi_html += '</div>'
        st.markdown(kpi_html, unsafe_allow_html=True)

    # --- OEE breakdown bars --------------------------------------------
    st.markdown('<div class="section-title">OEE Components by Machine</div>', unsafe_allow_html=True)
    oee_data = summary.get("machine_oee", {})
    if oee_data:
        oee_df = pd.DataFrame(oee_data).T
        oee_df.index.name = "Machine"
        oee_df.columns = ["Availability", "Performance", "Quality", "OEE"]

        fig = go.Figure(layout=PLOTLY_LAYOUT)
        colors = {"Availability": "#58a6ff", "Performance": "#3fb950", "Quality": "#bc8cff"}
        for col in ["Availability", "Performance", "Quality"]:
            fig.add_trace(go.Bar(
                x=oee_df.index, y=oee_df[col], name=col,
                marker_color=colors[col], text=[f"{v:.0%}" for v in oee_df[col]],
                textposition="outside",
            ))
        fig.add_trace(go.Scatter(
            x=oee_df.index, y=oee_df["OEE"], name="OEE",
            mode="lines+markers", line=dict(color="#f85149", width=3),
            marker=dict(size=10, symbol="diamond"),
        ))
        fig.update_layout(
            barmode="group",
            title="Availability × Performance × Quality = OEE",
            yaxis=dict(title="Score", range=[0, 1.15], tickformat=".0%"),
            legend=dict(orientation="h", y=-0.15),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(oee_df.style.format("{:.2%}"), use_container_width=True)

    # --- Bottleneck -----------------------------------------------------
    st.markdown('<div class="section-title">Bottleneck Analysis</div>', unsafe_allow_html=True)
    bn = analytics.identify_bottleneck()
    if bn.get("bottleneck"):
        st.markdown(
            f'<div class="section-card">'
            f'<b>Bottleneck Machine:</b> <span class="risk-pill risk-warning">{bn["bottleneck"]}</span>  '
            f'<span class="scenario-chip">{bn.get("throughput_parts_per_min", 0)} parts/min</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if "all_throughputs" in bn:
            tp_df = pd.DataFrame({
                "Machine": list(bn["all_throughputs"].keys()),
                "Throughput": list(bn["all_throughputs"].values()),
            }).sort_values("Throughput")
            fig = go.Figure(layout=PLOTLY_LAYOUT)
            fig.add_trace(go.Bar(
                x=tp_df["Throughput"], y=tp_df["Machine"], orientation="h",
                marker=dict(
                    color=tp_df["Throughput"],
                    colorscale=[[0, "#f85149"], [0.5, "#d29922"], [1, "#3fb950"]],
                ),
                text=[f"{v:.3f}" for v in tp_df["Throughput"]],
                textposition="outside",
            ))
            fig.update_layout(
                title="Throughput (parts/min)",
                xaxis_title="Parts per minute",
                height=280,
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(bn.get("reason", "No bottleneck data."))

    st.caption(
        "OEE = Availability × Performance × Quality. "
        "Assumptions: quality uses state heuristic (99% normal, 95% warning, 0% fault); "
        "performance uses ideal cycle times defined per machine type."
    )


# ---------------------------------------------------------------------------
# Page E: Alerts & Events
# ---------------------------------------------------------------------------

def render_alerts() -> None:
    st.markdown("## 🚨 Alerts & Maintenance Events")

    repo = _get("repo")
    factory = _get("factory")
    if repo is None:
        st.warning("Database not initialized.")
        return

    # --- Filter bar -----------------------------------------------------
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        machines = ["All"] + (list(factory.machines.keys()) if factory else [])
        machine_filter = st.selectbox("Machine", machines)
    with c2:
        severity_filter = st.selectbox("Severity", ["All", "CRITICAL", "WARNING", "INFO"])
    with c3:
        limit = st.slider("Max alerts", 10, 200, 50)
    st.markdown('</div>', unsafe_allow_html=True)

    mid = machine_filter if machine_filter != "All" else None
    sev = severity_filter if severity_filter != "All" else None
    alerts = repo.get_alerts(machine_id=mid, severity=sev, limit=limit)

    # --- Summary KPIs ---------------------------------------------------
    critical_count = sum(1 for a in alerts if a["severity"] == "CRITICAL")
    warning_count = sum(1 for a in alerts if a["severity"] == "WARNING")
    unack_count = repo.get_active_alert_count()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("Total", str(len(alerts)), "blue"), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Critical", str(critical_count), "red"), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Warning", str(warning_count), "amber"), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card("Unacknowledged", str(unack_count), "purple"), unsafe_allow_html=True)

    if not alerts:
        st.info("No alerts matching the current filters.")
        return

    # --- Alert list -----------------------------------------------------
    st.markdown('<div class="section-title">Alert Log</div>', unsafe_allow_html=True)
    for a in alerts:
        sev_class = a["severity"].lower()
        ack_icon = "✅" if a["acknowledged"] else "⏳"
        with st.expander(
            f"{ack_icon} [{a['severity']}] {a['machine_id']} · {a['category']}  —  {a['timestamp'][:19]}",
            expanded=False,
        ):
            st.markdown(
                f'<div class="alert-item {sev_class}" style="margin:0">'
                f'<div><b>Message:</b> {a["message"]}<br>'
                f'<b>Action:</b> {a.get("recommended_action", "N/A")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if not a["acknowledged"]:
                if st.button(f"✓ Acknowledge Alert #{a['id']}", key=f"ack_{a['id']}", type="primary"):
                    repo.acknowledge_alert(a["id"])
                    st.rerun()


# ---------------------------------------------------------------------------
# Page F: Simulation & What-If
# ---------------------------------------------------------------------------

def render_simulation() -> None:
    st.markdown("## 🎮 Simulation & What-If Scenarios")

    factory = _get("factory")
    if factory is None:
        st.warning("Factory not initialized.")
        return

    # --- Control panel --------------------------------------------------
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Simulation Controls</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("▶ Start", use_container_width=True, type="primary"):
            factory.start()
            st.session_state.sim_running = True
            st.rerun()
    with c2:
        if st.button("⏸ Pause", use_container_width=True):
            factory.pause()
            st.session_state.sim_running = False
            st.rerun()
    with c3:
        if st.button("🔄 Reset", use_container_width=True):
            factory.reset()
            st.session_state.sim_running = False
            st.rerun()
    with c4:
        speed = st.selectbox("Speed", [1, 5, 10], index=0, key="sim_speed")
        factory.set_speed(speed)

    status_color = "green" if factory.is_running else "amber"
    status_text = "🟢 Running" if factory.is_running else "⏸ Paused"
    scn = factory.active_scenario_name or "Normal"

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(kpi_card("Status", status_text, status_color), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Tick Count", str(factory.tick_count), "blue"), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Active Scenario", scn.replace("_", " ").title(), "purple"), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Run ticks ------------------------------------------------------
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Advance Simulation</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 2])
    with c1:
        n_ticks = st.number_input("Ticks", 1, 100, 10, key="n_ticks")
    with c2:
        st.write("")
        if st.button(f"⚡ Run {n_ticks} Ticks", use_container_width=True, type="primary"):
            _run_ticks(n_ticks)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Scenario injection ---------------------------------------------
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">What-If Scenario Injection</div>', unsafe_allow_html=True)
    st.caption("⚠️ Scenarios inject controlled parameter overrides. Clearly labeled as test inputs.")

    from cognicnc.simulator.scenarios import list_scenarios

    c1, c2, c3 = st.columns(3)
    with c1:
        scenario_name = st.selectbox("Scenario", list_scenarios(), key="scenario_select")
    with c2:
        target = st.multiselect(
            "Target Machines",
            options=list(factory.machines.keys()),
            default=list(factory.machines.keys()),
            key="scenario_targets",
        )
    with c3:
        duration = st.number_input("Duration (0=indefinite)", 0, 100, 0, key="scenario_duration")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔥 Apply Scenario", use_container_width=True, type="primary"):
            factory.apply_scenario(
                scenario_name,
                target_machine_ids=target if target else None,
                duration_ticks=duration,
            )
            st.success(f"Scenario '{scenario_name}' applied to {target or 'ALL'}.")
    with c2:
        if st.button("🔙 Restore Normal Operation", use_container_width=True):
            factory.clear_scenario()
            for m in factory.machines.values():
                if m.state.value == "FAULT":
                    m.reset()
                    m.start()
            st.success("Normal operation restored.")
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Machine state table --------------------------------------------
    st.markdown('<div class="section-title">Live Machine States</div>', unsafe_allow_html=True)
    grid_html = '<div class="machine-grid">'
    for m in factory.line_order:
        metrics = {
            "RPM": f"{m.current_rpm:.0f}",
            "Torque": f"{m.current_torque:.1f} Nm",
            "Process Temp": f"{m.process_temp_k - 273.15:.1f} °C",
            "Tool Wear": f"{m.tool_wear_min:.0f} min",
            "Vibration": f"{m.vibration:.1f} mm/s",
            "Power": f"{m.power_kw:.1f} kW",
            "Production": f"{m.production_count}",
        }
        grid_html += machine_card_html(m.machine_id, m.machine_name, m.state.value, metrics)
    grid_html += '</div>'
    st.markdown(grid_html, unsafe_allow_html=True)


def _run_ticks(n: int) -> None:
    """Advance the simulation by n ticks, storing all data."""
    factory = _get("factory")
    repo = _get("repo")
    inference = _get("inference")
    decision_engine = _get("decision_engine")
    alert_service = _get("alert_service")

    if factory is None:
        return
    if not factory.is_running:
        factory.start()

    for _ in range(n):
        samples = factory.tick()
        if not samples:
            break
        if repo:
            repo.store_telemetry(samples)
        for s in samples:
            if inference and inference.is_loaded:
                pred = inference.predict(s)
                if repo:
                    repo.store_prediction(s.machine_id, s.timestamp, pred)
                if decision_engine and alert_service:
                    decision = decision_engine.evaluate(s, pred)
                    alert_service.process(s, decision)
            if repo:
                repo.store_production(
                    s.timestamp, s.machine_id,
                    parts_produced=1 if s.production_count > 0 else 0,
                    parts_rejected=1 if s.state == "FAULT" else 0,
                    cycle_time_s=s.cycle_time_s,
                )