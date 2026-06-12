import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["MOCK_LLM"] = "true"
os.environ["PUBLISH_DRY_RUN"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.base as db_base
from app.db.base import Base


@pytest.fixture()
def db_engine(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_base, "engine", engine)
    monkeypatch.setattr(db_base, "SessionLocal", TestSession)
    # 라우터들이 SessionLocal을 직접 import하므로 그것도 패치
    import app.routers.generation as gen_router
    import app.routers.publish as pub_router
    monkeypatch.setattr(gen_router, "SessionLocal", TestSession)
    monkeypatch.setattr(pub_router, "SessionLocal", TestSession)
    yield engine


@pytest.fixture()
def db(db_engine):
    TestSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    from app.db.base import get_db
    from app.main import create_app

    app = create_app()
    TestSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
