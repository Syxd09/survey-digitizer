from celery import Celery
import os
import socket
import logging

logger = logging.getLogger(__name__)

# Configure Celery to use Redis as the broker and backend
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Safety Check: Can we even reach Redis?
def check_redis():
    try:
        host = REDIS_URL.split("//")[1].split(":")[0]
        port = int(REDIS_URL.split(":")[1].split("/")[0])
        s = socket.socket(socket.getaddrinfo(host, port)[0][0], socket.getaddrinfo(host, port)[0][1])
        s.settimeout(1)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False

HAS_REDIS = check_redis()

if HAS_REDIS:
    logger.info(f"[CELERY] Redis detected at {REDIS_URL}. Initializing heavy task queue.")
    celery_app = Celery(
        "survey_digitizer",
        broker=REDIS_URL,
        backend=REDIS_URL,
        include=["tasks"]
    )
else:
    logger.warning("[CELERY] Redis unreachable. Initializing in infrastructure-lite mode (Fallbacks enabled).")
    # We initialize without broker/backend to prevent the CRITICAL crash
    celery_app = Celery("survey_digitizer", include=["tasks"])

# Optional configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300, # 5 minutes max per form
)
