"""
WSGI entry point for production (Gunicorn on Railway).
Local dev: use `python main.py` instead.
"""

from database.connection import init_db
from app import create_app

try:
    init_db()
except Exception as e:
    print(f"[wsgi] DB init note: {e}")

try:
    from data_collection.scheduler import start_scheduler
    start_scheduler()
except Exception:
    pass

app = create_app()
