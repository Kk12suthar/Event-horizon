"""Quick dev script: create a default admin user if one doesn't already exist.

Reads connection details from the environment (see .env.example) instead of
hardcoding credentials. Run from the backend/ directory:

    python create_user.py
"""

import os

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

host = os.environ.get("POSTGRES_HOST", "localhost")
port = os.environ.get("POSTGRES_PORT", "5432")
user = os.environ.get("POSTGRES_USER", "postgres")
password = os.environ.get("POSTGRES_PASSWORD")
dbname = os.environ.get("POSTGRES_METADATA_DBNAME", "postgres")

DATABASE_URL = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        # Check if user already exists
        check_query = text("""
            SELECT id, name, email FROM instance01.mtd_users
            WHERE id = '550e8400-e29b-41d4-a716-446655440001'
        """)
        result = conn.execute(check_query).fetchone()

        if result:
            print(f"User already exists:")
            print(f"  ID: {result[0]}")
            print(f"  Name: {result[1]}")
            print(f"  Email: {result[2]}")
        else:
            # Create the user
            insert_query = text("""
                INSERT INTO instance01.mtd_users (id, name, email, role)
                VALUES (
                    '550e8400-e29b-41d4-a716-446655440001',
                    'Default User',
                    'user@example.com',
                    'ADMIN'
                )
            """)
            conn.execute(insert_query)
            conn.commit()
            print("[OK] User created successfully!")
            print("  ID: 550e8400-e29b-41d4-a716-446655440001")
            print("  Name: Default User")
            print("  Email: user@example.com")

except Exception as e:
    print(f"Error: {e}")
finally:
    engine.dispose()
