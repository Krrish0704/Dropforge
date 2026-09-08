import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    """FastAPI dependency to yield a database session."""
    async with AsyncSessionLocal() as session:
        yield session

async def set_tenant_context(session: AsyncSession, tenant_id: str):
    """
    Enforces PostgreSQL Row-Level Security (RLS) for the current transaction.
    Every query on this session will now be restricted to this tenant_id.
    """
    await session.execute(text("SET LOCAL app.current_tenant = :tenant_id"), {"tenant_id": tenant_id})