import subprocess
import time
import sys
import os

print("Starting services...")

env = os.environ.copy()
venv_python = r".\venv\Scripts\python.exe"
venv_uvicorn = r".\venv\Scripts\uvicorn.exe"
venv_arq = r".\venv\Scripts\arq.exe"

api_proc = subprocess.Popen([venv_uvicorn, "app.main:app", "--host", "127.0.0.1", "--port", "8000"], env=env)

arq_proc = subprocess.Popen([venv_arq, "app.worker.WorkerSettings"], env=env)

watchdog_proc = subprocess.Popen([venv_python, "app/watchdog.py"], env=env)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping services...")
    api_proc.terminate()
    arq_proc.terminate()
    watchdog_proc.terminate()
