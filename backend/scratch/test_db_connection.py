import os
from dotenv import load_dotenv
from services.database import DatabaseService

load_dotenv()

def test_connection():
    print(f"Testing connection to: {os.getenv('DATABASE_URL')}")
    try:
        db = DatabaseService()
        print("Successfully connected to the database!")
        print("Creating tables...")
        db.create_tables()
        print("Tables created successfully!")
    except Exception as e:
        print(f"Failed to connect: {e}")

if __name__ == "__main__":
    test_connection()
