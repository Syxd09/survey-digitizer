import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    print("DATABASE_URL not found in .env")
    exit(1)

# Fix for Supabase PgBouncer (add ?sslmode=disable if needed, but usually pooled connections are fine)
if "pooler.supabase.com" in DB_URL:
    print("Detected Supabase Pooler. Attempting connection...")

try:
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version();"))
        print(f"Connection Successful! Postgres version: {result.fetchone()[0]}")
except Exception as e:
    print(f"Connection Failed: {e}")
