from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import datetime
from uuid import UUID

from . import models, schemas
from .database import get_db, SessionLocal
import asyncio
import time

from arq import create_pool
from arq.connections import RedisSettings

router = APIRouter()


async def get_redis():
    return await create_pool(RedisSettings(host="127.0.0.1", port=6379))


# ─── Users ───────────────────────────────────────────────────────────────────

@router.post("/users", response_model=schemas.UserResponse, status_code=201)
def create_user(body: schemas.UserCreate, db: Session = Depends(get_db)):
    """Create a new user (k6 calls this during setup)."""
    existing = db.execute(
        select(models.User).where(models.User.email == body.email)
    ).scalars().first()
    if existing:
        return existing  # idempotent: return the existing user

    user = models.User(email=body.email, name=body.name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user(user_id: UUID, db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ─── Jobs ────────────────────────────────────────────────────────────────────

@router.post("/jobs", response_model=schemas.JobResponse, status_code=201)
async def submit_job(body: schemas.JobCreate, db: Session = Depends(get_db)):
    """
    Submit a job. Security: user_id is validated against the users table
    before inserting - prevents phantom user submissions.
    """
    user = db.get(models.User, body.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    job = models.Job(
        user_id=body.user_id,
        payload=body.payload,
        status="QUEUED",
        retry_count=0,
    )
    db.add(job)
    db.flush()  # get job.id without committing

    # Record the QUEUED event
    event = models.JobEvent(
        job_id=job.id,
        event_type="STATUS_CHANGE",
        new_status="QUEUED",
    )
    db.add(event)
    db.commit()
    db.refresh(job)

    # Enqueue into Redis - ARQ worker will pick it up
    redis = await get_redis()
    await redis.enqueue_job("process_job", str(job.id), _job_id=str(job.id))

    return job


@router.get("/jobs/{job_id}", response_model=schemas.JobResponse)
def get_job(job_id: UUID, user_id: UUID, db: Session = Depends(get_db)):
    """
    Get a specific job. Requires user_id query param to prevent IDOR.
    A user can only see their own jobs.
    """
    job = db.execute(
        select(models.Job).where(
            models.Job.id == job_id,
            models.Job.user_id == user_id,  # Security: ownership check
        )
    ).scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ─── Metrics ─────────────────────────────────────────────────────────────────

@router.get("/metrics", response_model=schemas.MetricsResponse)
def get_metrics(db: Session = Depends(get_db)):
    """Aggregate stats for the dashboard."""
    total_submitted = db.scalar(select(func.count(models.Job.id))) or 0
    total_completed = db.scalar(select(func.count(models.Job.id)).where(models.Job.status == "SUCCESS")) or 0
    total_failed    = db.scalar(select(func.count(models.Job.id)).where(models.Job.status == "FAILED")) or 0
    total_queued    = db.scalar(select(func.count(models.Job.id)).where(models.Job.status == "QUEUED")) or 0
    total_running   = db.scalar(select(func.count(models.Job.id)).where(models.Job.status == "RUNNING")) or 0
    total_retries   = db.scalar(select(func.sum(models.Job.retry_count))) or 0

    # Average execution time in ms from job_executions (only SUCCESS rows)
    avg_ms_result = db.execute(
        select(func.avg(models.JobExecution.execution_time_ms))
        .where(models.JobExecution.status == "SUCCESS")
    ).scalar()
    avg_ms = float(avg_ms_result) if avg_ms_result else 0.0

    success_rate = round((total_completed / total_submitted) * 100.0, 2) if total_submitted > 0 else 0.0

    active_workers = db.scalar(
        select(func.count(models.Worker.id)).where(models.Worker.status == "ACTIVE")
    ) or 0

    return schemas.MetricsResponse(
        total_jobs_submitted=total_submitted,
        total_jobs_completed=total_completed,
        total_jobs_failed=total_failed,
        total_jobs_queued=total_queued,
        total_jobs_running=total_running,
        total_retries=total_retries,
        average_execution_time_ms=avg_ms,
        success_rate_percent=success_rate,
        queue_depth=total_queued,
        active_workers=active_workers,
    )


# ─── Load Test Generator ─────────────────────────────────────────────────────

_load_test_running = False

async def _run_load_test(duration_minutes: int):
    global _load_test_running
    end_time = time.time() + (duration_minutes * 60)
    
    # Ensure load tester exists
    user_id = None
    with SessionLocal() as db:
        user = db.execute(select(models.User).where(models.User.email == "autoloader@example.com")).scalars().first()
        if not user:
            user = models.User(email="autoloader@example.com", name="Auto Loader")
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = user.id

    redis = await get_redis()
    print(f"[LoadTest] Started load generation for {duration_minutes} minutes")
    
    while time.time() < end_time:
        try:
            with SessionLocal() as db:
                job = models.Job(
                    user_id=user_id,
                    payload={"task": "auto_load_test"},
                    status="QUEUED",
                    retry_count=0,
                )
                db.add(job)
                db.flush()
                event = models.JobEvent(
                    job_id=job.id,
                    event_type="STATUS_CHANGE",
                    new_status="QUEUED",
                )
                db.add(event)
                db.commit()
                job_id_str = str(job.id)
                
            await redis.enqueue_job("process_job", job_id_str, _job_id=job_id_str)
        except Exception as e:
            print(f"[LoadTest] error inserting job: {e}")
            
        await asyncio.sleep(0.2) # ~5 jobs per second

    print(f"[LoadTest] Finished")
    _load_test_running = False


@router.post("/loadtest", status_code=202)
def trigger_load_test(body: schemas.LoadTestRequest, background_tasks: BackgroundTasks):
    """Trigger the backend load generator to pump jobs for a specific duration."""
    global _load_test_running
    if _load_test_running:
        raise HTTPException(status_code=400, detail="A load test is already running")
        
    _load_test_running = True
    background_tasks.add_task(_run_load_test, body.duration_minutes)
    return {"message": f"Load test started for {body.duration_minutes} minutes"}

