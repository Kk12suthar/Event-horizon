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
database_name = os.getenv("POSTGRES_UPLOAD_DBNAME")
db_host = os.getenv("POSTGRES_HOST")
db_port = os.getenv("POSTGRES_PORT")
driver = "psycopg2"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SECURITY FIX-009: Database connection configuration
# Connection pooling and timeout settings for stability and security
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_POOL_MAX_OVERFLOW = int(os.getenv("DB_POOL_MAX_OVERFLOW", "5"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))
DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))

try:
    SQLALCHEMY_DATABASE_URL = (
        f"postgresql+{driver}://{username}:{password}@{db_host}:{db_port}/{database_name}"
        f"?connect_timeout={DB_CONNECT_TIMEOUT}"
    )
    
    # Create engine with connection pooling and timeout settings
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_POOL_MAX_OVERFLOW,
        pool_timeout=DB_POOL_TIMEOUT,
        pool_recycle=DB_POOL_RECYCLE,
        pool_pre_ping=True,  # Test connections before using them
        echo=False,  # Set to True for SQL debugging
    )

    # Test the connection
    with engine.connect() as connection:
        logger.info("✅ Successfully connected to the database")
        logger.info(f"   Pool size: {DB_POOL_SIZE}, Max overflow: {DB_POOL_MAX_OVERFLOW}")
        logger.info(f"   Connection timeout: {DB_CONNECT_TIMEOUT}s, Pool timeout: {DB_POOL_TIMEOUT}s")
except Exception as e:
    logger.error(f"❌ Failed to connect to database: {str(e)}")
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
