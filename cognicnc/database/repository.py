"""Database repository — all CRUD operations in one place.

Every database interaction goes through this module. Dashboard and
service layers never import SQLAlchemy directly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cognicnc.config import AppConfig
from cognicnc.database.connection import get_engine, get_session, reset_engine
from cognicnc.database.models import (
    AlertRecord,
    Base,
    MaintenanceEvent,
    PredictionRecord,
    ProductionRecord,
    TelemetryRecord,
)
from cognicnc.simulator.telemetry import TelemetrySample

logger = logging.getLogger("cognicnc.database")


class Repository:
    """Centralized data access for all CogniCNC tables."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._initialized = False

    def init_db(self) -> None:
        """Create all tables if they do not exist."""
        engine = get_engine(self.config)
        Base.metadata.create_all(engine)
        self._initialized = True
        logger.info("Database tables initialized.")

    def _session(self) -> Session:
        if not self._initialized:
            self.init_db()
        return get_session(self.config)

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def store_telemetry(self, samples: List[TelemetrySample]) -> int:
        """Insert a batch of telemetry samples. Returns count inserted."""
        if not samples:
            return 0
        session = self._session()
        try:
            records = [
                TelemetryRecord(
                    timestamp=s.timestamp,
                    machine_id=s.machine_id,
                    state=s.state,
                    air_temperature_k=s.air_temperature_k,
                    process_temperature_k=s.process_temperature_k,
                    rotational_speed_rpm=s.rotational_speed_rpm,
                    torque_nm=s.torque_nm,
                    tool_wear_min=s.tool_wear_min,
                    vibration_mm_s=s.vibration_mm_s,
                    power_kw=s.power_kw,
                    production_count=s.production_count,
                    uptime_min=s.uptime_min,
                    downtime_min=s.downtime_min,
                )
                for s in samples
            ]
            session.add_all(records)
            session.commit()
            logger.debug("Stored %d telemetry records.", len(records))
            return len(records)
        except Exception:
            session.rollback()
            logger.exception("Failed to store telemetry.")
            raise
        finally:
            session.close()

    def get_telemetry_history(
        self, machine_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Return recent telemetry for a machine, newest first."""
        session = self._session()
        try:
            stmt = (
                select(TelemetryRecord)
                .where(TelemetryRecord.machine_id == machine_id)
                .order_by(TelemetryRecord.id.desc())
                .limit(limit)
            )
            rows = session.execute(stmt).scalars().all()
            return [
                {   
                    "machine_id": r.machine_id,
                    "timestamp": r.timestamp,
                    "state": r.state,
                    "air_temperature_k": r.air_temperature_k,
                    "process_temperature_k": r.process_temperature_k,
                    "rotational_speed_rpm": r.rotational_speed_rpm,
                    "torque_nm": r.torque_nm,
                    "tool_wear_min": r.tool_wear_min,
                    "vibration_mm_s": r.vibration_mm_s,
                    "power_kw": r.power_kw,
                    "production_count": r.production_count,
                }
                for r in reversed(rows)
            ]
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Predictions
    # ------------------------------------------------------------------

    def store_prediction(
        self, machine_id: str, timestamp: str, prediction: Dict[str, Any]
    ) -> None:
        """Store a single inference result."""
        session = self._session()
        try:
            record = PredictionRecord(
                timestamp=timestamp,
                machine_id=machine_id,
                failure_probability=prediction["failure_probability"],
                failure_prediction=prediction["failure_prediction"],
                anomaly_score=prediction["anomaly_score"],
                is_anomaly=prediction["is_anomaly"],
                model_type=prediction.get("model_type", "unknown"),
            )
            session.add(record)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to store prediction for %s.", machine_id)
            raise
        finally:
            session.close()

    def get_latest_prediction(self, machine_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recent prediction for a machine."""
        session = self._session()
        try:
            stmt = (
                select(PredictionRecord)
                .where(PredictionRecord.machine_id == machine_id)
                .order_by(PredictionRecord.id.desc())
                .limit(1)
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return None
            return {
                "failure_probability": row.failure_probability,
                "failure_prediction": row.failure_prediction,
                "anomaly_score": row.anomaly_score,
                "is_anomaly": row.is_anomaly,
                "model_type": row.model_type,
                "timestamp": row.timestamp,
            }
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Alerts (with deduplication)
    # ------------------------------------------------------------------

    def create_alert(
        self,
        timestamp: str,
        machine_id: str,
        severity: str,
        category: str,
        message: str,
        model_output: str = "",
        recommended_action: str = "",
        dedup_window_seconds: int = 30,
    ) -> bool:
        """Create an alert if no identical alert exists within the dedup window.

        Returns True if a new alert was inserted, False if deduplicated.
        """
        session = self._session()
        try:
            # Check for recent duplicate
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=dedup_window_seconds)
            stmt = (
                select(AlertRecord)
                .where(
                    AlertRecord.machine_id == machine_id,
                    AlertRecord.category == category,
                    AlertRecord.severity == severity,
                    AlertRecord.created_at >= cutoff,
                )
                .limit(1)
            )
            existing = session.execute(stmt).scalar_one_or_none()
            if existing is not None:
                logger.debug(
                    "Alert deduplicated: %s/%s/%s", machine_id, category, severity
                )
                return False

            record = AlertRecord(
                timestamp=timestamp,
                machine_id=machine_id,
                severity=severity,
                category=category,
                message=message,
                model_output=model_output,
                recommended_action=recommended_action,
            )
            session.add(record)
            session.commit()
            logger.info(
                "Alert created: [%s] %s — %s", severity, machine_id, category
            )
            return True
        except Exception:
            session.rollback()
            logger.exception("Failed to create alert.")
            raise
        finally:
            session.close()

    def get_alerts(
        self,
        machine_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query alerts with optional filters, newest first."""
        session = self._session()
        try:
            stmt = select(AlertRecord).order_by(AlertRecord.id.desc())
            if machine_id:
                stmt = stmt.where(AlertRecord.machine_id == machine_id)
            if severity:
                stmt = stmt.where(AlertRecord.severity == severity)
            stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [
                {
                    "id": r.id,
                    "timestamp": r.timestamp,
                    "machine_id": r.machine_id,
                    "severity": r.severity,
                    "category": r.category,
                    "message": r.message,
                    "recommended_action": r.recommended_action,
                    "acknowledged": r.acknowledged,
                }
                for r in rows
            ]
        finally:
            session.close()

    def acknowledge_alert(self, alert_id: int) -> bool:
        """Mark an alert as acknowledged."""
        session = self._session()
        try:
            stmt = select(AlertRecord).where(AlertRecord.id == alert_id)
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return False
            row.acknowledged = True
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_active_alert_count(self) -> int:
        """Count unacknowledged alerts."""
        session = self._session()
        try:
            stmt = select(func.count(AlertRecord.id)).where(
                AlertRecord.acknowledged == False  # noqa: E712
            )
            return session.execute(stmt).scalar() or 0
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Production
    # ------------------------------------------------------------------

    def store_production(
        self,
        timestamp: str,
        machine_id: str,
        parts_produced: int,
        parts_rejected: int,
        cycle_time_s: float,
    ) -> None:
        session = self._session()
        try:
            record = ProductionRecord(
                timestamp=timestamp,
                machine_id=machine_id,
                parts_produced=parts_produced,
                parts_rejected=parts_rejected,
                cycle_time_s=cycle_time_s,
            )
            session.add(record)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to store production record.")
            raise
        finally:
            session.close()

    def get_production_summary(self) -> Dict[str, Any]:
        """Aggregate production statistics across all machines."""
        session = self._session()
        try:
            stmt = select(
                func.sum(ProductionRecord.parts_produced).label("total_produced"),
                func.sum(ProductionRecord.parts_rejected).label("total_rejected"),
            )
            row = session.execute(stmt).one()
            total_produced = row.total_produced or 0
            total_rejected = row.total_rejected or 0
            return {
                "total_produced": total_produced,
                "total_rejected": total_rejected,
                "total_accepted": total_produced - total_rejected,
            }
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Maintenance events
    # ------------------------------------------------------------------

    def log_maintenance(
        self,
        timestamp: str,
        machine_id: str,
        event_type: str,
        description: str,
        duration_min: float = 0.0,
    ) -> None:
        session = self._session()
        try:
            record = MaintenanceEvent(
                timestamp=timestamp,
                machine_id=machine_id,
                event_type=event_type,
                description=description,
                duration_min=duration_min,
            )
            session.add(record)
            session.commit()
            logger.info("Maintenance logged: %s — %s", machine_id, event_type)
        except Exception:
            session.rollback()
            logger.exception("Failed to log maintenance event.")
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Uptime / Downtime
    # ------------------------------------------------------------------

    def get_machine_uptime_downtime(self) -> Dict[str, Dict[str, float]]:
        """Return {machine_id: {uptime_min, downtime_min}} from latest telemetry."""
        session = self._session()
        try:
            # Get the latest record per machine
            subq = (
                select(
                    TelemetryRecord.machine_id,
                    func.max(TelemetryRecord.id).label("max_id"),
                )
                .group_by(TelemetryRecord.machine_id)
                .subquery()
            )
            stmt = select(TelemetryRecord).join(
                subq,
                (TelemetryRecord.machine_id == subq.c.machine_id)
                & (TelemetryRecord.id == subq.c.max_id),
            )
            rows = session.execute(stmt).scalars().all()
            return {
                r.machine_id: {
                    "uptime_min": r.uptime_min,
                    "downtime_min": r.downtime_min,
                }
                for r in rows
            }
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Dispose the engine (call at application shutdown)."""
        reset_engine()
        logger.info("Database connection closed.")
        

CogniCNCRepository = Repository