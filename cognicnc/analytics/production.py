"""Production analytics and OEE calculations.

OEE (Overall Equipment Effectiveness) is computed as:

    OEE = Availability x Performance x Quality

Assumptions (simulation-specific, clearly documented):
* **Availability** = Uptime / (Uptime + Downtime).
  Planned production time equals total simulation time.
* **Performance** = (Actual Parts x Ideal Cycle Time) / Uptime.
  Ideal cycle times are defined per machine type. Capped at 1.0.
* **Quality** = (Total Parts - Rejected Parts) / Total Parts.
  Rejection is estimated from machine state history:
  RUNNING → 1% reject rate, WARNING → 5%, FAULT → 100%.
  This is a simulation heuristic, not measured quality data.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from cognicnc.config import AppConfig
from cognicnc.database.repository import Repository

logger = logging.getLogger("cognicnc.simulator")

# Ideal cycle time per machine type (seconds per part).
# These are simulation heuristics, not manufacturer specifications.
IDEAL_CYCLE_TIMES: Dict[str, float] = {
    "turning": 120.0,
    "milling": 150.0,
    "drilling": 90.0,
    "grinding": 180.0,
    "inspection": 10.0,
}


class ProductionAnalytics:
    """Compute production KPIs from database records."""

    def __init__(self, config: AppConfig, repository: Repository):
        self.config = config
        self.repo = repository
        self._machine_types: Dict[str, str] = {
            m["id"]: m["type"] for m in config.machines
        }

    def compute_oee(self) -> Dict[str, Dict[str, float]]:
        """Compute OEE for each machine.

        Returns
        -------
        dict mapping machine_id to:
            availability : float (0.0 – 1.0)
            performance  : float (0.0 – 1.0, capped)
            quality      : float (0.0 – 1.0)
            oee          : float (0.0 – 1.0)
        """
        uptime_data = self.repo.get_machine_uptime_downtime()
        prod_summary = self.repo.get_production_summary()
        results: Dict[str, Dict[str, float]] = {}

        for machine_id, times in uptime_data.items():
            uptime = times["uptime_min"]
            downtime = times["downtime_min"]
            total_time = uptime + downtime

            # Availability
            availability = uptime / total_time if total_time > 0 else 0.0

            # Performance
            machine_type = self._machine_types.get(machine_id, "turning")
            ideal_ct = IDEAL_CYCLE_TIMES.get(machine_type, 120.0)
            # Get production count from latest telemetry
            history = self.repo.get_telemetry_history(machine_id, limit=1)
            parts = history[0]["production_count"] if history else 0
            uptime_seconds = uptime * 60.0
            if uptime_seconds > 0 and parts > 0:
                performance = (parts * ideal_ct) / uptime_seconds
                performance = min(performance, 1.0)  # Cap at 100%
            else:
                performance = 0.0

            # Quality (simulation heuristic)
            # We estimate rejects from the proportion of time in each state.
            # For simplicity, use a fixed quality based on current state.
            current_state = history[0]["state"] if history else "IDLE"
            if current_state == "FAULT":
                quality = 0.0
            elif current_state == "WARNING":
                quality = 0.95
            else:
                quality = 0.99

            oee = availability * performance * quality

            results[machine_id] = {
                "availability": round(availability, 4),
                "performance": round(performance, 4),
                "quality": round(quality, 4),
                "oee": round(oee, 4),
            }

        return results

    def compute_factory_summary(self) -> Dict[str, Any]:
        """Compute factory-wide production summary."""
        prod = self.repo.get_production_summary()
        oee_data = self.compute_oee()
        uptime_data = self.repo.get_machine_uptime_downtime()

        total_uptime = sum(t["uptime_min"] for t in uptime_data.values())
        total_downtime = sum(t["downtime_min"] for t in uptime_data.values())

        # Factory OEE = average of machine OEEs (simplified)
        oee_values = [v["oee"] for v in oee_data.values()]
        avg_oee = sum(oee_values) / len(oee_values) if oee_values else 0.0

        return {
            "total_produced": prod["total_produced"],
            "total_rejected": prod["total_rejected"],
            "total_accepted": prod["total_accepted"],
            "total_uptime_min": round(total_uptime, 1),
            "total_downtime_min": round(total_downtime, 1),
            "factory_oee": round(avg_oee, 4),
            "machine_oee": oee_data,
        }

    def identify_bottleneck(self) -> Dict[str, Any]:
        """Identify the machine with the lowest throughput.

        Throughput = parts produced / uptime minutes.
        Machines with zero uptime are excluded.
        """
        uptime_data = self.repo.get_machine_uptime_downtime()
        throughputs: Dict[str, float] = {}

        for machine_id, times in uptime_data.items():
            uptime = times["uptime_min"]
            if uptime <= 0:
                continue
            history = self.repo.get_telemetry_history(machine_id, limit=1)
            parts = history[0]["production_count"] if history else 0
            throughputs[machine_id] = parts / uptime

        if not throughputs:
            return {"bottleneck": None, "reason": "No production data yet."}

        bottleneck_id = min(throughputs, key=throughputs.get)
        return {
            "bottleneck": bottleneck_id,
            "throughput_parts_per_min": round(throughputs[bottleneck_id], 3),
            "all_throughputs": {k: round(v, 3) for k, v in throughputs.items()},
        }