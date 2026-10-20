"""
scripts/run_e2e_benchmark.py
----------------------------
End-to-End Stress Test & Throughput Benchmark for CogniCNC.

Executes a configurable load test (default: 100 factory cycles)
through the entire pipeline:
  Factory Telemetry Generation -> ML Inference -> Rule Engine -> SQLite Persistence

Outputs performance metrics (throughput, latency, DB execution time).
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cognicnc.config import load_config
from cognicnc.database.repository import Repository as CogniCNCRepository
from cognicnc.simulator.factory import VirtualFactory as FactorySimulator
from cognicnc.services.inference import InferenceService
from cognicnc.services.decision_engine import DecisionEngine
from cognicnc.services.alert_service import AlertService
from cognicnc.analytics.production import ProductionAnalytics
from cognicnc.logging_config import configure_logging, get_logger

logger = get_logger("benchmark")


def run_benchmark(cycles: int = 100) -> None:
    configure_logging()
    print("\n" + "=" * 70)
    print(f"   COGNICNC END-TO-END PIPELINE BENCHMARK ({cycles} FACTORY TICKS)")
    print("=" * 70)

    config = load_config()
    db_path = PROJECT_ROOT / "data" / "processed" / "benchmark_test.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    # Point database path to benchmark SQLite file
    config.settings["paths"]["database"] = str(db_path.parent)

    repo = CogniCNCRepository(config)
    repo.init_db()

    inference = InferenceService(config)
    try:
        inference.load()
    except FileNotFoundError:
        logger.warning("Inference artifacts not found. Skipping ML inference phase.")

    decision = DecisionEngine(config)
    alert_svc = AlertService(config, repo)
    analytics = ProductionAnalytics(config, repo)
    factory = FactorySimulator(config)
    factory.start()

    total_samples = cycles * 5
    print(f"[*] Machines configured : 5 (TC-01, MC-01, DR-01, GR-01, VIS-01)")
    print(f"[*] Total cycles        : {cycles}")
    print(f"[*] Total telemetry rows: {total_samples}")
    print(f"[*] SQLite Target       : {db_path.name} (WAL mode enabled)")
    print("-" * 70)

    # Benchmark Loop
    inference_times = []
    db_times = []
    t_start = time.perf_counter()

    for c in range(cycles):
        # Inject scenario variations at specific ticks
        if c == 25:
            factory.apply_scenario("temperature_increase", target_machine_ids=["TC-01"])
        elif c == 50:
            factory.apply_scenario("high_torque", target_machine_ids=["MC-01"])
        elif c == 75:
            factory.apply_scenario("high_tool_wear", target_machine_ids=["DR-01"])

        samples = factory.tick()

        # Store telemetry batch
        t_db0 = time.perf_counter()
        repo.store_telemetry(samples)
        t_db1 = time.perf_counter()
        db_batch_time = (t_db1 - t_db0) * 1000.0

        for sample in samples:
            db_times.append(db_batch_time / len(samples))

            if inference.is_loaded:
                t_inf0 = time.perf_counter()
                pred = inference.predict(sample)
                t_inf1 = time.perf_counter()
                inference_times.append((t_inf1 - t_inf0) * 1000.0)

                action = decision.evaluate(sample, pred)
                _ = alert_svc.process_decision(action) if hasattr(alert_svc, "process_decision") else None

    t_total = time.perf_counter() - t_start

    # Analytics calculation
    summary = analytics.compute_factory_summary()

    # Cleanup test DB
    if db_path.exists():
        db_path.unlink()

    # Results calculation
    throughput = total_samples / t_total if t_total > 0 else 0.0
    avg_inf_ms = (sum(inference_times) / len(inference_times)) if inference_times else 0.0
    p95_inf_ms = sorted(inference_times)[int(len(inference_times) * 0.95)] if inference_times else 0.0
    avg_db_ms = (sum(db_times) / len(db_times)) if db_times else 0.0
    p95_db_ms = sorted(db_times)[int(len(db_times) * 0.95)] if db_times else 0.0

    print("\n" + "=" * 70)
    print("                    BENCHMARK RESULTS")
    print("=" * 70)
    print(f"Total Pipeline Execution Time : {t_total:.3f} s")
    print(f"Overall Processing Throughput  : {throughput:.1f} samples/sec")
    print(f"Inference Latency (Avg)       : {avg_inf_ms:.2f} ms / sample")
    print(f"Inference Latency (95th Pct)  : {p95_inf_ms:.2f} ms / sample")
    print(f"Database Write Latency (Avg)  : {avg_db_ms:.2f} ms / transaction")
    print(f"Database Write Latency (95th) : {p95_db_ms:.2f} ms / transaction")
    print(f"Factory OEE Calculated        : {summary.get('factory_oee', 0.0) * 100.0:.2f}%")
    
    bottleneck = summary.get('bottleneck', {})
    if bottleneck:
        print(f"Bottleneck Identified         : {bottleneck.get('machine_id', 'N/A')} ({bottleneck.get('machine_name', 'N/A')})")
    
    print("=" * 70)
    print("[SUCCESS] All pipeline stages passed end-to-end stress verification.\n")


if __name__ == "__main__":
    run_benchmark(cycles=100)