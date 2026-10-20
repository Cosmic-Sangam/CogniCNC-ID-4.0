"""Predefined simulation scenarios for what-if analysis.

Each scenario defines a set of parameter modifiers that the factory
applies to target machines during each tick. Scenarios are clearly
labelled as test inputs and do not represent validated real-world
failure data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Scenario:
    """A named simulation scenario with parameter overrides."""
    name: str
    description: str
    target_machine_ids: List[str]  # empty = all machines
    modifiers: Dict[str, float] = field(default_factory=dict)
    duration_ticks: int = 0  # 0 = indefinite until cleared

    def applies_to(self, machine_id: str) -> bool:
        if not self.target_machine_ids:
            return True
        return machine_id in self.target_machine_ids


# ---------------------------------------------------------------------------
# Predefined scenarios
# ---------------------------------------------------------------------------

SCENARIOS: Dict[str, Scenario] = {
    "normal": Scenario(
        name="normal",
        description="Normal production — no overrides.",
        target_machine_ids=[],
        modifiers={},
    ),
    "temperature_increase": Scenario(
        name="temperature_increase",
        description="Ambient temperature rise (+15 K air, +10 K process).",
        target_machine_ids=[],
        modifiers={"air_temp_offset": 15.0, "process_temp_offset": 10.0},
    ),
    "high_tool_wear": Scenario(
        name="high_tool_wear",
        description="Accelerated tool wear (5x rate).",
        target_machine_ids=[],
        modifiers={"wear_rate_factor": 5.0},
    ),
    "high_torque": Scenario(
        name="high_torque",
        description="Excessive torque load (1.8x).",
        target_machine_ids=[],
        modifiers={"torque_factor": 1.8},
    ),
    "vibration_increase": Scenario(
        name="vibration_increase",
        description="Elevated vibration levels (3x). Simulator display only.",
        target_machine_ids=[],
        modifiers={"vibration_factor": 3.0},
    ),
    "rpm_drop": Scenario(
        name="rpm_drop",
        description="Spindle speed degradation (0.6x).",
        target_machine_ids=[],
        modifiers={"rpm_factor": 0.6},
    ),
    "machine_breakdown": Scenario(
        name="machine_breakdown",
        description="Forced machine fault.",
        target_machine_ids=[],
        modifiers={"force_fault": 1.0},
    ),
    "high_demand": Scenario(
        name="high_demand",
        description="High production demand (increased RPM, faster wear).",
        target_machine_ids=[],
        modifiers={"rpm_factor": 1.2, "wear_rate_factor": 1.5},
    ),
}


def get_scenario(name: str) -> Scenario:
    """Look up a scenario by name. Raises KeyError if not found."""
    if name not in SCENARIOS:
        available = ", ".join(sorted(SCENARIOS.keys()))
        raise KeyError(f"Unknown scenario '{name}'. Available: {available}")
    return SCENARIOS[name]


def list_scenarios() -> List[str]:
    return sorted(SCENARIOS.keys())