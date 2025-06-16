import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text
import os
from decouple import config

# Database configuration
DATABASE_URL = config(
    'DATABASE_URL', 
    default='postgresql+asyncpg://postgres:password@localhost:5432/tag_autocomplete'
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=config('DB_ECHO', default=False, cast=bool),
    pool_size=20,
    max_overflow=30,
    pool_timeout=30,
    pool_recycle=3600,
    future=True
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get database session
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    Initialize database with required extensions and tables
    """
    from app.models.tag import Base
    
    async with engine.begin() as conn:
        # Create pg_trgm extension for fuzzy search
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """
    Close database connections
    """
    await engine.dispose()