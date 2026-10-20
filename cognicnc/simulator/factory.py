"""Virtual factory managing all CNC machines and the simulation clock.

The factory owns the simulation lifecycle:
* ``start()`` / ``pause()`` / ``reset()`` control the clock.
* ``tick()`` advances all machines by one time step.
* ``apply_scenario()`` injects parameter overrides into target machines.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from cognicnc.config import AppConfig
from cognicnc.simulator.machine import MachineState, VirtualMachine
from cognicnc.simulator.scenarios import Scenario, get_scenario
from cognicnc.simulator.telemetry import TelemetrySample

logger = logging.getLogger("cognicnc.simulator")


class VirtualFactory:
    """Manages the virtual precision-manufacturing line."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.random_seed = config.random_seed

        # Create machines from configuration
        self.machines: Dict[str, VirtualMachine] = {}
        for mcfg in config.machines:
            machine = VirtualMachine(mcfg, random_seed=self.random_seed)
            self.machines[machine.machine_id] = machine

        # Ordered list matching the production line
        self.line_order = sorted(
            self.machines.values(), key=lambda m: m.position
        )

        # Simulation clock
        self._running = False
        self._tick_count = 0
        self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
        self._speed_multiplier = 1
        self._dt_min = float(config.settings.get("simulation", {}).get("tick_seconds", 1.0))

        # Active scenario
        self._active_scenario: Optional[Scenario] = None
        self._scenario_ticks_remaining = 0

        # Aggregate counters
        self.total_production = 0
        self.total_downtime_min = 0.0

        logger.info(
            "VirtualFactory initialized with %d machines: %s",
            len(self.machines),
            ", ".join(self.machines.keys()),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not self._running:
            self._running = True
            for m in self.machines.values():
                if m.state == MachineState.IDLE:
                    m.start()
            logger.info("Factory simulation started (speed=%dx).", self._speed_multiplier)

    def pause(self) -> None:
        if self._running:
            self._running = False
            logger.info("Factory simulation paused at tick %d.", self._tick_count)

    def reset(self) -> None:
        self._running = False
        self._tick_count = 0
        self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
        self._active_scenario = None
        self._scenario_ticks_remaining = 0
        self.total_production = 0
        self.total_downtime_min = 0.0
        for m in self.machines.values():
            m.reset()
        logger.info("Factory simulation reset.")

    def set_speed(self, multiplier: int) -> None:
        if multiplier not in (1, 5, 10):
            raise ValueError("Speed multiplier must be 1, 5, or 10.")
        self._speed_multiplier = multiplier
        logger.info("Simulation speed set to %dx.", multiplier)

    # ------------------------------------------------------------------
    # Scenario control
    # ------------------------------------------------------------------

    def apply_scenario(
        self,
        scenario_name: str,
        target_machine_ids: Optional[List[str]] = None,
        duration_ticks: int = 0,
    ) -> None:
        """Activate a named scenario.

        Parameters
        ----------
        scenario_name : str
            Key from ``scenarios.SCENARIOS``.
        target_machine_ids : list of str, optional
            Override the scenario's default targets. ``None`` = use default.
        duration_ticks : int
            Override the scenario's default duration. 0 = indefinite.
        """
        scenario = get_scenario(scenario_name)
        if target_machine_ids is not None:
            scenario.target_machine_ids = target_machine_ids
        if duration_ticks > 0:
            scenario.duration_ticks = duration_ticks

        self._active_scenario = scenario
        self._scenario_ticks_remaining = scenario.duration_ticks

        for mid, machine in self.machines.items():
            if scenario.applies_to(mid):
                machine.set_scenario_modifiers(scenario.modifiers)
            else:
                machine.clear_scenario_modifiers()

        logger.info(
            "Scenario '%s' activated (targets=%s, duration=%s).",
            scenario.name,
            scenario.target_machine_ids or "ALL",
            scenario.duration_ticks or "indefinite",
        )

    def clear_scenario(self) -> None:
        """Remove all scenario overrides and return to normal operation."""
        self._active_scenario = None
        self._scenario_ticks_remaining = 0
        for m in self.machines.values():
            m.clear_scenario_modifiers()
        logger.info("Scenario cleared — normal operation restored.")

    # ------------------------------------------------------------------
    # Simulation tick
    # ------------------------------------------------------------------

    def tick(self) -> List[TelemetrySample]:
        """Advance the simulation by one time step.

        Returns a list of TelemetrySamples, one per machine.
        """
        if not self._running:
            return []

        self._tick_count += 1
        self._sim_time += timedelta(minutes=self._dt_min * self._speed_multiplier)
        timestamp = self._sim_time.isoformat()

        # Handle scenario duration
        if self._active_scenario and self._scenario_ticks_remaining > 0:
            self._scenario_ticks_remaining -= 1
            if self._scenario_ticks_remaining <= 0:
                self.clear_scenario()

        samples: List[TelemetrySample] = []
        for machine in self.line_order:
            sample = machine.tick(timestamp, dt_min=self._dt_min)
            samples.append(sample)

        # Update aggregates
        self.total_production = sum(m.production_count for m in self.machines.values())
        self.total_downtime_min = sum(m.downtime_min for m in self.machines.values())

        return samples

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def active_scenario_name(self) -> Optional[str]:
        return self._active_scenario.name if self._active_scenario else None

    def get_machine_status(self) -> Dict[str, str]:
        return {mid: m.state.value for mid, m in self.machines.items()}

    def get_running_count(self) -> int:
        return sum(1 for m in self.machines.values() if m.state == MachineState.RUNNING)

    def get_warning_count(self) -> int:
        return sum(1 for m in self.machines.values() if m.state == MachineState.WARNING)

    def get_fault_count(self) -> int:
        return sum(1 for m in self.machines.values() if m.state == MachineState.FAULT)
    
    # Alias for integration tests
FactorySimulator = VirtualFactory