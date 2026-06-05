from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .settings import DbSettings

__all__ = ["create_engine", "create_session_factory"]


def create_engine(settings: DbSettings) -> AsyncEngine:
    return create_async_engine(settings.dsn, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
