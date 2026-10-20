"""Phase 2 tests — simulator dynamics, scenarios, inference integration."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cognicnc.config import load_config
from cognicnc.simulator.machine import MachineState, VirtualMachine
from cognicnc.simulator.factory import VirtualFactory
from cognicnc.simulator.scenarios import get_scenario, list_scenarios
from cognicnc.simulator.telemetry import TelemetrySample
from cognicnc.services.inference import InferenceService


# ---------------------------------------------------------------------------
# Telemetry schema
# ---------------------------------------------------------------------------

def test_telemetry_to_model_features():
    sample = TelemetrySample(
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
        downtime_min=0.0,
    )
    features = sample.to_model_features()
    assert set(features.keys()) == {
        "Type", "Air temperature [K]", "Process temperature [K]",
        "Rotational speed [rpm]", "Torque [Nm]", "Tool wear [min]",
    }
    assert features["Type"] == "M"
    assert features["Air temperature [K]"] == 298.0


# ---------------------------------------------------------------------------
# Machine dynamics
# ---------------------------------------------------------------------------

def test_machine_starts_idle():
    cfg = load_config()
    m = VirtualMachine(cfg.machines[0], random_seed=42)
    assert m.state == MachineState.IDLE
    assert m.tool_wear_min == 0.0


def test_machine_running_accumulates_wear():
    cfg = load_config()
    m = VirtualMachine(cfg.machines[0], random_seed=42)
    m.start()
    for _ in range(20):
        m.tick("2025-01-01T08:00:00+00:00", dt_min=1.0)
    assert m.tool_wear_min > 0.0, "Tool wear should accumulate during running."
    assert m.uptime_min > 0.0


def test_machine_idle_no_wear():
    cfg = load_config()
    m = VirtualMachine(cfg.machines[0], random_seed=42)
    # Don't start — stays IDLE
    for _ in range(10):
        m.tick("2025-01-01T08:00:00+00:00", dt_min=1.0)
    assert m.tool_wear_min == 0.0, "Tool wear should not accumulate when idle."


def test_machine_scenario_fault():
    cfg = load_config()
    m = VirtualMachine(cfg.machines[0], random_seed=42)
    m.start()
    m.set_scenario_modifiers({"force_fault": 1.0})
    m.tick("2025-01-01T08:00:00+00:00")
    assert m.state == MachineState.FAULT


def test_machine_reset():
    cfg = load_config()
    m = VirtualMachine(cfg.machines[0], random_seed=42)
    m.start()
    for _ in range(10):
        m.tick("2025-01-01T08:00:00+00:00")
    m.reset()
    assert m.state == MachineState.IDLE
    assert m.tool_wear_min == 0.0
    assert m.production_count == 0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def test_factory_creates_five_machines():
    cfg = load_config()
    factory = VirtualFactory(cfg)
    assert len(factory.machines) == 5
    assert set(factory.machines.keys()) == {"TC-01", "MC-01", "DR-01", "GR-01", "VIS-01"}


def test_factory_tick_returns_five_samples():
    cfg = load_config()
    factory = VirtualFactory(cfg)
    factory.start()
    samples = factory.tick()
    assert len(samples) == 5
    assert all(isinstance(s, TelemetrySample) for s in samples)


def test_factory_not_running_returns_empty():
    cfg = load_config()
    factory = VirtualFactory(cfg)
    samples = factory.tick()
    assert samples == []


def test_factory_scenario_and_clear():
    cfg = load_config()
    factory = VirtualFactory(cfg)
    factory.start()
    factory.apply_scenario("temperature_increase", target_machine_ids=["MC-01"])
    assert factory.active_scenario_name == "temperature_increase"
    factory.clear_scenario()
    assert factory.active_scenario_name is None


def test_factory_reset():
    cfg = load_config()
    factory = VirtualFactory(cfg)
    factory.start()
    for _ in range(5):
        factory.tick()
    factory.reset()
    assert factory.tick_count == 0
    assert factory.total_production == 0
    assert not factory.is_running


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def test_list_scenarios():
    names = list_scenarios()
    assert "normal" in names
    assert "machine_breakdown" in names
    assert len(names) >= 6


def test_get_unknown_scenario_raises():
    with pytest.raises(KeyError, match="Unknown scenario"):
        get_scenario("nonexistent_scenario")


# ---------------------------------------------------------------------------
# Inference integration
# ---------------------------------------------------------------------------

def test_inference_service_loads():
    cfg = load_config()
    pm_dir = cfg.resolved_path("artifacts_pm")
    if not (pm_dir / "failure_pipeline.joblib").is_file():
        pytest.skip("Phase 1 artifacts not found — run train_models.py first.")

    svc = InferenceService(cfg)
    svc.load()
    assert svc.is_loaded


def test_inference_on_simulated_sample():
    cfg = load_config()
    pm_dir = cfg.resolved_path("artifacts_pm")
    if not (pm_dir / "failure_pipeline.joblib").is_file():
        pytest.skip("Phase 1 artifacts not found.")

    svc = InferenceService(cfg)
    svc.load()

    sample = TelemetrySample(
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
        downtime_min=0.0,
    )
    result = svc.predict(sample)
    assert "failure_probability" in result
    assert 0.0 <= result["failure_probability"] <= 1.0
    assert "is_anomaly" in result
    assert isinstance(result["is_anomaly"], bool)
    assert result["feature_values"]["Type"] == "M"