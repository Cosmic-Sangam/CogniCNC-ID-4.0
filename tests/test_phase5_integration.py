"""
tests/test_phase5_integration.py
---------------------------------
End-to-End Integration & Robustness Test Suite for CogniCNC.
"""

import os
import shutil
import tempfile
import pytest
import numpy as np
import pandas as pd

from cognicnc.config import load_config, AppConfig
from cognicnc.database.connection import get_engine, get_session_factory, reset_engine
from cognicnc.database.repository import Repository as CogniCNCRepository
from cognicnc.simulator.factory import VirtualFactory as FactorySimulator
from cognicnc.simulator.telemetry import TelemetrySample
from cognicnc.simulator.machine import MachineState
from cognicnc.services.inference import InferenceService
from cognicnc.services.decision_engine import DecisionEngine
from cognicnc.services.alert_service import AlertService
from cognicnc.services.mqtt_bridge import MQTTBridge
from cognicnc.analytics.production import ProductionAnalytics


@pytest.fixture(scope="module")
def app_config():
    """Load real application configuration."""
    return load_config()


@pytest.fixture
def temp_db(app_config):
    """Create an isolated temporary SQLite database for test execution."""
    temp_dir = tempfile.mkdtemp()
    
    # Override settings path temporarily for testing
    app_config.settings["paths"]["database"] = temp_dir
    
    repo = CogniCNCRepository(app_config)
    repo.init_db()

    yield repo, app_config

    reset_engine()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_services(app_config, temp_db):
    """Assemble all services against the temporary database."""
    repo, cfg = temp_db
    inference = InferenceService(cfg)
    try:
        inference.load()
    except FileNotFoundError:
        pass  # Handled if artifacts aren't pre-loaded in isolated test runner

    decision = DecisionEngine(cfg)
    alerts = AlertService(cfg, repo)
    analytics = ProductionAnalytics(cfg, repo)
    factory = FactorySimulator(cfg)
    mqtt = MQTTBridge(enabled=False)

    return {
        "repo": repo,
        "inference": inference,
        "decision": decision,
        "alerts": alerts,
        "analytics": analytics,
        "factory": factory,
        "mqtt": mqtt,
        "config": cfg,
    }


# =========================================================================
# TEST CASES
# =========================================================================

def test_full_pipeline_single_tick(test_services):
    """
    1. Verify that a single factory tick processes machines through
       inference, decision logic, and database persistence.
    """
    factory = test_services["factory"]
    inference = test_services["inference"]
    decision = test_services["decision"]
    repo = test_services["repo"]

    factory.start()
    samples = factory.tick()
    assert len(samples) == 5

    repo.store_telemetry(samples)

    for sample in samples:
        if inference.is_loaded:
            pred = inference.predict(sample)
            assert "failure_probability" in pred
            action = decision.evaluate(sample, pred)
            assert action.risk_level in ("LOW", "WARNING", "CRITICAL")


def test_scenario_application_lifecycle(test_services):
    """
    2. Test applying and clearing scenarios on the virtual factory.
    """
    factory = test_services["factory"]
    factory.start()
    
    factory.apply_scenario("temperature_increase", target_machine_ids=["TC-01"], duration_ticks=5)
    assert factory.active_scenario_name == "temperature_increase"

    samples = factory.tick()
    tc_sample = next(s for s in samples if s.machine_id == "TC-01")
    assert tc_sample is not None

    factory.clear_scenario()
    assert factory.active_scenario_name is None


def test_database_multi_table_integrity(test_services):
    """
    3. Validate database consistency across telemetry storage and retrieval.
    """
    repo = test_services["repo"]
    factory = test_services["factory"]
    factory.start()

    for _ in range(5):
        samples = factory.tick()
        repo.store_telemetry(samples)

    history = repo.get_telemetry_history(machine_id="TC-01", limit=10)
    assert len(history) > 0
    assert history[0]["machine_id"] == "TC-01"


def test_production_analytics_summary(test_services):
    """
    4. Verify factory OEE metrics and line summary computation.
    """
    factory = test_services["factory"]
    analytics = test_services["analytics"]
    factory.start()

    for _ in range(10):
        factory.tick()

    summary = analytics.compute_factory_summary()
    assert "factory_oee" in summary
    assert 0.0 <= summary["factory_oee"] <= 1.0


def test_inference_out_of_bounds_resilience(test_services):
    """
    5. Ensure ML inference service gracefully handles extreme sensor values.
    """
    inference = test_services["inference"]
    if not inference.is_loaded:
        pytest.skip("Inference models not loaded")

    extreme_sample = TelemetrySample(
        timestamp="2025-01-01T12:00:00+00:00",
        machine_id="TC-01",
        machine_name="CNC Turning Center",
        state=MachineState.RUNNING,
        model_type="M",
        air_temperature_k=450.0,
        process_temperature_k=500.0,
        rotational_speed_rpm=5000.0,
        torque_nm=300.0,
        tool_wear_min=500.0,
        vibration_mm_s=25.0,
        power_kw=40.0,
        production_count=100,
        cycle_time_s=120.0,
        uptime_min=200.0,
        downtime_min=0.0,
    )

    pred = inference.predict(extreme_sample)
    assert 0.0 <= pred["failure_probability"] <= 1.0


def test_empty_database_analytics_handling(app_config):
    """
    6. Ensure analytics services handle empty database tables safely.
    """
    temp_dir = tempfile.mkdtemp()
    app_config.settings["paths"]["database"] = temp_dir
    
    repo = CogniCNCRepository(app_config)
    repo.init_db()
    analytics = ProductionAnalytics(app_config, repo)

    summary = analytics.compute_factory_summary()
    assert summary is not None

    reset_engine()
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_mqtt_bridge_offline_graceful():
    """
    7. Ensure MQTT bridge operates safely in offline/disabled mode.
    """
    bridge = MQTTBridge(enabled=False)
    assert not bridge.is_connected

    sample = TelemetrySample(
        timestamp="2025-01-01T12:00:00+00:00",
        machine_id="TC-01",
        machine_name="CNC Turning Center",
        state=MachineState.RUNNING,
        model_type="M",
        air_temperature_k=300.0,
        process_temperature_k=310.0,
        rotational_speed_rpm=1500.0,
        torque_nm=40.0,
        tool_wear_min=10.0,
        vibration_mm_s=1.0,
        power_kw=5.0,
        production_count=10,
        cycle_time_s=60.0,
        uptime_min=10.0,
        downtime_min=0.0,
    )
    
    assert bridge.publish_telemetry(sample) is False
    bridge.shutdown()