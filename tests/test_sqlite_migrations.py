"""Migration failures must not leave unrecorded schema changes behind."""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

import aiosqlite
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlite_migrations import (
    SQLiteMigration,
    apply_async_sqlite_migrations,
    apply_sqlite_migrations,
)

BROKEN_MIGRATION = (
    SQLiteMigration(1, "broken", ("CREATE TABLE example (id INTEGER)", "INVALID SQL")),
)


def test_failed_sync_migration_rolls_back_schema(tmp_path):
    conn = sqlite3.connect(tmp_path / "migration.db")
    try:
        with pytest.raises(sqlite3.OperationalError), conn:
            apply_sqlite_migrations(conn, "test", BROKEN_MIGRATION)
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'example'"
        ).fetchone() is None
        apply_sqlite_migrations(conn, "test", (
            SQLiteMigration(1, "fixed", ("CREATE TABLE example (id INTEGER)",)),
        ))
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_failed_async_migration_rolls_back_schema(tmp_path):
    async with aiosqlite.connect(tmp_path / "migration.db") as db:
        with pytest.raises(sqlite3.OperationalError):
            await apply_async_sqlite_migrations(db, "test", BROKEN_MIGRATION)
        await db.rollback()
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE name = 'example'"
        ) as cursor:
            assert await cursor.fetchone() is None
        await apply_async_sqlite_migrations(db, "test", (
            SQLiteMigration(1, "fixed", ("CREATE TABLE example (id INTEGER)",)),
        ))
        await db.commit()


def test_migration_respects_existing_caller_transaction(tmp_path):
    conn = sqlite3.connect(tmp_path / "migration.db")
    try:
        conn.execute("CREATE TABLE caller (id INTEGER)")
        conn.execute("INSERT INTO caller VALUES (1)")
        apply_sqlite_migrations(conn, "test", (
            SQLiteMigration(1, "example", ("CREATE TABLE example (id INTEGER)",)),
        ))
        conn.rollback()
        assert conn.execute("SELECT * FROM caller").fetchall() == []
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'example'"
        ).fetchone() is None
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_concurrent_migrations_apply_only_once(tmp_path):
    path = tmp_path / "migration.db"
    migrations = (
        SQLiteMigration(1, "example", ("CREATE TABLE example (id INTEGER)",)),
    )

    async def initialize():
        async with aiosqlite.connect(path) as db:
            await apply_async_sqlite_migrations(db, "test", migrations)
            await db.commit()

    await asyncio.gather(*(initialize() for _ in range(4)))
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE namespace = 'test'"
        ) as cursor:
            assert await cursor.fetchone() == (1,)
