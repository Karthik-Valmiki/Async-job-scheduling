import subprocess
import time
import sys
import os

print("Starting services...")

env = os.environ.copy()
venv_python = r".\venv\Scripts\python.exe"
venv_uvicorn = r".\venv\Scripts\uvicorn.exe"
venv_arq = r".\venv\Scripts\arq.exe"

api_log = open("api.log", "w")
api_proc = subprocess.Popen([venv_uvicorn, "app.main:app", "--host", "127.0.0.1", "--port", "8000"], stdout=api_log, stderr=subprocess.STDOUT, env=env)

arq_log = open("arq.log", "w")
arq_proc = subprocess.Popen([venv_arq, "app.worker.WorkerSettings"], stdout=arq_log, stderr=subprocess.STDOUT, env=env)

watchdog_log = open("watchdog.log", "w")
watchdog_proc = subprocess.Popen([venv_python, "app/watchdog.py"], stdout=watchdog_log, stderr=subprocess.STDOUT, env=env)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping services...")
    api_proc.terminate()
    arq_proc.terminate()
    watchdog_proc.terminate()
    api_log.close()
    arq_log.close()
    watchdog_log.close()
