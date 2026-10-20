"""Phase 2 demo — run the virtual factory with inference.

Usage
-----
    python scripts/run_simulator.py

Demonstrates:
1. Factory startup and normal operation (10 ticks).
2. Scenario injection (temperature increase on MC-01, 5 ticks).
3. Scenario injection (machine breakdown on TC-01, 5 ticks).
4. Scenario clear and return to normal (5 ticks).
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cognicnc.config import load_config
from cognicnc.logging_config import configure_logging, get_logger
from cognicnc.simulator.factory import VirtualFactory
from cognicnc.services.inference import InferenceService


def print_header(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_samples(samples, predictions=None) -> None:
    for i, s in enumerate(samples):
        pred_str = ""
        if predictions:
            p = predictions[i]
            pred_str = (
                f"  | fail_prob={p['failure_probability']:.3f} "
                f"anomaly={p['is_anomaly']} "
                f"score={p['anomaly_score']:.3f}"
            )
        print(
            f"  {s.machine_id:<7s} | {s.state:<8s} | "
            f"air={s.air_temperature_k:.1f}K "
            f"proc={s.process_temperature_k:.1f}K "
            f"rpm={s.rotational_speed_rpm:>7.0f} "
            f"torque={s.torque_nm:>5.1f} "
            f"wear={s.tool_wear_min:>6.1f} "
            f"vib={s.vibration_mm_s:>4.1f} "
            f"prod={s.production_count:>4d}"
            f"{pred_str}"
        )


def main() -> int:
    configure_logging()
    logger = get_logger("cognicnc.simulator")
    cfg = load_config()

    factory = VirtualFactory(cfg)
    inference = InferenceService(cfg)

    try:
        inference.load()
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}")
        print("Run 'python scripts/train_models.py' first to create artifacts.\n")
        return 1

    # ------------------------------------------------------------------
    # Phase A: Normal operation
    # ------------------------------------------------------------------
    print_header("Phase A: Normal Operation (10 ticks)")
    factory.start()
    for tick in range(10):
        samples = factory.tick()
        if tick == 0 or tick == 9:
            print(f"\n  --- Tick {factory.tick_count} ---")
            predictions = inference.predict_batch(samples)
            print_samples(samples, predictions)

    # ------------------------------------------------------------------
    # Phase B: Temperature increase on MC-01
    # ------------------------------------------------------------------
    print_header("Phase B: Temperature Increase on MC-01 (5 ticks)")
    factory.apply_scenario("temperature_increase", target_machine_ids=["MC-01"])
    for tick in range(5):
        samples = factory.tick()
        if tick == 4:
            print(f"\n  --- Tick {factory.tick_count} ---")
            predictions = inference.predict_batch(samples)
            print_samples(samples, predictions)

    # ------------------------------------------------------------------
    # Phase C: Machine breakdown on TC-01
    # ------------------------------------------------------------------
    print_header("Phase C: Machine Breakdown on TC-01 (5 ticks)")
    factory.clear_scenario()
    factory.apply_scenario("machine_breakdown", target_machine_ids=["TC-01"])
    for tick in range(5):
        samples = factory.tick()
        if tick == 4:
            print(f"\n  --- Tick {factory.tick_count} ---")
            predictions = inference.predict_batch(samples)
            print_samples(samples, predictions)

    # ------------------------------------------------------------------
    # Phase D: Return to normal
    # ------------------------------------------------------------------
    print_header("Phase D: Return to Normal (5 ticks)")
    factory.clear_scenario()
    # Reset the faulted machine
    factory.machines["TC-01"].reset()
    factory.machines["TC-01"].start()
    for tick in range(5):
        samples = factory.tick()
        if tick == 4:
            print(f"\n  --- Tick {factory.tick_count} ---")
            predictions = inference.predict_batch(samples)
            print_samples(samples, predictions)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print_header("Simulation Summary")
    print(f"  Total ticks        : {factory.tick_count}")
    print(f"  Total production   : {factory.total_production} parts")
    print(f"  Total downtime     : {factory.total_downtime_min:.1f} min")
    print(f"  Machine states     : {factory.get_machine_status()}")
    print(f"  Active scenario    : {factory.active_scenario_name or 'None'}")
    print(f"\n  Phase 2 verification complete.\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())