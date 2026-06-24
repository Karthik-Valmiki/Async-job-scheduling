import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from .api import router

app = FastAPI(
    title="Reliable Job Lifecycle Manager",
    description="Fault-tolerant async job scheduling system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# Serve the frontend static files
_base = os.path.dirname(os.path.dirname(__file__))
_frontend = os.path.join(_base, "frontend")

app.mount("/static", StaticFiles(directory=_frontend), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(_frontend, "index.html"))
