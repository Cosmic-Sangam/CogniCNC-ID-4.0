"""Stateful virtual CNC machine model.

Each machine maintains internal state that evolves across simulation
ticks. Telemetry values are generated from physics-inspired heuristics
with bounded noise, NOT from independent random draws.

Key dynamics:
* Tool wear accumulates proportionally to operating time and load.
* Process temperature responds to air temperature and load with
  thermal inertia (exponential moving average).
* RPM fluctuates around the baseline and degrades under fault.
* Torque is inversely related to RPM at roughly constant power,
  with increases under strain.
* Vibration and power are derived quantities (simulator-only).
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Optional

import numpy as np

from cognicnc.simulator.telemetry import TelemetrySample

logger = logging.getLogger("cognicnc.simulator")


class MachineState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WARNING = "WARNING"
    FAULT = "FAULT"
    MAINTENANCE = "MAINTENANCE"


class VirtualMachine:
    """A single virtual CNC machine with stateful telemetry generation."""

    def __init__(self, config: Dict[str, Any], random_seed: int = 42):
        self.machine_id: str = config["id"]
        self.machine_name: str = config["name"]
        self.machine_type: str = config["type"]
        self.model_type: str = config["model_type"]
        self.position: int = config["position_in_line"]

        bl = config["baseline"]
        self.base_rpm: float = float(bl["rpm"])
        self.base_torque: float = float(bl["torque_nm"])
        self.base_wear_rate: float = float(bl["tool_wear_rate_per_min"])
        self.base_air_temp_c: float = float(bl["air_temp_c"])
        self.base_process_temp_c: float = float(bl["process_temp_c"])

        self.rng = np.random.default_rng(random_seed + hash(self.machine_id) % 10000)

        # Internal state
        self.state = MachineState.IDLE
        self.tool_wear_min: float = 0.0
        self.air_temp_k: float = self.base_air_temp_c + 273.15
        self.process_temp_k: float = self.base_process_temp_c + 273.15
        self.current_rpm: float = 0.0
        self.current_torque: float = 0.0
        self.vibration: float = 0.0
        self.power_kw: float = 0.0
        self.production_count: int = 0
        self.uptime_min: float = 0.0
        self.downtime_min: float = 0.0
        self._tick_count: int = 0

        # Scenario modifiers (set by factory when a scenario is active)
        self._scenario_mods: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_scenario_modifiers(self, mods: Dict[str, float]) -> None:
        """Apply scenario-driven parameter overrides.

        Supported keys: ``air_temp_offset``, ``process_temp_offset``,
        ``rpm_factor``, ``torque_factor``, ``wear_rate_factor``,
        ``vibration_factor``, ``force_fault``.
        """
        self._scenario_mods = mods

    def clear_scenario_modifiers(self) -> None:
        self._scenario_mods = {}

    def tick(self, timestamp: str, dt_min: float = 1.0) -> TelemetrySample:
        """Advance the machine state by *dt_min* minutes and return telemetry."""
        self._tick_count += 1

        if self.state == MachineState.MAINTENANCE:
            self.downtime_min += dt_min
            return self._make_sample(timestamp)

        if self.state == MachineState.FAULT:
            self.downtime_min += dt_min
            self._update_fault_telemetry(dt_min)
            return self._make_sample(timestamp)

        # --- RUNNING / IDLE / WARNING dynamics -------------------------
        is_running = self.state in (MachineState.RUNNING, MachineState.WARNING)

        if is_running:
            self.uptime_min += dt_min
            self._update_running_telemetry(dt_min)
        else:
            self.downtime_min += dt_min
            self._update_idle_telemetry(dt_min)

        # State transitions based on thresholds
        self._evaluate_state()

        return self._make_sample(timestamp)

    def start(self) -> None:
        if self.state in (MachineState.IDLE, MachineState.WARNING):
            self.state = MachineState.RUNNING
            logger.info("%s started.", self.machine_id)

    def stop(self) -> None:
        if self.state in (MachineState.RUNNING, MachineState.WARNING):
            self.state = MachineState.IDLE
            logger.info("%s stopped.", self.machine_id)

    def reset(self) -> None:
        self.state = MachineState.IDLE
        self.tool_wear_min = 0.0
        self.air_temp_k = self.base_air_temp_c + 273.15
        self.process_temp_k = self.base_process_temp_c + 273.15
        self.current_rpm = 0.0
        self.current_torque = 0.0
        self.vibration = 0.0
        self.power_kw = 0.0
        self.production_count = 0
        self.uptime_min = 0.0
        self.downtime_min = 0.0
        self._tick_count = 0
        self._scenario_mods = {}
        logger.info("%s reset to initial state.", self.machine_id)

    # ------------------------------------------------------------------
    # Internal dynamics
    # ------------------------------------------------------------------

    def _update_running_telemetry(self, dt: float) -> None:
        """Update telemetry for a running machine."""
        mods = self._scenario_mods

        # Air temperature: slow random walk around baseline
        air_offset = mods.get("air_temp_offset", 0.0)
        target_air = self.base_air_temp_c + 273.15 + air_offset
        self.air_temp_k += (target_air - self.air_temp_k) * 0.05 + self.rng.normal(0, 0.15)

        # Process temperature: responds to load and air temp with lag
        process_offset = mods.get("process_temp_offset", 0.0)
        load_factor = self.current_rpm / max(self.base_rpm, 1.0) if self.base_rpm > 0 else 0
        target_process = (
            self.base_process_temp_c + 273.15
            + load_factor * 8.0
            + (self.air_temp_k - 297.0) * 0.3
            + process_offset
        )
        self.process_temp_k += (target_process - self.process_temp_k) * 0.08 + self.rng.normal(0, 0.2)

        # RPM: fluctuate around baseline, degrade with wear
        rpm_factor = mods.get("rpm_factor", 1.0)
        wear_degradation = max(0.0, 1.0 - self.tool_wear_min / 300.0)
        if self.base_rpm > 0:
            target_rpm = self.base_rpm * rpm_factor * wear_degradation
            self.current_rpm += (target_rpm - self.current_rpm) * 0.1 + self.rng.normal(0, self.base_rpm * 0.01)
            self.current_rpm = max(0.0, self.current_rpm)
        else:
            self.current_rpm = 0.0

        # Torque: roughly inverse to RPM at constant power, plus strain
        torque_factor = mods.get("torque_factor", 1.0)
        if self.base_rpm > 0 and self.current_rpm > 0:
            base_power = self.base_torque * self.base_rpm
            target_torque = (base_power / max(self.current_rpm, 100)) * torque_factor
            self.current_torque += (target_torque - self.current_torque) * 0.1 + self.rng.normal(0, 0.5)
            self.current_torque = max(0.0, self.current_torque)
        else:
            self.current_torque = 0.0

        # Tool wear: accumulates based on rate, load, and scenario
        wear_factor = mods.get("wear_rate_factor", 1.0)
        if self.base_wear_rate > 0:
            wear_increment = self.base_wear_rate * dt * wear_factor * (0.8 + 0.4 * load_factor)
            self.tool_wear_min += wear_increment

        # Vibration (simulator-only): increases with wear and faults
        vib_factor = mods.get("vibration_factor", 1.0)
        base_vib = 1.5 + self.tool_wear_min * 0.02
        self.vibration = max(0.0, base_vib * vib_factor + self.rng.normal(0, 0.3))

        # Power (simulator-only): P = torque * omega
        omega = 2.0 * np.pi * self.current_rpm / 60.0
        self.power_kw = max(0.0, self.current_torque * omega / 1000.0)

        # Production: one part per ~2 minutes at nominal speed
        if self.base_rpm > 0:
            speed_ratio = self.current_rpm / self.base_rpm
            if self.rng.random() < speed_ratio * dt / 2.0:
                self.production_count += 1

    def _update_idle_telemetry(self, dt: float) -> None:
        """Cool-down dynamics when machine is idle."""
        self.air_temp_k += ((self.base_air_temp_c + 273.15) - self.air_temp_k) * 0.02 + self.rng.normal(0, 0.05)
        self.process_temp_k += ((self.base_process_temp_c + 273.15) - self.process_temp_k) * 0.05 + self.rng.normal(0, 0.1)
        self.current_rpm *= 0.8
        self.current_torque *= 0.8
        self.vibration *= 0.9
        self.power_kw = self.current_torque * 2.0 * np.pi * self.current_rpm / 60.0 / 1000.0

    def _update_fault_telemetry(self, dt: float) -> None:
        """Telemetry during a fault state."""
        self.air_temp_k += self.rng.normal(0, 0.3)
        self.process_temp_k += 2.0 + self.rng.normal(0, 0.5)  # overheating
        self.current_rpm = max(0.0, self.current_rpm * 0.5 + self.rng.normal(0, 50))
        self.current_torque = max(0.0, self.current_torque * 1.2 + self.rng.normal(0, 2))
        self.vibration = max(0.0, 8.0 + self.rng.normal(0, 1.5))
        omega = 2.0 * np.pi * self.current_rpm / 60.0
        self.power_kw = max(0.0, self.current_torque * omega / 1000.0)

    def _evaluate_state(self) -> None:
        """Transition between RUNNING / WARNING / FAULT based on thresholds."""
        if self._scenario_mods.get("force_fault", 0) >= 1:
            if self.state != MachineState.FAULT:
                self.state = MachineState.FAULT
                logger.warning("%s forced into FAULT by scenario.", self.machine_id)
            return

        if self.state == MachineState.FAULT:
            return  # Fault persists until manual reset

        # Warning conditions
        warnings = 0
        if self.process_temp_k > 343.0:  # ~70 C
            warnings += 1
        if self.tool_wear_min > 200:
            warnings += 1
        if self.vibration > 6.0:
            warnings += 1
        if self.base_rpm > 0 and self.current_rpm < self.base_rpm * 0.7:
            warnings += 1

        if warnings >= 2:
            if self.state != MachineState.WARNING:
                self.state = MachineState.WARNING
                logger.warning("%s entered WARNING state.", self.machine_id)
        elif warnings == 0 and self.state == MachineState.WARNING:
            self.state = MachineState.RUNNING

    # ------------------------------------------------------------------
    # Sample construction
    # ------------------------------------------------------------------

    def _make_sample(self, timestamp: str) -> TelemetrySample:
        cycle_time = 120.0 if self.base_rpm > 0 else 0.0
        if self.state in (MachineState.RUNNING, MachineState.WARNING) and self.current_rpm > 0:
            cycle_time = 120.0 * (self.base_rpm / max(self.current_rpm, 1.0))

        return TelemetrySample(
            timestamp=timestamp,
            machine_id=self.machine_id,
            machine_name=self.machine_name,
            state=self.state.value,
            model_type=self.model_type,
            air_temperature_k=round(self.air_temp_k, 2),
            process_temperature_k=round(self.process_temp_k, 2),
            rotational_speed_rpm=round(self.current_rpm, 1),
            torque_nm=round(self.current_torque, 2),
            tool_wear_min=round(self.tool_wear_min, 2),
            vibration_mm_s=round(self.vibration, 2),
            power_kw=round(self.power_kw, 2),
            production_count=self.production_count,
            cycle_time_s=round(cycle_time, 1),
            uptime_min=round(self.uptime_min, 2),
            downtime_min=round(self.downtime_min, 2),
        )