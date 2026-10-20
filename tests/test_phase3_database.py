"""Phase 3 tests — database, decision engine, alerts, analytics."""

from __future__ import annotations

from pathlib import Path

import pytest

from cognicnc.config import load_config
from cognicnc.database.connection import reset_engine
from cognicnc.database.repository import Repository
from cognicnc.services.decision_engine import DecisionEngine, DecisionResult
from cognicnc.services.alert_service import AlertService
from cognicnc.analytics.production import ProductionAnalytics
from cognicnc.simulator.telemetry import TelemetrySample


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_sample(**overrides) -> TelemetrySample:
    defaults = dict(
        timestamp="2025-01-01T08:00:00+00:00",
        machine_id="TC-01",
        machine_name="CNC Turning Center",
        state="RUNNING",
        model_type="M",
        air_temperature_k=298.0,
        process_temperature_k=310.0,
        rotational_speed_rpm=2200.0,
        torque_nm=28.0,
        tool_wear_min=50.0,
        vibration_mm_s=2.0,
        power_kw=5.0,
        production_count=10,
        cycle_time_s=120.0,
        uptime_min=100.0,
        downtime_min=5.0,
    )
    defaults.update(overrides)
    return TelemetrySample(**defaults)


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    cfg = load_config()
    # Override the database path to use a temp directory
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    monkeypatch.setitem(cfg.settings["paths"], "database", str(db_dir))
    reset_engine()
    yield cfg
    reset_engine()


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

def test_init_db(clean_db):
    cfg = clean_db
    repo = Repository(cfg)
    repo.init_db()
    # Should not raise on second call
    repo.init_db()


def test_store_and_query_telemetry(clean_db):
    cfg = clean_db
    repo = Repository(cfg)
    repo.init_db()

    samples = [_make_sample(machine_id="TC-01"), _make_sample(machine_id="MC-01")]
    count = repo.store_telemetry(samples)
    assert count == 2

    history = repo.get_telemetry_history("TC-01")
    assert len(history) == 1
    assert history[0]["machine_id"] == "TC-01"


def test_store_and_query_prediction(clean_db):
    cfg = clean_db
    repo = Repository(cfg)
    repo.init_db()

    pred = {
        "failure_probability": 0.15,
        "failure_prediction": 0,
        "anomaly_score": 0.12,
        "is_anomaly": False,
        "model_type": "RandomForestClassifier",
    }
    repo.store_prediction("TC-01", "2025-01-01T08:00:00+00:00", pred)

    latest = repo.get_latest_prediction("TC-01")
    assert latest is not None
    assert latest["failure_probability"] == 0.15


def test_alert_deduplication(clean_db):
    cfg = clean_db
    repo = Repository(cfg)
    repo.init_db()

    created1 = repo.create_alert(
        timestamp="2025-01-01T08:00:00+00:00",
        machine_id="TC-01",
        severity="WARNING",
        category="OVERHEATING",
        message="Temperature high",
        dedup_window_seconds=300,
    )
    assert created1 is True

    # Same alert within window should be deduplicated
    created2 = repo.create_alert(
        timestamp="2025-01-01T08:00:05+00:00",
        machine_id="TC-01",
        severity="WARNING",
        category="OVERHEATING",
        message="Temperature high",
        dedup_window_seconds=300,
    )
    assert created2 is False

    # Different severity should NOT be deduplicated
    created3 = repo.create_alert(
        timestamp="2025-01-01T08:00:10+00:00",
        machine_id="TC-01",
        severity="CRITICAL",
        category="OVERHEATING",
        message="Temperature critical",
        dedup_window_seconds=300,
    )
    assert created3 is True


def test_alert_query_and_acknowledge(clean_db):
    cfg = clean_db
    repo = Repository(cfg)
    repo.init_db()

    repo.create_alert(
        timestamp="2025-01-01T08:00:00+00:00",
        machine_id="TC-01",
        severity="CRITICAL",
        category="MACHINE_FAULT",
        message="Machine faulted",
    )
    alerts = repo.get_alerts(machine_id="TC-01")
    assert len(alerts) == 1
    assert alerts[0]["acknowledged"] is False

    repo.acknowledge_alert(alerts[0]["id"])
    alerts_after = repo.get_alerts(machine_id="TC-01")
    assert alerts_after[0]["acknowledged"] is True
    assert repo.get_active_alert_count() == 0


# ---------------------------------------------------------------------------
# Decision Engine
# ---------------------------------------------------------------------------

def test_decision_low_risk(clean_db):
    cfg = clean_db
    engine = DecisionEngine(cfg)
    sample = _make_sample()
    pred = {"failure_probability": 0.05, "is_anomaly": False}
    result = engine.evaluate(sample, pred)
    assert result.risk_level == "LOW"
    assert "No action required" in result.recommended_action


def test_decision_warning_risk(clean_db):
    cfg = clean_db
    engine = DecisionEngine(cfg)
    sample = _make_sample(tool_wear_min=190.0)
    pred = {"failure_probability": 0.40, "is_anomaly": False}
    result = engine.evaluate(sample, pred)
    assert result.risk_level == "WARNING"


def test_decision_critical_risk(clean_db):
    cfg = clean_db
    engine = DecisionEngine(cfg)
    sample = _make_sample(state="FAULT", process_temperature_k=350.0)
    pred = {"failure_probability": 0.75, "is_anomaly": True}
    result = engine.evaluate(sample, pred)
    assert result.risk_level == "CRITICAL"
    assert "shutdown" in result.recommended_action.lower() or "emergency" in result.recommended_action.lower()


# ---------------------------------------------------------------------------
# Alert Service
# ---------------------------------------------------------------------------

def test_alert_service_no_alert_for_low_risk(clean_db):
    cfg = clean_db
    repo = Repository(cfg)
    repo.init_db()
    svc = AlertService(cfg, repo)

    sample = _make_sample()
    decision = DecisionResult(
        risk_level="LOW",
        failure_probability=0.05,
        is_anomaly=False,
        explanation="Normal",
        recommended_action="None",
    )
    result = svc.process(sample, decision)
    assert result is None


def test_alert_service_creates_warning_alert(clean_db):
    cfg = clean_db
    repo = Repository(cfg)
    repo.init_db()
    svc = AlertService(cfg, repo)

    sample = _make_sample(tool_wear_min=190.0)
    decision = DecisionResult(
        risk_level="WARNING",
        failure_probability=0.40,
        is_anomaly=False,
        explanation="Tool wear high",
        recommended_action="Plan replacement",
    )
    result = svc.process(sample, decision)
    assert result is not None

    alerts = repo.get_alerts()
    assert len(alerts) >= 1


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def test_oee_computation(clean_db):
    cfg = clean_db
    repo = Repository(cfg)
    repo.init_db()

    # Store some data
    for mid in ["TC-01", "MC-01"]:
        repo.store_telemetry([_make_sample(machine_id=mid, uptime_min=90, downtime_min=10)])
        repo.store_production(
            "2025-01-01T08:00:00+00:00", mid,
            parts_produced=40, parts_rejected=1, cycle_time_s=120.0,
        )

    analytics = ProductionAnalytics(cfg, repo)
    oee = analytics.compute_oee()
    assert "TC-01" in oee
    assert 0.0 <= oee["TC-01"]["oee"] <= 1.0
    assert oee["TC-01"]["availability"] > 0.0


def test_bottleneck_identification(clean_db):
    cfg = clean_db
    repo = Repository(cfg)
    repo.init_db()

    repo.store_telemetry([
        _make_sample(machine_id="TC-01", uptime_min=100),
        _make_sample(machine_id="MC-01", uptime_min=100),
    ])
    repo.store_production("2025-01-01T08:00:00", "TC-01", 50, 0, 120.0)
    repo.store_production("2025-01-01T08:00:00", "MC-01", 10, 0, 150.0)

    analytics = ProductionAnalytics(cfg, repo)
    bn = analytics.identify_bottleneck()
    assert bn["bottleneck"] == "MC-01"  # Lower throughput