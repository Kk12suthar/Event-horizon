from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import logging
import os
from env import load_environment
from pathlib import Path

load_environment()

# Database configuration
username = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")
database_name = os.getenv("POSTGRES_CHARTS_DB_NAME")
db_host = os.getenv("POSTGRES_HOST")
db_port = os.getenv("POSTGRES_PORT")
driver = "psycopg2"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    SQLALCHEMY_DATABASE_URL = (
        f"postgresql+{driver}://{username}:{password}@{db_host}:{db_port}/{database_name}"
    )
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

    # Test the connection
    with engine.connect() as connection:
        logger.info("Successfully connected to the database")
except Exception as e:
    logger.error(f"Failed to connect to database: {str(e)}")
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    Dependency to get a database session.
    Ensures the session is closed after the request is finished.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
