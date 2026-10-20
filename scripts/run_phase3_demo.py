"""Phase 3 demo — database, decision engine, alerts, and analytics.

Usage
-----
    python scripts/run_phase3_demo.py
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
from cognicnc.services.decision_engine import DecisionEngine
from cognicnc.services.alert_service import AlertService
from cognicnc.database.repository import Repository
from cognicnc.analytics.production import ProductionAnalytics


def main() -> int:
    configure_logging()
    logger = get_logger("cognicnc")
    cfg = load_config()

    # Initialize components
    factory = VirtualFactory(cfg)
    inference = InferenceService(cfg)
    decision_engine = DecisionEngine(cfg)
    repo = Repository(cfg)
    alert_service = AlertService(cfg, repo)
    analytics = ProductionAnalytics(cfg, repo)

    try:
        inference.load()
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}")
        print("Run 'python scripts/train_models.py' first.\n")
        return 1

    repo.init_db()

    # ------------------------------------------------------------------
    # Phase A: Normal operation (15 ticks)
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("  Phase A: Normal Operation (15 ticks)")
    print("=" * 65)
    factory.start()
    alerts_created = 0
    for _ in range(15):
        samples = factory.tick()
        repo.store_telemetry(samples)
        for s in samples:
            pred = inference.predict(s)
            repo.store_prediction(s.machine_id, s.timestamp, pred)
            decision = decision_engine.evaluate(s, pred)
            alert_id = alert_service.process(s, decision)
            if alert_id:
                alerts_created += 1
            # Store production
            repo.store_production(
                s.timestamp, s.machine_id,
                parts_produced=1 if s.production_count > 0 else 0,
                parts_rejected=0,
                cycle_time_s=s.cycle_time_s,
            )

    print(f"  Telemetry stored  : {factory.tick_count * 5} records")
    print(f"  Alerts created    : {alerts_created}")
    print(f"  Active alerts     : {repo.get_active_alert_count()}")

    # ------------------------------------------------------------------
    # Phase B: Breakdown on TC-01 (10 ticks)
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("  Phase B: Machine Breakdown on TC-01 (10 ticks)")
    print("=" * 65)
    factory.apply_scenario("machine_breakdown", target_machine_ids=["TC-01"])
    alerts_before = alerts_created
    for _ in range(10):
        samples = factory.tick()
        repo.store_telemetry(samples)
        for s in samples:
            pred = inference.predict(s)
            repo.store_prediction(s.machine_id, s.timestamp, pred)
            decision = decision_engine.evaluate(s, pred)
            alert_id = alert_service.process(s, decision)
            if alert_id:
                alerts_created += 1
            repo.store_production(
                s.timestamp, s.machine_id,
                parts_produced=1 if s.production_count > 0 else 0,
                parts_rejected=1 if s.state == "FAULT" else 0,
                cycle_time_s=s.cycle_time_s,
            )

    print(f"  New alerts        : {alerts_created - alerts_before}")
    print(f"  Total alerts      : {alerts_created}")

    # Show latest decisions for TC-01
    tc01_pred = repo.get_latest_prediction("TC-01")
    if tc01_pred:
        print(f"\n  TC-01 latest prediction:")
        print(f"    Failure prob    : {tc01_pred['failure_probability']:.3f}")
        print(f"    Anomaly         : {tc01_pred['is_anomaly']}")

    # Show recent alerts
    recent_alerts = repo.get_alerts(machine_id="TC-01", limit=3)
    if recent_alerts:
        print(f"\n  Recent TC-01 alerts:")
        for a in recent_alerts:
            print(f"    [{a['severity']}] {a['category']}: {a['message'][:60]}...")

    # ------------------------------------------------------------------
    # Phase C: Recovery (5 ticks)
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("  Phase C: Recovery (5 ticks)")
    print("=" * 65)
    factory.clear_scenario()
    factory.machines["TC-01"].reset()
    factory.machines["TC-01"].start()
    for _ in range(5):
        samples = factory.tick()
        repo.store_telemetry(samples)
        for s in samples:
            pred = inference.predict(s)
            repo.store_prediction(s.machine_id, s.timestamp, pred)
            repo.store_production(
                s.timestamp, s.machine_id,
                parts_produced=1 if s.production_count > 0 else 0,
                parts_rejected=0,
                cycle_time_s=s.cycle_time_s,
            )

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("  Production Analytics")
    print("=" * 65)

    summary = analytics.compute_factory_summary()
    print(f"  Total produced    : {summary['total_produced']}")
    print(f"  Total rejected    : {summary['total_rejected']}")
    print(f"  Total accepted    : {summary['total_accepted']}")
    print(f"  Total uptime      : {summary['total_uptime_min']} min")
    print(f"  Total downtime    : {summary['total_downtime_min']} min")
    print(f"  Factory OEE       : {summary['factory_oee']:.2%}")
    print()
    print("  Machine OEE breakdown:")
    for mid, oee in summary["machine_oee"].items():
        print(
            f"    {mid:<7s} | A={oee['availability']:.2f} "
            f"P={oee['performance']:.2f} "
            f"Q={oee['quality']:.2f} "
            f"OEE={oee['oee']:.2%}"
        )

    print()
    bottleneck = analytics.identify_bottleneck()
    print(f"  Bottleneck        : {bottleneck.get('bottleneck', 'N/A')}")
    if "throughput_parts_per_min" in bottleneck:
        print(f"    Throughput      : {bottleneck['throughput_parts_per_min']} parts/min")

    print("\n" + "=" * 65)
    print("  Phase 3 verification complete.")
    print("=" * 65 + "\n")

    repo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())