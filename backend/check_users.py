"""Quick dev script: list the first 10 users in the database.

Reads connection details from the environment (see .env.example) instead of
hardcoding credentials. Run from the backend/ directory:

    python check_users.py
"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

conn = psycopg2.connect(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=os.environ.get("POSTGRES_PORT", "5432"),
    user=os.environ.get("POSTGRES_USER", "postgres"),
    password=os.environ.get("POSTGRES_PASSWORD"),
    dbname=os.environ.get("POSTGRES_METADATA_DBNAME", "postgres"),
)
cur = conn.cursor()
cur.execute("SELECT id, name, email FROM instance01.mtd_users LIMIT 10")
print("Users in database:")
for row in cur.fetchall():
    print(f"  ID: {row[0]}, Name: {row[1]}, Email: {row[2]}")
cur.close()
conn.close()
