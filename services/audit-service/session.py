from __future__ import annotations
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from wcag_common import BaseServiceSettings

class Base(DeclarativeBase):
    pass

class AuditServiceSettings(BaseServiceSettings):
    service_name: str = "audit-service"

settings = AuditServiceSettings()

sync_engine = create_engine(settings.sync_database_url, echo=False)
async_engine = create_async_engine(settings.async_database_url, echo=False)
async_session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

async def get_async_db():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
