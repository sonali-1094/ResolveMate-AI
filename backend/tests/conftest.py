import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# main.py creates and seeds its configured database at import time. Use
# in-memory SQLite so importing the app cannot touch the demo database or leave
# a locked temporary file behind on Windows.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AI_PROVIDER"] = "openai"

import main  # noqa: E402


@pytest.fixture
def client(tmp_path):
    """Provide an isolated SQLite database and FastAPI client per test."""
    main.provider_status = "not_checked"
    main.provider_error_category = None
    main.provider_http_status = None
    main.provider_error_stage = None
    main.provider_exception_class = None
    main.provider_response_content_type = None
    database_path = tmp_path / "test.db"
    test_engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    main.Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False)

    with TestSession() as session:
        session.add_all(
            [
                main.Transaction(
                    id="TXN1001",
                    amount=500,
                    status="SUCCESS",
                    method="UPI",
                    description="Sample successful payment",
                ),
                main.Transaction(
                    id="TXN1002",
                    amount=250,
                    status="PENDING",
                    method="UPI",
                    description="Sample pending payment",
                ),
            ]
        )
        session.commit()

    def override_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[main.db] = override_db
    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        main.app.dependency_overrides.pop(main.db, None)
        test_engine.dispose()
