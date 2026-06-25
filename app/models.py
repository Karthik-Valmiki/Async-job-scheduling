"""
SQLAlchemy ORM models
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, BigInteger, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email       = Column(String(255), unique=True, nullable=False)
    name        = Column(String(100), nullable=False)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at  = Column(DateTime, nullable=False, default=datetime.utcnow)

    jobs = relationship("Job", back_populates="user", foreign_keys="Job.user_id")


class Worker(Base):
    __tablename__ = "workers"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hostname       = Column(String(255), nullable=False)
    status         = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE | DEAD | DRAINING
    last_heartbeat = Column(DateTime, nullable=True)
    started_at     = Column(DateTime, nullable=False, default=datetime.utcnow)
    terminated_at  = Column(DateTime, nullable=True)

    executions = relationship("JobExecution", back_populates="worker")


class Job(Base):
    __tablename__ = "jobs"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id           = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status            = Column(String(20), nullable=False, default="QUEUED")  # QUEUED|RUNNING|SUCCESS|FAILED
    payload           = Column(JSONB, nullable=False)
    retry_count       = Column(Integer, nullable=False, default=0)
    current_worker_id = Column(UUID(as_uuid=True), ForeignKey("workers.id", ondelete="SET NULL"), nullable=True)
    last_error        = Column(Text, nullable=True)
    created_at        = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at        = Column(DateTime, nullable=True)
    completed_at      = Column(DateTime, nullable=True)

    user       = relationship("User", back_populates="jobs", foreign_keys=[user_id])
    executions = relationship("JobExecution", back_populates="job")


class JobExecution(Base):
    __tablename__ = "job_executions"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id           = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    worker_id        = Column(UUID(as_uuid=True), ForeignKey("workers.id", ondelete="SET NULL"), nullable=True)
    attempt_number   = Column(Integer, nullable=False)
    status           = Column(String(20), nullable=False)  # RUNNING | SUCCESS | FAILED
    execution_time_ms = Column(BigInteger, nullable=True)
    error_message    = Column(Text, nullable=True)
    started_at       = Column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at         = Column(DateTime, nullable=True)

    job    = relationship("Job", back_populates="executions")
    worker = relationship("Worker", back_populates="executions")


class JobEvent(Base):
    __tablename__ = "job_events"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id     = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(50), nullable=False)
    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=True)
    event_metadata = Column("metadata", JSONB, nullable=True)  # 'metadata' is reserved in SQLAlchemy
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
