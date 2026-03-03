from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()


def _set_search_path(dbapi_conn, connection_record):
    cur = dbapi_conn.cursor()
    try:
        cur.execute("SET search_path TO public")
    finally:
        cur.close()


engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    future=True,
)
event.listen(engine.sync_engine, "connect", _set_search_path)

async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    """Database dependency."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()