# outfitai_project/db/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator

# --- CORRECTED IMPORT PATH ---
# From: from ..config.settings import settings
# To:   from config.settings import settings  (Absolute import from project root)
from config.settings import settings

engine = create_async_engine(
    settings.DATABASE_URL,
)

AsyncSessionLocal = async_sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    class_=AsyncSession
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session