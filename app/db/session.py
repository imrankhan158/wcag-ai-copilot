import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

host = os.getenv("POSTGRES_HOST", "localhost")
port = os.getenv("POSTGRES_PORT", "5432")
db = os.getenv("POSTGRES_DB", "wcag_ai")
user = os.getenv("POSTGRES_USER", "admin")
pw = os.getenv("POSTGRES_PASSWORD", "admin123")

# Database connection configurations
SYNC_DATABASE_URL = f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}"
ASYNC_DATABASE_URL = f"postgresql+asyncpg://{user}:{pw}@{host}:{port}/{db}"

# Async engine for FastAPI routing
async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)

# Sync engine for startup table metadata initialization
sync_engine = create_engine(SYNC_DATABASE_URL, echo=False)

async_session_maker = sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


async def get_async_db():
    """Dependency to provide database session to async endpoints."""
    async with async_session_maker() as session:
        yield session
