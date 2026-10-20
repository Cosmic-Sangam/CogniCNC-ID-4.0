"""SQLAlchemy ORM models for the CogniCNC database.

Tables
------
* ``telemetry_log``     — time-series machine telemetry
* ``predictions``       — model inference results
* ``alerts``            — deduplicated alert records
* ``maintenance_events`` — maintenance actions and recommendations
* ``production_log``    — per-tick production counts
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TelemetryRecord(Base):
    __tablename__ = "telemetry_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    machine_id: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(15), nullable=False)
    air_temperature_k: Mapped[float] = mapped_column(Float, nullable=False)
    process_temperature_k: Mapped[float] = mapped_column(Float, nullable=False)
    rotational_speed_rpm: Mapped[float] = mapped_column(Float, nullable=False)
    torque_nm: Mapped[float] = mapped_column(Float, nullable=False)
    tool_wear_min: Mapped[float] = mapped_column(Float, nullable=False)
    vibration_mm_s: Mapped[float] = mapped_column(Float, nullable=False)
    power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    production_count: Mapped[int] = mapped_column(Integer, nullable=False)
    uptime_min: Mapped[float] = mapped_column(Float, nullable=False)
    downtime_min: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )


class PredictionRecord(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    machine_id: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    failure_probability: Mapped[float] = mapped_column(Float, nullable=False)
    failure_prediction: Mapped[int] = mapped_column(Integer, nullable=False)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )


class AlertRecord(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    machine_id: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # INFO|WARNING|CRITICAL
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    model_output: Mapped[str] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    machine_id: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    duration_min: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )


class ProductionRecord(Base):
    __tablename__ = "production_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    machine_id: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    parts_produced: Mapped[int] = mapped_column(Integer, nullable=False)
    parts_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cycle_time_s: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )