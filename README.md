# Async Job Scheduling System

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?logo=redis&logoColor=white)](https://redis.io/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-%23316192.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

Provides fault-tolerant asynchronous job execution across distributed worker nodes with at-least-once delivery guarantees and strict execution auditing. This system solves the problem of "zombie" or "orphaned" jobs caused by worker crashes by separating the ephemeral transport layer (Redis) from a durable, strictly consistent state store (PostgreSQL), utilizing a separate watchdog process to detect stalled heartbeats and safely re-queue orphaned workloads.

## Architecture

```text
                     ┌─────────────┐
                     │ API Clients │
                     └──────┬──────┘
                            │ (REST / JSON)
                            ▼
                    ┌──────────────┐
                    │   FastAPI    │
                    │ API Layer    │
                    └──────┬───────┘
                           │ 1. Persist (QUEUED)
                           ▼
                  ┌──────────────────┐
                  │ PostgreSQL       │ <── Source Of Truth (State & Audit)
                  └──────┬───────────┘
                         │ 2. Push Job ID
                         ▼
                  ┌──────────────┐
                  │ Redis Queue  │ <── Ephemeral Transport
                  └──────┬───────┘
                         │ 3. Pull Job ID
                         ▼
                 ┌────────────────┐
                 │ ARQ Workers    │ <── Async Execution
                 └──────┬─────────┘
                        │ 4. Heartbeats & Status
                        ▼
                  PostgreSQL Update
```

The key design decision is decoupling the job payload and state from the message queue. Redis acts strictly as an ephemeral transport mechanism pushing `job_id`s, while PostgreSQL retains absolute authority over the job state machine. If Redis crashes or drops data, no jobs are lost because the authoritative state resides in PostgreSQL, allowing the watchdog to reconcile and re-queue any jobs stuck in `RUNNING` without active worker heartbeats.

## Tech Stack

| Component | Choice | Why |
| :--- | :--- | :--- |
| API | FastAPI | Native asyncio support and strict type-hinting/validation for job payloads. |
| Database | PostgreSQL | ACID compliance guarantees job state transitions are strictly consistent, crucial for accurate auditing. |
| Message Broker | Redis | Lightweight, fast in-memory transport layer for pushing job IDs to workers. |
| Task Queue | ARQ | High-performance Python `asyncio` task queue designed specifically for Redis. |

## Getting Started

### Prerequisites
- Python 3.10+
- PostgreSQL server running locally
- Redis server running locally

### Installation
```bash
git clone <repository_url>
cd Async-job-scheduling
python -m venv venv

# Windows
.\venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

pip install -r requirements.txt
```

### Environment Variables
Copy `.env.example` to `.env` or create a new `.env` file in the root directory:

```env
# Example configuration for local development
DATABASE_URL=postgresql://postgres:password@localhost/async_jobs
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=local_development_secret_do_not_use_in_prod
ALGORITHM=HS256
```

Ensure you create the database in PostgreSQL before running:
```bash
psql -U postgres -c "CREATE DATABASE async_jobs;"
```

### Running Locally
Start the FastAPI server, ARQ worker, and Watchdog service simultaneously:
```bash
python run_all.py
```

### Verifying It Works
To verify the API is responsive, check the health/documentation endpoint:
```bash
curl -I http://127.0.0.1:8000/docs
```
*(Expected: HTTP 200 OK)*

You can also submit a job (requires a valid JWT obtained via `/token`) or view the observability dashboard by opening `frontend/index.html` in your browser.

## Security

**Implemented:**
- **Multi-tenant Data Isolation:** Every API request verifies job ownership (`job_id` AND `user_id`). Users cannot access or enumerate jobs belonging to other tenants.
- **Resource Identifiers:** UUIDv4 is used for all primary keys (`user_id`, `job_id`, `worker_id`) to prevent Insecure Direct Object Reference (IDOR) attacks via ID enumeration.
- **Authentication:** Standard JWT-based authentication for API access with salted password hashing.

**Explicitly Out of Scope:**
- Rate limiting / DDoS protection (assumes API gateway/WAF in production).
- Secret rotation mechanisms.
- SSL/TLS termination (delegated to reverse proxy).

## Known Limitations & Tradeoffs

- **Single Point of Failure (Watchdog):** The watchdog script currently runs as a single process. In a high-availability production environment, this would require distributed locking (e.g., Redlock) to allow multiple watchdogs to run concurrently without causing race conditions on job re-queueing.
- **Database Write Bottleneck:** Because PostgreSQL tracks every heartbeat and granular state transition, write contention will become the primary bottleneck at very high scale. At that scale, heartbeats should be offloaded to an in-memory store (Redis) with periodic batch flushing to Postgres.
- **No Global Worker Registry:** Workers are tracked entirely through implicit heartbeats. There is no central orchestrator cleanly scaling workers up or down based on queue depth.
