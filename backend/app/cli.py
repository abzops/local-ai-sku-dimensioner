"""Small dependency-free operational commands for Windows scripts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import get_settings
from backend.app.database import Database


def healthcheck() -> int:
    """Check the configured database without starting an HTTP server."""
    settings = get_settings()
    database: Database | None = None
    try:
        database = Database(settings.resolved_database_url)
        revision = database.check_readiness()
    except (OSError, RuntimeError, SQLAlchemyError, ValueError):
        print(json.dumps({"status": "error", "code": "DATABASE_UNAVAILABLE"}))
        return 1
    finally:
        if database is not None:
            database.dispose()

    print(json.dumps({"status": "ok", "database_revision": revision}))
    return 0


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local AI SKU Dimensioner operations")
    parser.add_argument("command", choices=["healthcheck"])
    arguments = parser.parse_args(argv)
    if arguments.command == "healthcheck":
        return healthcheck()
    return 2


if __name__ == "__main__":
    raise SystemExit(run())
