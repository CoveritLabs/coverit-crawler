from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def _query_value(value) -> str:
    if isinstance(value, tuple):
        return str(value[-1])
    return str(value)


def create_engine(database_url: str) -> AsyncEngine:
    url = make_url(database_url)
    connect_args = {}

    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")

    schema = url.query.get("schema")
    if schema:
        connect_args["server_settings"] = {"search_path": _query_value(schema)}

    sslmode = url.query.get("sslmode")
    if sslmode:
        connect_args["ssl"] = _query_value(sslmode).lower() not in {"disable", "allow", "prefer"}

    connect_timeout = url.query.get("connect_timeout")
    if connect_timeout:
        connect_args["timeout"] = float(_query_value(connect_timeout))

    url = url.difference_update_query(
        [
            "schema",
            "sslmode",
            "connect_timeout",
            "connection_limit",
            "pool_timeout",
            "pgbouncer",
            "channel_binding",
            "target_session_attrs",
        ]
    )
    return create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
