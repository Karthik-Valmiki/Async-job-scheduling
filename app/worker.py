"""
ARQ Worker - processes jobs from the Redis queue.

Responsibilities:
  1. Register itself in the workers table on startup.
  2. Send a heartbeat every 5 seconds.
  3. Pick up 'process_job' tasks, simulate work, update DB.
  4. Handle failures: mark job FAILED, record error.
  5. Mark itself DEAD on clean shutdown.
"""
import asyncio
import socket
import uuid
from datetime import datetime, timezone
from arq.connections import RedisSettings
from sqlalchemy.orm import Session
from sqlalchemy import select

from .database import SessionLocal
from . import models

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _db_transition(db: Session, job: models.Job, new_status: str, event_type: str, old_status: str):
    """Record a job state transition and write a job_event row."""
    job.status = new_status
    event = models.JobEvent(
        job_id=job.id,
        event_type=event_type,
        old_status=old_status,
        new_status=new_status,
    )
    db.add(event)


# ─── Main task ───────────────────────────────────────────────────────────────

async def process_job(ctx: dict, job_id_str: str):
    """
    Core job processing function called by ARQ.
    Idempotent: checks current job status before doing work.
    """
    worker_id: uuid.UUID = ctx["worker_id"]
    job_id = uuid.UUID(job_id_str)
    t_start = _now()

    with SessionLocal() as db:
        job = db.get(models.Job, job_id)
        if job is None:
            return  # Job deleted - nothing to do

        # Idempotency guard: if already SUCCESS don't run again
        if job.status == "SUCCESS":
            return

        old_status = job.status
        attempt_number = job.retry_count + 1

        # Create execution record
        execution = models.JobExecution(
            job_id=job_id,
            worker_id=worker_id,
            attempt_number=attempt_number,
            status="RUNNING",
            started_at=t_start,
        )
        db.add(execution)

        # Update job to RUNNING
        job.status = "RUNNING"
        job.current_worker_id = worker_id
        job.started_at = t_start
        job.retry_count = attempt_number

        db.add(models.JobEvent(
            job_id=job_id,
            event_type="STATUS_CHANGE",
            old_status=old_status,
            new_status="RUNNING",
        ))
        db.commit()
        execution_id = execution.id

    try:
        # ── Simulate actual work (replace with real logic) ──
        import random
        # 20% chance of failure to demonstrate the retry / FAILED path
        if random.random() < 0.20:
            raise ValueError("Simulated transient failure")

        await asyncio.sleep(1.5)  # simulate processing time
        # ────────────────────────────────────────────────────

        t_end = _now()
        elapsed_ms = int((t_end - t_start).total_seconds() * 1000)

        with SessionLocal() as db:
            execution = db.get(models.JobExecution, execution_id)
            if execution:
                execution.status = "SUCCESS"
                execution.ended_at = t_end
                execution.execution_time_ms = elapsed_ms

            job = db.get(models.Job, job_id)
            if job:
                job.status = "SUCCESS"
                job.completed_at = t_end
                job.current_worker_id = None
                db.add(models.JobEvent(
                    job_id=job_id,
                    event_type="STATUS_CHANGE",
                    old_status="RUNNING",
                    new_status="SUCCESS",
                ))
            db.commit()

    except Exception as exc:
        t_end = _now()
        elapsed_ms = int((t_end - t_start).total_seconds() * 1000)

        with SessionLocal() as db:
            execution = db.get(models.JobExecution, execution_id)
            if execution:
                execution.status = "FAILED"
                execution.ended_at = t_end
                execution.execution_time_ms = elapsed_ms
                execution.error_message = str(exc)

            job = db.get(models.Job, job_id)
            if job:
                job.status = "FAILED"
                job.last_error = str(exc)
                job.current_worker_id = None
                db.add(models.JobEvent(
                    job_id=job_id,
                    event_type="STATUS_CHANGE",
                    old_status="RUNNING",
                    new_status="FAILED",
                ))
            db.commit()
        raise  # re-raise so ARQ knows the task failed


# ─── Heartbeat ───────────────────────────────────────────────────────────────

async def _heartbeat_loop(worker_id: uuid.UUID):
    while True:
        await asyncio.sleep(5)
        try:
            with SessionLocal() as db:
                w = db.get(models.Worker, worker_id)
                if w:
                    w.last_heartbeat = _now()
                    db.commit()
        except Exception as e:
            print(f"[Heartbeat] Error: {e}")


# ─── Lifecycle ───────────────────────────────────────────────────────────────

async def startup(ctx: dict):
    worker_id = uuid.uuid4()
    ctx["worker_id"] = worker_id

    with SessionLocal() as db:
        w = models.Worker(
            id=worker_id,
            hostname=socket.gethostname(),
            status="ACTIVE",
            last_heartbeat=_now(),
        )
        db.add(w)
        db.commit()

    ctx["heartbeat_task"] = asyncio.create_task(_heartbeat_loop(worker_id))
    print(f"[Worker] Started — id={worker_id}, host={socket.gethostname()}")


async def shutdown(ctx: dict):
    ctx["heartbeat_task"].cancel()
    worker_id = ctx["worker_id"]

    with SessionLocal() as db:
        w = db.get(models.Worker, worker_id)
        if w:
            w.status = "DEAD"
            w.terminated_at = _now()
            db.commit()

    print(f"[Worker] Shut down — id={worker_id}")


# ─── Worker Settings ─────────────────────────────────────────────────────────

class WorkerSettings:
    functions = [process_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(host="127.0.0.1", port=6379)
    max_jobs = 10
    job_timeout = 30
