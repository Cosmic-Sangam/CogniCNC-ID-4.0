"""CogniCNC — Industry 4.0 Smart CNC Control Center.

Launch with:
    streamlit run app.py

For non-interactive use (Phase 0 smoke test), run:
    python app.py --smoke-test
"""

from __future__ import annotations

import base64
import io
import math
import struct
import sys
import wave
from pathlib import Path

import streamlit as st
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cognicnc import __version__
from cognicnc.config import load_config
from cognicnc.logging_config import configure_logging, get_logger
from cognicnc.simulator.factory import VirtualFactory
from cognicnc.services.inference import InferenceService
from cognicnc.services.decision_engine import DecisionEngine
from cognicnc.services.alert_service import AlertService
from cognicnc.database.repository import Repository
from cognicnc.analytics.production import ProductionAnalytics
from cognicnc.dashboard.styles import DARK_THEME_CSS
from cognicnc.dashboard.pages import (
    render_overview,
    render_monitoring,
    render_maintenance,
    render_analytics,
    render_alerts,
    render_simulation,
)

_HAS_AUTOREFRESH = st_autorefresh is not None


# ---------------------------------------------------------------------------
# Alarm Sound System
# ---------------------------------------------------------------------------

def _generate_alarm_wav_b64() -> str:
    """Generate a 3-beep alarm WAV as base64 string."""
    sample_rate = 44100
    duration_beep = 0.25
    duration_gap = 0.15
    freq = 880
    volume = 0.6
    total_samples = int(sample_rate * (duration_beep * 3 + duration_gap * 2))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        t = 0
        for beep in range(3):
            for i in range(int(sample_rate * duration_beep)):
                val = int(volume * 32767 * math.sin(2 * math.pi * freq * t / sample_rate))
                wf.writeframes(struct.pack("<h", val))
                t += 1
            if beep < 2:
                for i in range(int(sample_rate * duration_gap)):
                    wf.writeframes(struct.pack("<h", 0))
                    t += 1
    return base64.b64encode(buf.getvalue()).decode()


@st.cache_data
def get_alarm_audio_tag() -> str:
    b64 = _generate_alarm_wav_b64()
    return f'<audio autoplay loop playsinline><source src="data:audio/wav;base64,{b64}" type="audio/wav"></audio>'


def render_alarm_system(fault_count: int, warning_count: int):
    """Render alarm banner + continuous sound until faults are fixed or toggled off."""

    # ── Sound enable toggle ──
    if "alarm_sound_enabled" not in st.session_state:
        st.session_state.alarm_sound_enabled = False

    with st.sidebar.expander("🔊 Alarm Settings", expanded=False):
        if st.button(
            "🔊 Enable Alarm Sound" if not st.session_state.alarm_sound_enabled
            else "🔇 Disable Alarm Sound",
            key="toggle_alarm_sound",
        ):
            st.session_state.alarm_sound_enabled = not st.session_state.alarm_sound_enabled
            st.rerun()

        if st.session_state.alarm_sound_enabled:
            st.caption("✅ Sound enabled — alarms loop continuously on CRITICAL faults")
        else:
            st.caption("⚠️ Click above to unlock browser audio")

    # ── CRITICAL banner + continuous looping sound ──
    if fault_count > 0:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(90deg, #ff0000, #cc0000);
                color: white;
                padding: 12px 20px;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
                text-align: center;
                animation: alarmPulse 1s infinite;
                margin-bottom: 10px;
            ">
                🚨 CRITICAL FAULT — {fault_count} machine(s) in FAILURE state! 🚨
            </div>
            <style>
            @keyframes alarmPulse {{
                0%, 100% {{ box-shadow: 0 0 5px #ff0000; }}
                50% {{ box-shadow: 0 0 30px #ff0000, 0 0 60px #ff4444; }}
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.alarm_sound_enabled:
            st.markdown(get_alarm_audio_tag(), unsafe_allow_html=True)

    elif warning_count > 0:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(90deg, #ff8c00, #cc7000);
                color: white;
                padding: 10px 16px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                text-align: center;
                margin-bottom: 10px;
            ">
                ⚠️ WARNING — {warning_count} machine(s) showing abnormal readings
            </div>
            """,
            unsafe_allow_html=True,
        )


def check_and_play_alarm() -> None:
    """Check for active fault/warning conditions and trigger alarm system."""
    factory = st.session_state.get("factory")
    if factory is None:
        return

    fault_count = factory.get_fault_count()
    warning_count = factory.get_warning_count()

    render_alarm_system(fault_count, warning_count)

    if fault_count > 0:
        fault_machines = [
            mid for mid, state in factory.get_machine_status().items()
            if state == "FAULT"
        ]
        st.sidebar.error(
            f"🚨 **CRITICAL**\n\n"
            f"{fault_count} machine(s) in FAULT:\n"
            f"{', '.join(fault_machines)}"
        )
    elif warning_count > 0:
        st.sidebar.warning(f"⚠️ {warning_count} machine(s) degraded")


# ---------------------------------------------------------------------------
# Auto-Train Models (for Streamlit Cloud first launch)
# ---------------------------------------------------------------------------

def auto_train_models(config) -> bool:
    """Train models from the AI4I dataset if artifacts are missing.

    Returns True if training succeeded, False otherwise.
    """
    import subprocess
    project_root = Path(__file__).resolve().parent
    train_script = project_root / "scripts" / "train_models.py"

    if not train_script.exists():
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(train_script)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True
        else:
            logger = get_logger("cognicnc")
            logger.error("Auto-train failed: %s", result.stderr[:500])
            return False
    except Exception as e:
        logger = get_logger("cognicnc")
        logger.error("Auto-train exception: %s", e)
        return False


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

@st.cache_resource
def init_services():
    """Load all services once and cache them across Streamlit reruns."""
    configure_logging()
    logger = get_logger("cognicnc")
    cfg = load_config()

    factory = VirtualFactory(cfg)
    repo = Repository(cfg)
    repo.init_db()

    inference = InferenceService(cfg)
    try:
        inference.load()
    except Exception:
        logger.warning("Model artifacts not found on first attempt.")

    # Auto-train if models are missing
    if not inference.is_loaded:
        logger.info("Attempting auto-train from AI4I dataset...")
        success = auto_train_models(cfg)
        if success:
            try:
                inference.load()
                logger.info("Auto-train succeeded. Models loaded.")
            except Exception:
                logger.warning("Auto-train completed but models still not loadable.")
        else:
            logger.warning("Auto-train failed. Running in demo mode.")

    decision_engine = DecisionEngine(cfg)
    alert_service = AlertService(cfg, repo)
    analytics = ProductionAnalytics(cfg, repo)

    logger.info("CogniCNC services initialized (models_loaded=%s).", inference.is_loaded)
    return {
        "factory": factory,
        "repo": repo,
        "inference": inference,
        "decision_engine": decision_engine,
        "alert_service": alert_service,
        "analytics": analytics,
        "config": cfg,
    }


def main() -> None:
    st.set_page_config(
        page_title="CogniCNC",
        page_icon="🏭",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)

    services = init_services()

    for key, val in services.items():
        st.session_state[key] = val
    if "sim_running" not in st.session_state:
        st.session_state.sim_running = False

    # --- Auto-refresh when simulation is running ---
    if st.session_state.sim_running:
        if st_autorefresh is not None:
            st_autorefresh(interval=3000, key="sim_autorefresh")

    # --- Sidebar ---
    st.sidebar.title("🏭 CogniCNC")
    st.sidebar.caption(f"v{__version__} | Industry 4.0 Platform")
    st.sidebar.divider()

    # Model status indicator
    inference = st.session_state.get("inference")
    if inference and inference.is_loaded:
        st.sidebar.success("🧠 ML Models: **Loaded**")
    else:
        st.sidebar.warning("🧠 ML Models: **Demo Mode** (rule-based)")
        if st.sidebar.button("🔄 Train Models Now", use_container_width=True):
            # Fixed: Changed st.sidebar.spinner to st.spinner
            with st.spinner("Training models from AI4I dataset..."):
                success = auto_train_models(st.session_state.config)
                if success:
                    inference.load()
                    st.sidebar.success("✅ Models trained and loaded!")
                    st.rerun()
                else:
                    st.sidebar.error("❌ Training failed. Check logs.")

    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigation",
        [
            "🏭 Factory Overview",
            "📊 Machine Monitoring",
            "🔧 Predictive Maintenance",
            "📈 Production Analytics",
            "🚨 Alerts & Events",
            "🎮 Simulation & What-If",
        ],
        label_visibility="collapsed",
    )

    # --- Alarm ---
    check_and_play_alarm()

    # --- Factory Reset ---
    st.sidebar.divider()
    with st.sidebar.expander("⚠️ Danger Zone", expanded=False):
        st.caption("Erase ALL data and reset machines to initial state.")
        confirm_reset = st.checkbox(
            "I understand — erase everything",
            key="confirm_reset_checkbox",
        )
        if st.button(
            "🔄 Reset Entire Factory",
            type="secondary",
            disabled=not confirm_reset,
            use_container_width=True,
            key="reset_factory_btn",
        ):
            factory = st.session_state.factory
            repo = st.session_state.repo
            alert_service = st.session_state.alert_service

            st.session_state.sim_running = False
            factory.pause()
            factory.full_factory_reset()

            try:
                deleted = repo.reset_all_data()
            except Exception:
                deleted = 0

            if hasattr(alert_service, "_recent_alerts"):
                alert_service._recent_alerts.clear()
            if hasattr(alert_service, "suppressed_count"):
                alert_service.suppressed_count = 0

            keys_to_keep = {
                "factory", "repo", "inference", "decision_engine",
                "alert_service", "analytics", "config", "sim_running",
                "confirm_reset_checkbox", "reset_factory_btn",
            }
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep:
                    del st.session_state[key]

            st.session_state.reset_message = (
                f"✅ Factory reset! All machines → RUNNING. "
                f"Database cleared ({deleted} records)."
            )
            st.rerun()

    if "reset_message" in st.session_state:
        st.sidebar.success(st.session_state.reset_message)
        del st.session_state.reset_message

    st.sidebar.divider()
    st.sidebar.caption(
        "⚠️ Simulated data only.\n"
        "AI4I 2020 dataset (UCI).\n"
        "Not a validated industrial system."
    )

    # --- Page dispatch ---
    if "Overview" in page:
        render_overview()
    elif "Monitoring" in page:
        render_monitoring()
    elif "Maintenance" in page:
        render_maintenance()
    elif "Analytics" in page:
        render_analytics()
    elif "Alerts" in page:
        render_alerts()
    elif "Simulation" in page:
        render_simulation()


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def smoke_test() -> int:
    configure_logging()
    logger = get_logger("cognicnc")
    cfg = load_config()

    logger.info("Smoke test: loading services ...")
    factory = VirtualFactory(cfg)
    repo = Repository(cfg)
    repo.init_db()
    inference = InferenceService(cfg)
    try:
        inference.load()
        logger.info("Smoke test: inference loaded OK.")
    except Exception:
        logger.warning("Smoke test: inference not loaded (demo mode).")

    decision_engine = DecisionEngine(cfg)
    alert_service = AlertService(cfg, repo)
    analytics = ProductionAnalytics(cfg, repo)

    factory.start()
    samples = factory.tick()
    assert len(samples) == 5, f"Expected 5 samples, got {len(samples)}"

    repo.store_telemetry(samples)
    for s in samples:
        pred = inference.predict(s)
        assert hasattr(pred, "failure_probability") or "failure_probability" in pred
        decision = decision_engine.evaluate(s, pred)
        assert decision.risk_level in ("LOW", "WARNING", "CRITICAL")

    summary = analytics.compute_factory_summary()
    assert "factory_oee" in summary

    logger.info("Smoke test PASSED.")
    print("\n[OK] CogniCNC smoke test passed.\n")
    return 0


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        sys.exit(smoke_test())
    else:
        main()