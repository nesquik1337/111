from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass
class User:
    user_id: int
    username: str | None
    full_name: str


@dataclass
class Request:
    id: int
    creator_id: int
    creator_name: str
    game: str
    play_time: str
    created_at: str


@dataclass
class RequestResponse:
    request_id: int
    user_id: int
    username: str | None
    full_name: str
    response: str


class Storage:
    def __init__(self, db_path: str = "bot.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    play_time TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (creator_id) REFERENCES users (user_id)
                );

                CREATE TABLE IF NOT EXISTS responses (
                    request_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    response TEXT NOT NULL CHECK (response IN ('yes', 'no')),
                    answered_at TEXT NOT NULL,
                    PRIMARY KEY (request_id, user_id),
                    FOREIGN KEY (request_id) REFERENCES requests (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                );
                """
            )

    def upsert_user(self, user_id: int, username: str | None, full_name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users(user_id, username, full_name, is_active, created_at)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    full_name=excluded.full_name,
                    is_active=1
                """,
                (user_id, username, full_name, datetime.utcnow().isoformat()),
            )

    def create_request(self, creator_id: int, game: str, play_time: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO requests(creator_id, game, play_time, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (creator_id, game, play_time, datetime.utcnow().isoformat()),
            )
            return int(cur.lastrowid)

    def get_user(self, user_id: int) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, full_name FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return User(row["user_id"], row["username"], row["full_name"])

    def get_other_users(self, user_id: int) -> list[User]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, username, full_name
                FROM users
                WHERE user_id != ? AND is_active = 1
                ORDER BY full_name ASC
                """,
                (user_id,),
            ).fetchall()
            return [User(r["user_id"], r["username"], r["full_name"]) for r in rows]

    def save_response(self, request_id: int, user_id: int, response: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO responses(request_id, user_id, response, answered_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(request_id, user_id) DO UPDATE SET
                    response=excluded.response,
                    answered_at=excluded.answered_at
                """,
                (request_id, user_id, response, datetime.utcnow().isoformat()),
            )

    def get_request(self, request_id: int) -> Request | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT r.id, r.creator_id, u.full_name AS creator_name, r.game, r.play_time, r.created_at
                FROM requests r
                JOIN users u ON u.user_id = r.creator_id
                WHERE r.id = ?
                """,
                (request_id,),
            ).fetchone()
            if not row:
                return None
            return Request(
                id=row["id"],
                creator_id=row["creator_id"],
                creator_name=row["creator_name"],
                game=row["game"],
                play_time=row["play_time"],
                created_at=row["created_at"],
            )

    def get_request_responses(self, request_id: int) -> list[RequestResponse]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT resp.request_id, resp.user_id, u.username, u.full_name, resp.response
                FROM responses resp
                JOIN users u ON u.user_id = resp.user_id
                WHERE resp.request_id = ?
                ORDER BY u.full_name ASC
                """,
                (request_id,),
            ).fetchall()
            return [
                RequestResponse(
                    request_id=r["request_id"],
                    user_id=r["user_id"],
                    username=r["username"],
                    full_name=r["full_name"],
                    response=r["response"],
                )
                for r in rows
            ]

    def get_creator_requests(self, creator_id: int, limit: int = 10) -> list[Request]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.creator_id, u.full_name AS creator_name, r.game, r.play_time, r.created_at
                FROM requests r
                JOIN users u ON u.user_id = r.creator_id
                WHERE r.creator_id = ?
                ORDER BY r.id DESC
                LIMIT ?
                """,
                (creator_id, limit),
            ).fetchall()
            return [
                Request(
                    id=r["id"],
                    creator_id=r["creator_id"],
                    creator_name=r["creator_name"],
                    game=r["game"],
                    play_time=r["play_time"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]
