# # # """Virtual factory managing all CNC machines and the simulation clock.

# # # The factory owns the simulation lifecycle:
# # # * ``start()`` / ``pause()`` / ``reset()`` control the clock.
# # # * ``tick()`` advances all machines by one time step.
# # # * ``apply_scenario()`` injects parameter overrides into target machines.
# # # * ``full_factory_reset()`` resets everything to a clean demo-ready state.
# # # """

# # # from __future__ import annotations

# # # import logging
# # # from datetime import datetime, timedelta, timezone
# # # from typing import Dict, List, Optional

# # # from cognicnc.config import AppConfig
# # # from cognicnc.simulator.machine import MachineState, VirtualMachine
# # # from cognicnc.simulator.scenarios import Scenario, get_scenario
# # # from cognicnc.simulator.telemetry import TelemetrySample

# # # logger = logging.getLogger("cognicnc.simulator")


# # # class VirtualFactory:
# # #     """Manages the virtual precision-manufacturing line."""

# # #     def __init__(self, config: AppConfig):
# # #         self.config = config
# # #         self.random_seed = config.random_seed

# # #         # Create machines from configuration
# # #         self.machines: Dict[str, VirtualMachine] = {}
# # #         for mcfg in config.machines:
# # #             machine = VirtualMachine(mcfg, random_seed=self.random_seed)
# # #             self.machines[machine.machine_id] = machine

# # #         # Ordered list matching the production line
# # #         self.line_order = sorted(
# # #             self.machines.values(), key=lambda m: m.position
# # #         )

# # #         # Simulation clock
# # #         self._running = False
# # #         self._tick_count = 0
# # #         self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
# # #         self._speed_multiplier = 1
# # #         self._dt_min = float(config.settings.get("simulation", {}).get("tick_seconds", 1.0))

# # #         # Active scenario
# # #         self._active_scenario: Optional[Scenario] = None
# # #         self._scenario_ticks_remaining = 0

# # #         # Aggregate counters
# # #         self.total_production = 0
# # #         self.total_downtime_min = 0.0

# # #         logger.info(
# # #             "VirtualFactory initialized with %d machines: %s",
# # #             len(self.machines),
# # #             ", ".join(self.machines.keys()),
# # #         )

# # #     # ------------------------------------------------------------------
# # #     # Lifecycle
# # #     # ------------------------------------------------------------------

# # #     def start(self) -> None:
# # #         if not self._running:
# # #             self._running = True
# # #             for m in self.machines.values():
# # #                 if m.state == MachineState.IDLE:
# # #                     m.start()
# # #             logger.info("Factory simulation started (speed=%dx).", self._speed_multiplier)

# # #     def pause(self) -> None:
# # #         if self._running:
# # #             self._running = False
# # #             logger.info("Factory simulation paused at tick %d.", self._tick_count)

# # #     def reset(self) -> None:
# # #         self._running = False
# # #         self._tick_count = 0
# # #         self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
# # #         self._active_scenario = None
# # #         self._scenario_ticks_remaining = 0
# # #         self.total_production = 0
# # #         self.total_downtime_min = 0.0
# # #         for m in self.machines.values():
# # #             m.reset()
# # #         logger.info("Factory simulation reset.")

# # #     def full_factory_reset(self) -> None:
# # #         """Complete factory reset for demo restarts.

# # #         Does everything ``reset()`` does, plus:
# # #         - Forces every machine to RUNNING state
# # #         - Clears all scenario modifiers
# # #         - Resets machine-level production counters and tool wear to zero
# # #         - Resets machine-level uptime/downtime to zero
# # #         - Logs the reset event
# # #         """
# # #         # 1. Stop simulation and reset clock
# # #         self._running = False
# # #         self._tick_count = 0
# # #         self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
# # #         self._speed_multiplier = 1

# # #         # 2. Clear all scenarios
# # #         self._active_scenario = None
# # #         self._scenario_ticks_remaining = 0

# # #         # 3. Reset aggregate counters
# # #         self.total_production = 0
# # #         self.total_downtime_min = 0.0

# # #         # 4. Reset every machine to clean nominal state
# # #         for m in self.machines.values():
# # #             # Call the machine's own reset (clears internal state)
# # #             m.reset()

# # #             # Force state to RUNNING (not IDLE)
# # #             m.state = MachineState.RUNNING

# # #             # Clear any lingering scenario modifiers
# # #             m.clear_scenario_modifiers()

# # #             # Zero out production and maintenance counters
# # #             m.production_count = 0
# # #             m.uptime_min = 0.0
# # #             m.downtime_min = 0.0

# # #             # Reset tool wear to zero
# # #             if hasattr(m, "tool_wear_min"):
# # #                 m.tool_wear_min = 0.0

# # #         logger.info(
# # #             "Full factory reset completed: %d machines restored to nominal RUNNING state.",
# # #             len(self.machines),
# # #         )

# # #     def set_speed(self, multiplier: int) -> None:
# # #         if multiplier not in (1, 5, 10):
# # #             raise ValueError("Speed multiplier must be 1, 5, or 10.")
# # #         self._speed_multiplier = multiplier
# # #         logger.info("Simulation speed set to %dx.", multiplier)

# # #     # ------------------------------------------------------------------
# # #     # Scenario control
# # #     # ------------------------------------------------------------------

# # #     def apply_scenario(
# # #         self,
# # #         scenario_name: str,
# # #         target_machine_ids: Optional[List[str]] = None,
# # #         duration_ticks: int = 0,
# # #     ) -> None:
# # #         """Activate a named scenario.

# # #         Parameters
# # #         ----------
# # #         scenario_name : str
# # #             Key from ``scenarios.SCENARIOS``.
# # #         target_machine_ids : list of str, optional
# # #             Override the scenario's default targets. ``None`` = use default.
# # #         duration_ticks : int
# # #             Override the scenario's default duration. 0 = indefinite.
# # #         """
# # #         scenario = get_scenario(scenario_name)
# # #         if target_machine_ids is not None:
# # #             scenario.target_machine_ids = target_machine_ids
# # #         if duration_ticks > 0:
# # #             scenario.duration_ticks = duration_ticks

# # #         self._active_scenario = scenario
# # #         self._scenario_ticks_remaining = scenario.duration_ticks

# # #         for mid, machine in self.machines.items():
# # #             if scenario.applies_to(mid):
# # #                 machine.set_scenario_modifiers(scenario.modifiers)
# # #             else:
# # #                 machine.clear_scenario_modifiers()

# # #         logger.info(
# # #             "Scenario '%s' activated (targets=%s, duration=%s).",
# # #             scenario.name,
# # #             scenario.target_machine_ids or "ALL",
# # #             scenario.duration_ticks or "indefinite",
# # #         )

# # #     def clear_scenario(self) -> None:
# # #         """Remove all scenario overrides and return to normal operation."""
# # #         self._active_scenario = None
# # #         self._scenario_ticks_remaining = 0
# # #         for m in self.machines.values():
# # #             m.clear_scenario_modifiers()
# # #         logger.info("Scenario cleared — normal operation restored.")

# # #     # ------------------------------------------------------------------
# # #     # Simulation tick
# # #     # ------------------------------------------------------------------

# # #     def tick(self) -> List[TelemetrySample]:
# # #         """Advance the simulation by one time step.

# # #         Returns a list of TelemetrySamples, one per machine.
# # #         """
# # #         if not self._running:
# # #             return []

# # #         self._tick_count += 1
# # #         self._sim_time += timedelta(minutes=self._dt_min * self._speed_multiplier)
# # #         timestamp = self._sim_time.isoformat()

# # #         # Handle scenario duration
# # #         if self._active_scenario and self._scenario_ticks_remaining > 0:
# # #             self._scenario_ticks_remaining -= 1
# # #             if self._scenario_ticks_remaining <= 0:
# # #                 self.clear_scenario()

# # #         samples: List[TelemetrySample] = []
# # #         for machine in self.line_order:
# # #             sample = machine.tick(timestamp, dt_min=self._dt_min)
# # #             samples.append(sample)

# # #         # Update aggregates
# # #         self.total_production = sum(m.production_count for m in self.machines.values())
# # #         self.total_downtime_min = sum(m.downtime_min for m in self.machines.values())

# # #         return samples

# # #     # ------------------------------------------------------------------
# # #     # Status
# # #     # ------------------------------------------------------------------

# # #     @property
# # #     def is_running(self) -> bool:
# # #         return self._running

# # #     @property
# # #     def tick_count(self) -> int:
# # #         return self._tick_count

# # #     @property
# # #     def active_scenario_name(self) -> Optional[str]:
# # #         return self._active_scenario.name if self._active_scenario else None

# # #     def get_machine_status(self) -> Dict[str, str]:
# # #         return {mid: m.state.value for mid, m in self.machines.items()}

# # #     def get_running_count(self) -> int:
# # #         return sum(1 for m in self.machines.values() if m.state == MachineState.RUNNING)

# # #     def get_warning_count(self) -> int:
# # #         return sum(1 for m in self.machines.values() if m.state == MachineState.WARNING)

# # #     def get_fault_count(self) -> int:
# # #         return sum(1 for m in self.machines.values() if m.state == MachineState.FAULT)


# # # # Alias for integration tests
# # # FactorySimulator = VirtualFactory

# # """Virtual factory managing all CNC machines and the simulation clock.

# # The factory owns the simulation lifecycle:
# # * ``start()`` / ``pause()`` / ``reset()`` control the clock.
# # * ``tick()`` advances all machines by one time step.
# # * ``apply_scenario()`` injects parameter overrides into target machines.
# # * ``full_factory_reset()`` resets everything to a clean demo-ready state.
# # """

# # from __future__ import annotations

# # import logging
# # from datetime import datetime, timedelta, timezone
# # from typing import Dict, List, Optional

# # from cognicnc.config import AppConfig
# # from cognicnc.simulator.machine import MachineState, VirtualMachine
# # from cognicnc.simulator.scenarios import Scenario, get_scenario
# # from cognicnc.simulator.telemetry import TelemetrySample

# # logger = logging.getLogger("cognicnc.simulator")


# # class VirtualFactory:
# #     """Manages the virtual precision-manufacturing line."""

# #     def __init__(self, config: AppConfig):
# #         self.config = config
# #         self.random_seed = getattr(config, "random_seed", 42)

# #         # Create machines from configuration
# #         self.machines: Dict[str, VirtualMachine] = {}
# #         machines_cfg = getattr(config, "machines", [])
# #         if not machines_cfg and hasattr(config, "simulator"):
# #             machines_cfg = getattr(config.simulator, "machines", [])

# #         for mcfg in machines_cfg:
# #             machine = VirtualMachine(mcfg, random_seed=self.random_seed)
# #             self.machines[machine.machine_id] = machine

# #         # Ordered list matching the production line
# #         self.line_order = sorted(
# #             self.machines.values(), key=lambda m: getattr(m, "position", 0)
# #         )

# #         # Simulation clock
# #         self._running = False
# #         self._tick_count = 0
# #         self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
# #         self._speed_multiplier = 1

# #         tick_sec = 1.0
# #         if hasattr(config, "settings") and isinstance(config.settings, dict):
# #             tick_sec = float(config.settings.get("simulation", {}).get("tick_seconds", 1.0))
# #         self._dt_min = tick_sec

# #         # Active scenario
# #         self._active_scenario: Optional[Scenario] = None
# #         self._scenario_ticks_remaining = 0

# #         # Aggregate counters
# #         self.total_production = 0
# #         self.total_downtime_min = 0.0

# #         logger.info(
# #             "VirtualFactory initialized with %d machines: %s",
# #             len(self.machines),
# #             ", ".join(self.machines.keys()),
# #         )

# #     # ------------------------------------------------------------------
# #     # Lifecycle
# #     # ------------------------------------------------------------------

# #     def start(self) -> None:
# #         """Start simulation clock and switch IDLE machines to RUNNING."""
# #         self._running = True
# #         for m in self.machines.values():
# #             if m.state != MachineState.FAULT:
# #                 if hasattr(m, "start") and callable(getattr(m, "start")):
# #                     m.start()
# #                 else:
# #                     m.state = MachineState.RUNNING
# #         logger.info("Factory simulation started (speed=%dx).", self._speed_multiplier)

# #     def pause(self) -> None:
# #         """Pause simulation clock and update non-fault machines to IDLE."""
# #         self._running = False
# #         for m in self.machines.values():
# #             if m.state != MachineState.FAULT:
# #                 if hasattr(m, "pause") and callable(getattr(m, "pause")):
# #                     m.pause()
# #                 else:
# #                     m.state = MachineState.IDLE
# #         logger.info("Factory simulation paused at tick %d.", self._tick_count)

# #     def reset(self) -> None:
# #         """Reset factory simulation state and return machines to IDLE."""
# #         self._running = False
# #         self._tick_count = 0
# #         self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
# #         self._active_scenario = None
# #         self._scenario_ticks_remaining = 0
# #         self.total_production = 0
# #         self.total_downtime_min = 0.0
# #         for m in self.machines.values():
# #             m.reset()
# #             m.state = MachineState.IDLE
# #         logger.info("Factory simulation reset.")

# #     def full_factory_reset(self) -> None:
# #         """Complete factory reset for demo restarts."""
# #         self._running = False
# #         self._tick_count = 0
# #         self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
# #         self._speed_multiplier = 1

# #         self._active_scenario = None
# #         self._scenario_ticks_remaining = 0

# #         self.total_production = 0
# #         self.total_downtime_min = 0.0

# #         for m in self.machines.values():
# #             m.reset()
# #             # Set to IDLE because simulation clock is paused on reset
# #             m.state = MachineState.IDLE

# #             if hasattr(m, "clear_scenario_modifiers"):
# #                 m.clear_scenario_modifiers()

# #             m.production_count = 0
# #             m.uptime_min = 0.0
# #             m.downtime_min = 0.0

# #             if hasattr(m, "tool_wear_min"):
# #                 m.tool_wear_min = 0.0

# #         logger.info(
# #             "Full factory reset completed: %d machines restored to nominal IDLE state.",
# #             len(self.machines),
# #         )

# #     def set_speed(self, multiplier: int) -> None:
# #         if multiplier not in (1, 5, 10):
# #             raise ValueError("Speed multiplier must be 1, 5, or 10.")
# #         self._speed_multiplier = multiplier
# #         logger.info("Simulation speed set to %dx.", multiplier)

# #     # ------------------------------------------------------------------
# #     # Scenario control
# #     # ------------------------------------------------------------------

# #     def apply_scenario(
# #         self,
# #         scenario_name: str,
# #         target_machine_ids: Optional[List[str]] = None,
# #         duration_ticks: int = 0,
# #     ) -> None:
# #         """Activate a named scenario."""
# #         scenario = get_scenario(scenario_name)
# #         if target_machine_ids is not None:
# #             scenario.target_machine_ids = target_machine_ids
# #         if duration_ticks > 0:
# #             scenario.duration_ticks = duration_ticks

# #         self._active_scenario = scenario
# #         self._scenario_ticks_remaining = scenario.duration_ticks

# #         for mid, machine in self.machines.items():
# #             if scenario.applies_to(mid):
# #                 if hasattr(machine, "set_scenario_modifiers"):
# #                     machine.set_scenario_modifiers(scenario.modifiers)
# #             else:
# #                 if hasattr(machine, "clear_scenario_modifiers"):
# #                     machine.clear_scenario_modifiers()

# #         logger.info(
# #             "Scenario '%s' activated (targets=%s, duration=%s).",
# #             scenario.name,
# #             scenario.target_machine_ids or "ALL",
# #             scenario.duration_ticks or "indefinite",
# #         )

# #     def clear_scenario(self) -> None:
# #         """Remove all scenario overrides and return to normal operation."""
# #         self._active_scenario = None
# #         self._scenario_ticks_remaining = 0
# #         for m in self.machines.values():
# #             if hasattr(m, "clear_scenario_modifiers"):
# #                 m.clear_scenario_modifiers()
# #         logger.info("Scenario cleared — normal operation restored.")

# #     # ------------------------------------------------------------------
# #     # Simulation tick
# #     # ------------------------------------------------------------------

# #     def tick(self, force: bool = False) -> List[TelemetrySample]:
# #         """Advance the simulation by one time step.

# #         Parameters
# #         ----------
# #         force : bool, default False
# #             If True, allows stepping even when simulation clock is paused
# #             (e.g., for manual 'Run N Ticks' execution).
# #         """
# #         if not self._running and not force:
# #             return []

# #         self._tick_count += 1
# #         self._sim_time += timedelta(minutes=self._dt_min * self._speed_multiplier)
# #         timestamp = self._sim_time.isoformat()

# #         # Handle scenario duration
# #         if self._active_scenario and self._scenario_ticks_remaining > 0:
# #             self._scenario_ticks_remaining -= 1
# #             if self._scenario_ticks_remaining <= 0:
# #                 self.clear_scenario()

# #         samples: List[TelemetrySample] = []
# #         for machine in self.line_order:
# #             # If stepping while paused, temporarily ensure running state for sample generation
# #             sample = machine.tick(timestamp, dt_min=self._dt_min)
# #             samples.append(sample)

# #         # Update aggregates
# #         self.total_production = sum(getattr(m, "production_count", 0) for m in self.machines.values())
# #         self.total_downtime_min = sum(getattr(m, "downtime_min", 0.0) for m in self.machines.values())

# #         return samples

# #     # ------------------------------------------------------------------
# #     # Status
# #     # ------------------------------------------------------------------

# #     @property
# #     def is_running(self) -> bool:
# #         return self._running

# #     @property
# #     def tick_count(self) -> int:
# #         return self._tick_count

# #     @property
# #     def active_scenario_name(self) -> Optional[str]:
# #         return self._active_scenario.name if self._active_scenario else None

# #     def get_machine_status(self) -> Dict[str, str]:
# #         return {
# #             mid: (m.state.value if hasattr(m.state, "value") else str(m.state))
# #             for mid, m in self.machines.items()
# #         }

# #     def get_running_count(self) -> int:
# #         return sum(
# #             1 for m in self.machines.values()
# #             if (m.state.value if hasattr(m.state, "value") else str(m.state)) == "RUNNING"
# #         )

# #     def get_warning_count(self) -> int:
# #         return sum(
# #             1 for m in self.machines.values()
# #             if (m.state.value if hasattr(m.state, "value") else str(m.state)) == "WARNING"
# #         )

# #     def get_fault_count(self) -> int:
# #         return sum(
# #             1 for m in self.machines.values()
# #             if (m.state.value if hasattr(m.state, "value") else str(m.state)) == "FAULT"
# #         )


# # # Alias for integration tests
# # FactorySimulator = VirtualFactory





# """Virtual factory managing all CNC machines and the simulation clock.

# The factory owns the simulation lifecycle:
# * ``start()`` / ``pause()`` / ``reset()`` control the clock.
# * ``tick()`` advances all machines by one time step.
# * ``apply_scenario()`` injects parameter overrides into target machines.
# * ``full_factory_reset()`` resets everything to a clean demo-ready state.
# """

# from __future__ import annotations

# import logging
# from datetime import datetime, timedelta, timezone
# from typing import Dict, List, Optional

# from cognicnc.config import AppConfig
# from cognicnc.simulator.machine import MachineState, VirtualMachine
# from cognicnc.simulator.scenarios import Scenario, get_scenario
# from cognicnc.simulator.telemetry import TelemetrySample

# logger = logging.getLogger("cognicnc.simulator")


# class VirtualFactory:
#     """Manages the virtual precision-manufacturing line."""

#     def __init__(self, config: AppConfig):
#         self.config = config
#         self.random_seed = getattr(config, "random_seed", 42)

#         # Create machines from configuration
#         self.machines: Dict[str, VirtualMachine] = {}
#         machines_cfg = getattr(config, "machines", [])
#         if not machines_cfg and hasattr(config, "simulator"):
#             machines_cfg = getattr(config.simulator, "machines", [])

#         for mcfg in machines_cfg:
#             machine = VirtualMachine(mcfg, random_seed=self.random_seed)
#             self.machines[machine.machine_id] = machine

#         # Ordered list matching the production line
#         self.line_order = sorted(
#             self.machines.values(), key=lambda m: getattr(m, "position", 0)
#         )

#         # Simulation clock
#         self._running = False
#         self._tick_count = 0
#         self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
#         self._speed_multiplier = 1

#         tick_sec = 1.0
#         if hasattr(config, "settings") and isinstance(config.settings, dict):
#             tick_sec = float(config.settings.get("simulation", {}).get("tick_seconds", 1.0))
#         self._dt_min = tick_sec

#         # Active scenario
#         self._active_scenario: Optional[Scenario] = None
#         self._scenario_ticks_remaining = 0

#         # Aggregate counters
#         self.total_production = 0
#         self.total_downtime_min = 0.0

#         logger.info(
#             "VirtualFactory initialized with %d machines: %s",
#             len(self.machines),
#             ", ".join(self.machines.keys()),
#         )

#     # ------------------------------------------------------------------
#     # Lifecycle
#     # ------------------------------------------------------------------

#     def start(self) -> None:
#         """Start simulation clock and switch IDLE machines to RUNNING."""
#         self._running = True
#         for m in self.machines.values():
#             if str(getattr(m.state, "value", m.state)).upper() != "FAULT":
#                 if hasattr(m, "start") and callable(getattr(m, "start")):
#                     m.start()
#                 else:
#                     m.state = MachineState.RUNNING
#         logger.info("Factory simulation started (speed=%dx).", self._speed_multiplier)

#     def pause(self) -> None:
#         """Pause simulation clock and update non-fault machines to IDLE."""
#         self._running = False
#         for m in self.machines.values():
#             if str(getattr(m.state, "value", m.state)).upper() != "FAULT":
#                 if hasattr(m, "pause") and callable(getattr(m, "pause")):
#                     m.pause()
#                 else:
#                     m.state = MachineState.IDLE
#         logger.info("Factory simulation paused at tick %d.", self._tick_count)

#     def reset(self) -> None:
#         """Reset factory simulation state and return machines to IDLE."""
#         self._running = False
#         self._tick_count = 0
#         self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
#         self._active_scenario = None
#         self._scenario_ticks_remaining = 0
#         self.total_production = 0
#         self.total_downtime_min = 0.0
#         for m in self.machines.values():
#             m.reset()
#             m.state = MachineState.IDLE
#         logger.info("Factory simulation reset.")

#     def full_factory_reset(self) -> None:
#         """Complete factory reset for demo restarts."""
#         self._running = False
#         self._tick_count = 0
#         self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
#         self._speed_multiplier = 1

#         self._active_scenario = None
#         self._scenario_ticks_remaining = 0

#         self.total_production = 0
#         self.total_downtime_min = 0.0

#         for m in self.machines.values():
#             m.reset()
#             # Set to IDLE because simulation clock is paused on reset
#             m.state = MachineState.IDLE

#             if hasattr(m, "clear_scenario_modifiers"):
#                 m.clear_scenario_modifiers()

#             m.production_count = 0
#             m.uptime_min = 0.0
#             m.downtime_min = 0.0

#             if hasattr(m, "tool_wear_min"):
#                 m.tool_wear_min = 0.0

#         logger.info(
#             "Full factory reset completed: %d machines restored to nominal IDLE state.",
#             len(self.machines),
#         )

#     def set_speed(self, multiplier: int) -> None:
#         if multiplier not in (1, 5, 10):
#             raise ValueError("Speed multiplier must be 1, 5, or 10.")
#         self._speed_multiplier = multiplier
#         logger.info("Simulation speed set to %dx.", multiplier)

#     # ------------------------------------------------------------------
#     # Scenario control
#     # ------------------------------------------------------------------

#     def apply_scenario(
#         self,
#         scenario_name: str,
#         target_machine_ids: Optional[List[str]] = None,
#         duration_ticks: int = 0,
#     ) -> None:
#         """Activate a named scenario."""
#         scenario = get_scenario(scenario_name)
#         if target_machine_ids is not None:
#             scenario.target_machine_ids = target_machine_ids
#         if duration_ticks > 0:
#             scenario.duration_ticks = duration_ticks

#         self._active_scenario = scenario
#         self._scenario_ticks_remaining = scenario.duration_ticks

#         for mid, machine in self.machines.items():
#             if scenario.applies_to(mid):
#                 if hasattr(machine, "set_scenario_modifiers"):
#                     machine.set_scenario_modifiers(scenario.modifiers)
#             else:
#                 if hasattr(machine, "clear_scenario_modifiers"):
#                     machine.clear_scenario_modifiers()

#         logger.info(
#             "Scenario '%s' activated (targets=%s, duration=%s).",
#             scenario.name,
#             scenario.target_machine_ids or "ALL",
#             scenario.duration_ticks or "indefinite",
#         )

#     def clear_scenario(self) -> None:
#         """Remove all scenario overrides and return to normal operation."""
#         self._active_scenario = None
#         self._scenario_ticks_remaining = 0
#         for m in self.machines.values():
#             if hasattr(m, "clear_scenario_modifiers"):
#                 m.clear_scenario_modifiers()
#         logger.info("Scenario cleared — normal operation restored.")

#     # ------------------------------------------------------------------
#     # Simulation tick
#     # ------------------------------------------------------------------

#     def tick(self, force: bool = False) -> List[TelemetrySample]:
#         """Advance the simulation by one time step.

#         Parameters
#         ----------
#         force : bool, default False
#             If True, allows stepping even when simulation clock is paused
#             (e.g., for manual 'Run N Ticks' execution).
#         """
#         if not self._running and not force:
#             return []

#         self._tick_count += 1
#         self._sim_time += timedelta(minutes=self._dt_min * self._speed_multiplier)
#         timestamp = self._sim_time.isoformat()

#         # Handle scenario duration
#         if self._active_scenario and self._scenario_ticks_remaining > 0:
#             self._scenario_ticks_remaining -= 1
#             if self._scenario_ticks_remaining <= 0:
#                 self.clear_scenario()

#         samples: List[TelemetrySample] = []
#         for machine in self.line_order:
#             sample = machine.tick(timestamp, dt_min=self._dt_min)
#             samples.append(sample)

#         # Update aggregates
#         self.total_production = sum(getattr(m, "production_count", 0) for m in self.machines.values())
#         self.total_downtime_min = sum(getattr(m, "downtime_min", 0.0) for m in self.machines.values())

#         return samples

#     # ------------------------------------------------------------------
#     # Status & Warning Calculation
#     # ------------------------------------------------------------------

#     @property
#     def is_running(self) -> bool:
#         return self._running

#     @property
#     def tick_count(self) -> int:
#         return self._tick_count

#     @property
#     def active_scenario_name(self) -> Optional[str]:
#         return self._active_scenario.name if self._active_scenario else None

#     def _is_machine_in_warning(self, m: VirtualMachine) -> bool:
#         """Check if a machine state or its operational metrics indicate WARNING."""
#         state_str = str(getattr(m.state, "value", m.state)).upper()
#         if state_str == "WARNING":
#             return True
#         if state_str == "FAULT":
#             return False

#         # Extract metric parameters safely
#         tool_wear = float(getattr(m, "tool_wear_min", getattr(m, "tool_wear", 0.0)))
        
#         process_temp = float(
#             getattr(m, "process_temp_c", getattr(m, "process_temp", getattr(m, "process_temperature_k", 0.0)))
#         )
#         if process_temp > 200.0:  # Temp in Kelvin (e.g. 315 K -> 41.85 C)
#             process_temp -= 273.15

#         torque = float(getattr(m, "torque_nm", getattr(m, "torque", 0.0)))

#         # Warning threshold triggers (AI4I dataset standards)
#         if tool_wear > 180.0 or process_temp > 55.0 or torque > 55.0:
#             return True

#         return False

#     def get_machine_status(self) -> Dict[str, str]:
#         """Return dict of machine_id -> current state, accurately marking warning states."""
#         status_dict = {}
#         for mid, m in self.machines.items():
#             state_str = str(getattr(m.state, "value", m.state)).upper()
#             if state_str != "FAULT" and state_str != "IDLE":
#                 if self._is_machine_in_warning(m):
#                     state_str = "WARNING"
#             status_dict[mid] = state_str
#         return status_dict

#     def get_running_count(self) -> int:
#         """Count machines currently running nominally (excluding FAULT and IDLE)."""
#         return sum(
#             1 for mid, status in self.get_machine_status().items()
#             if status == "RUNNING"
#         )

#     def get_warning_count(self) -> int:
#         """Count machines currently showing warning signs or degraded parameters."""
#         return sum(
#             1 for m in self.machines.values()
#             if self._is_machine_in_warning(m)
#         )

#     def get_fault_count(self) -> int:
#         """Count machines currently in FAULT state."""
#         return sum(
#             1 for m in self.machines.values()
#             if str(getattr(m.state, "value", m.state)).upper() == "FAULT"
#         )


# # Alias for integration tests
# FactorySimulator = VirtualFactory




"""Virtual factory managing all CNC machines and the simulation clock.

The factory owns the simulation lifecycle:
* ``start()`` / ``pause()`` / ``reset()`` control the clock.
* ``tick()`` advances all machines by one time step.
* ``apply_scenario()`` injects parameter overrides into target machines.
* ``full_factory_reset()`` resets everything to a clean demo-ready state.
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
        self.random_seed = getattr(config, "random_seed", 42)

        # Create machines from configuration
        self.machines: Dict[str, VirtualMachine] = {}
        machines_cfg = getattr(config, "machines", [])
        if not machines_cfg and hasattr(config, "simulator"):
            machines_cfg = getattr(config.simulator, "machines", [])

        for mcfg in machines_cfg:
            machine = VirtualMachine(mcfg, random_seed=self.random_seed)
            self.machines[machine.machine_id] = machine

        # Ordered list matching the production line
        self.line_order = sorted(
            self.machines.values(), key=lambda m: getattr(m, "position", 0)
        )

        # Simulation clock
        self._running = False
        self._tick_count = 0
        self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
        self._speed_multiplier = 1

        tick_sec = 1.0
        if hasattr(config, "settings") and isinstance(config.settings, dict):
            tick_sec = float(config.settings.get("simulation", {}).get("tick_seconds", 1.0))
        self._dt_min = tick_sec

        # Active scenario
        self._active_scenario: Optional[Scenario] = None
        self._scenario_ticks_remaining = 0

        logger.info(
            "VirtualFactory initialized with %d machines: %s",
            len(self.machines),
            ", ".join(self.machines.keys()),
        )

    # ------------------------------------------------------------------
    # Dynamic Lifetime Aggregates (Preserves Downtime Across Restores)
    # ------------------------------------------------------------------

    @property
    def total_production(self) -> int:
        """Dynamic total production across all machines."""
        return sum(int(getattr(m, "production_count", 0)) for m in self.machines.values())

    @property
    def total_downtime_min(self) -> float:
        """Dynamic cumulative downtime across all machines (never wipes on restore)."""
        return sum(float(getattr(m, "downtime_min", 0.0)) for m in self.machines.values())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start simulation clock and switch IDLE machines to RUNNING."""
        self._running = True
        for m in self.machines.values():
            if str(getattr(m.state, "value", m.state)).upper() != "FAULT":
                if hasattr(m, "start") and callable(getattr(m, "start")):
                    m.start()
                else:
                    m.state = MachineState.RUNNING
        logger.info("Factory simulation started (speed=%dx).", self._speed_multiplier)

    def pause(self) -> None:
        """Pause simulation clock and update non-fault machines to IDLE."""
        self._running = False
        for m in self.machines.values():
            if str(getattr(m.state, "value", m.state)).upper() != "FAULT":
                if hasattr(m, "pause") and callable(getattr(m, "pause")):
                    m.pause()
                else:
                    m.state = MachineState.IDLE
        logger.info("Factory simulation paused at tick %d.", self._tick_count)

    def reset(self) -> None:
        """Reset simulation clock back to 0 without wiping lifetime downtime history."""
        self._running = False
        self._tick_count = 0
        self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
        self._active_scenario = None
        self._scenario_ticks_remaining = 0
        for m in self.machines.values():
            if hasattr(m, "pause") and callable(getattr(m, "pause")):
                m.pause()
            else:
                m.state = MachineState.IDLE
        logger.info("Factory simulation clock reset (cumulative downtime preserved).")

    def full_factory_reset(self) -> None:
        """Complete Danger Zone reset (only place lifetime counters are zeroed)."""
        self._running = False
        self._tick_count = 0
        self._sim_time = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
        self._speed_multiplier = 1

        self._active_scenario = None
        self._scenario_ticks_remaining = 0

        for m in self.machines.values():
            m.reset()  # Resets internal parameters and lifetime counters
            m.state = MachineState.IDLE

            if hasattr(m, "clear_scenario_modifiers"):
                m.clear_scenario_modifiers()

        logger.info(
            "Full factory reset completed: %d machines restored to initial state.",
            len(self.machines),
        )

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
        """Activate a named scenario."""
        scenario = get_scenario(scenario_name)
        if target_machine_ids is not None:
            scenario.target_machine_ids = target_machine_ids
        if duration_ticks > 0:
            scenario.duration_ticks = duration_ticks

        self._active_scenario = scenario
        self._scenario_ticks_remaining = scenario.duration_ticks

        for mid, machine in self.machines.items():
            if scenario.applies_to(mid):
                if hasattr(machine, "set_scenario_modifiers"):
                    machine.set_scenario_modifiers(scenario.modifiers)
            else:
                if hasattr(machine, "clear_scenario_modifiers"):
                    machine.clear_scenario_modifiers()

        logger.info(
            "Scenario '%s' activated (targets=%s, duration=%s).",
            scenario.name,
            scenario.target_machine_ids or "ALL",
            scenario.duration_ticks or "indefinite",
        )

    def clear_scenario(self) -> None:
        """Remove all scenario overrides and restore machines without losing downtime history."""
        self._active_scenario = None
        self._scenario_ticks_remaining = 0

        for m in self.machines.values():
            # 1. Clear scenario modifiers
            if hasattr(m, "clear_scenario_modifiers"):
                m.clear_scenario_modifiers()

            # 2. Cool thermal/strain parameters back to safe baseline
            if hasattr(m, "base_process_temp_c") and hasattr(m, "process_temp_k"):
                m.process_temp_k = m.base_process_temp_c + 273.15
            if hasattr(m, "baseline_temp") and hasattr(m, "process_temp"):
                m.process_temp = m.baseline_temp

            if hasattr(m, "base_torque") and hasattr(m, "current_torque"):
                m.current_torque = m.base_torque
            if hasattr(m, "baseline_torque") and hasattr(m, "torque"):
                m.torque = m.baseline_torque

            # 3. Restore FAULT machines back to operational state
            state_str = str(getattr(m.state, "value", m.state)).upper()
            if state_str == "FAULT":
                if hasattr(m, "restore_operation"):
                    m.restore_operation()
                elif hasattr(m, "repair"):
                    m.repair()
                else:
                    m.state = MachineState.RUNNING if self._running else MachineState.IDLE

        logger.info("Scenario cleared — normal operation restored (cumulative downtime preserved).")

    # ------------------------------------------------------------------
    # Simulation tick
    # ------------------------------------------------------------------

    def tick(self, force: bool = False) -> List[TelemetrySample]:
        """Advance the simulation by one time step."""
        if not self._running and not force:
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

        return samples

    # ------------------------------------------------------------------
    # Status & Warning Calculation
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

    def _is_machine_in_warning(self, m: VirtualMachine) -> bool:
        """Check if a machine state or its operational metrics indicate WARNING."""
        state_str = str(getattr(m.state, "value", m.state)).upper()
        if state_str == "WARNING":
            return True
        if state_str == "FAULT":
            return False

        tool_wear = float(getattr(m, "tool_wear_min", getattr(m, "tool_wear", 0.0)))
        process_temp = float(
            getattr(m, "process_temp_c", getattr(m, "process_temp", getattr(m, "process_temperature_k", 0.0)))
        )
        if process_temp > 200.0:  # Temp in Kelvin (e.g. 315 K -> 41.85 C)
            process_temp -= 273.15

        torque = float(getattr(m, "torque_nm", getattr(m, "torque", 0.0)))

        if tool_wear > 180.0 or process_temp > 55.0 or torque > 55.0:
            return True

        return False

    def get_machine_status(self) -> Dict[str, str]:
        """Return dict of machine_id -> current state, accurately marking warning states."""
        status_dict = {}
        for mid, m in self.machines.items():
            state_str = str(getattr(m.state, "value", m.state)).upper()
            if state_str != "FAULT" and state_str != "IDLE":
                if self._is_machine_in_warning(m):
                    state_str = "WARNING"
            status_dict[mid] = state_str
        return status_dict

    def get_running_count(self) -> int:
        """Count machines currently running nominally (excluding FAULT and IDLE)."""
        return sum(
            1 for mid, status in self.get_machine_status().items()
            if status == "RUNNING"
        )

    def get_warning_count(self) -> int:
        """Count machines currently showing warning signs or degraded parameters."""
        return sum(
            1 for m in self.machines.values()
            if self._is_machine_in_warning(m)
        )

    def get_fault_count(self) -> int:
        """Count machines currently in FAULT state."""
        return sum(
            1 for m in self.machines.values()
            if str(getattr(m.state, "value", m.state)).upper() == "FAULT"
        )


# Alias for integration tests
FactorySimulator = VirtualFactory