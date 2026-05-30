"""
راه‌اندازی پایه‌ی دیتابیس با SQLAlchemy async.
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.db_url_normalized,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """ساخت جداول (در شروع یا توسعه)."""
    import logging
    logger = logging.getLogger("moonax.db")
    url = settings.db_url_normalized
    # لاگ URL بدون پسورد
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        safe = f"{p.scheme}://{p.username}:***@{p.hostname}:{p.port}{p.path}"
        logger.info(f"Connecting to DB: {safe}")
    except Exception:
        pass
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """یک session جدید برمی‌گرداند."""
    return AsyncSessionLocal()
