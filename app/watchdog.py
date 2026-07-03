"""
Watchdog Service
"""
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from arq import create_pool
from arq.connections import RedisSettings

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.database import SessionLocal
from app import models

HEARTBEAT_TIMEOUT_SECS = int(os.environ.get("HEARTBEAT_TIMEOUT_SECS", 30))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
RETRY_DELAYS = {1: 5, 2: 30, 3: 120}   # seconds to wait before requeue


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def run_watchdog():
    redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
    redis_port = int(os.environ.get("REDIS_PORT", 6379))
    redis = await create_pool(RedisSettings(host=redis_host, port=redis_port))
    print("[Watchdog] Running...")

    while True:
        try:
            with SessionLocal() as db:
                now = _now()
                stale_cutoff = now - timedelta(seconds=HEARTBEAT_TIMEOUT_SECS)

                # ── Step 1: Mark stale ACTIVE workers as DEAD ─────────────────
                stale_workers = db.execute(
                    select(models.Worker).where(
                        models.Worker.status == "ACTIVE",
                        models.Worker.last_heartbeat < stale_cutoff,
                    )
                ).scalars().all()

                dead_ids = []
                for w in stale_workers:
                    w.status = "DEAD"
                    w.terminated_at = now
                    dead_ids.append(w.id)
                    print(f"[Watchdog] Worker {w.id} marked DEAD (last HB: {w.last_heartbeat})")

                # ── Step 2: Orphan running jobs on dead workers ───────────────
                if dead_ids:
                    orphan_executions = db.execute(
                        select(models.JobExecution).where(
                            models.JobExecution.status == "RUNNING",
                            models.JobExecution.worker_id.in_(dead_ids),
                        )
                    ).scalars().all()

                    for ex in orphan_executions:
                        ex.status = "FAILED"
                        ex.ended_at = now
                        ex.error_message = "Worker crashed (heartbeat timeout)"

                        job = db.get(models.Job, ex.job_id)
                        if job and job.status == "RUNNING":
                            job.status = "FAILED"
                            job.last_error = "Worker crashed"
                            job.current_worker_id = None
                            db.add(models.JobEvent(
                                job_id=job.id,
                                event_type="WORKER_CRASH",
                                old_status="RUNNING",
                                new_status="FAILED",
                            ))

                # ── Step 3: Retry eligible FAILED jobs ────────────────────────
                failed_jobs = db.execute(
                    select(models.Job).where(
                        models.Job.status == "FAILED",
                        models.Job.retry_count < MAX_RETRIES,
                    )
                ).scalars().all()

                for job in failed_jobs:
                    delay = RETRY_DELAYS.get(job.retry_count, 5)
                    job.status = "QUEUED"
                    db.add(models.JobEvent(
                        job_id=job.id,
                        event_type="RETRY_SCHEDULED",
                        old_status="FAILED",
                        new_status="QUEUED",
                        event_metadata={"delay_seconds": delay, "attempt": job.retry_count + 1},
                    ))
                    # ARQ deduplication key ensures no double-queue
                    arq_key = f"{job.id}_attempt_{job.retry_count + 1}"
                    await redis.enqueue_job(
                        "process_job",
                        str(job.id),
                        _job_id=arq_key,
                        _defer_by=delay,
                    )
                    print(f"[Watchdog] Requeued job {job.id} (attempt {job.retry_count + 1}, delay {delay}s)")

                db.commit()

        except Exception as e:
            print(f"[Watchdog] Error: {e}")

        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(run_watchdog())
