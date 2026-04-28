"""
Phase 9/15 — Storage & Data Model (SQLAlchemy / Supabase)
=========================================================
Singleton provider for DatabaseService.
"""

import os
from services.database import DatabaseService

_db_instance = None

def get_db_service() -> DatabaseService:
    """Singleton provider for DatabaseService."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseService(os.getenv("DATABASE_URL"))
        _db_instance.create_tables()
    return _db_instance

