"""数据库连接与会话管理。

按 .env 的 DB_BACKEND 策略选择后端：
- mysql  : 强制 MySQL，连不上直接报错
- sqlite : 强制本地 SQLite（零依赖，便于单机开发）
- auto   : 先试 MySQL，失败自动降级 SQLite
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("webmind.db")


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明基类。"""


_engine: Engine | None = None
_session_factory: sessionmaker | None = None
_active_backend: str | None = None


def _mysql_url() -> str:
    return (
        f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}"
        f"@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}"
        f"?charset=utf8mb4"
    )


def _sqlite_url() -> str:
    path = settings.resolve_file(settings.SQLITE_PATH)
    return f"sqlite:///{path.as_posix()}"


def _build_engine(url: str, **kwargs) -> Engine:
    if url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True, future=True, **kwargs)


def _probe(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("数据库连接探测失败: %s", exc)
        engine.dispose()
        return False


def get_engine() -> Engine:
    global _engine, _active_backend
    if _engine is not None:
        return _engine

    backend = (settings.DB_BACKEND or "auto").lower()

    if backend == "mysql":
        engine = _build_engine(_mysql_url())
        if not _probe(engine):
            raise RuntimeError("MySQL 不可用，请检查 .env 中的 MYSQL_* 配置或启动 Docker 服务")
        _engine, _active_backend = engine, "mysql"
    elif backend == "sqlite":
        _engine, _active_backend = _build_engine(_sqlite_url()), "sqlite"
    else:
        engine = _build_engine(_mysql_url(), pool_recycle=3600)
        if _probe(engine):
            _engine, _active_backend = engine, "mysql"
            logger.info("数据库后端: MySQL(%s:%s)", settings.MYSQL_HOST, settings.MYSQL_PORT)
        else:
            logger.warning("MySQL 不可用，已降级为本地 SQLite（单机开发模式）")
            _engine, _active_backend = _build_engine(_sqlite_url()), "sqlite"

    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False
        )
    return _session_factory


def active_backend() -> str:
    get_engine()
    return _active_backend or "unknown"


@contextmanager
def session_scope() -> Iterator[Session]:
    """提供事务性会话，退出时自动提交/回滚。"""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """建表并写入默认演示数据。"""
    from app.models.entities import Project, User  # 局部导入避免循环依赖

    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("数据库初始化完成，后端=%s", active_backend())

    with session_scope() as session:
        if session.query(User).count() == 0:
            session.add(User(username="admin", display_name="平台管理员", role="admin"))
        if session.query(Project).count() == 0:
            session.add_all(
                [
                    Project(name="工具软件线", code="TOOLS", description="内部工具 / 运营后台"),
                    Project(name="应用软件线", code="APP", description="业务应用"),
                    Project(name="社交软件线", code="SOCIAL", description="互动 / 活动向"),
                ]
            )
