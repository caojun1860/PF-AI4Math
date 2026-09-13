from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BudgetConfig, NANOCNY_PER_CNY


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BudgetExceeded(RuntimeError):
    def __init__(self, dimension: str, used: int, reserved: int, requested: int, limit: int):
        self.dimension = dimension
        self.used = used
        self.reserved = reserved
        self.requested = requested
        self.limit = limit
        super().__init__(f"{dimension} 预算不足")


@dataclass(frozen=True)
class Reservation:
    request_id: str
    budget_id: str
    alias: str
    input_estimate: int
    max_output: int
    reserved_tokens: int
    reserved_cny_nano: int


class BudgetLedger:
    """SQLite 原子预算账本，不保存 prompt 或 completion 内容。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS budgets (
                    id TEXT PRIMARY KEY,
                    token_limit INTEGER NOT NULL,
                    cny_limit_nano INTEGER NOT NULL,
                    request_limit INTEGER NOT NULL,
                    used_tokens INTEGER NOT NULL DEFAULT 0,
                    reserved_tokens INTEGER NOT NULL DEFAULT 0,
                    used_cny_nano INTEGER NOT NULL DEFAULT 0,
                    reserved_cny_nano INTEGER NOT NULL DEFAULT 0,
                    used_requests INTEGER NOT NULL DEFAULT 0,
                    reserved_requests INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    budget_id TEXT NOT NULL REFERENCES budgets(id),
                    alias TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_estimate INTEGER NOT NULL,
                    max_output INTEGER NOT NULL,
                    reserved_tokens INTEGER NOT NULL,
                    reserved_cny_nano INTEGER NOT NULL,
                    actual_input INTEGER,
                    actual_output INTEGER,
                    actual_tokens INTEGER,
                    actual_cny_nano INTEGER,
                    error_type TEXT,
                    created_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_requests_budget_created
                ON requests(budget_id, created_at DESC);
                """
            )

    def configure_budget(self, config: BudgetConfig) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO budgets (
                    id, token_limit, cny_limit_nano, request_limit, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    config.budget_id,
                    config.total_tokens,
                    config.total_cny_nano,
                    config.total_requests,
                    _now(),
                ),
            )
            connection.commit()

    def recover_reservations(self, *, error_type: str) -> int:
        """崩溃或关闭后，将无法确认结果的预留按最坏值结算。"""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            groups = connection.execute(
                """
                SELECT budget_id, COUNT(*) AS request_count,
                       SUM(reserved_tokens) AS tokens,
                       SUM(reserved_cny_nano) AS cny_nano
                FROM requests WHERE status = 'reserved'
                GROUP BY budget_id
                """
            ).fetchall()
            recovered = 0
            for group in groups:
                count = int(group["request_count"])
                connection.execute(
                    """
                    UPDATE budgets SET
                        reserved_tokens = reserved_tokens - ?,
                        reserved_cny_nano = reserved_cny_nano - ?,
                        reserved_requests = reserved_requests - ?,
                        used_tokens = used_tokens + ?,
                        used_cny_nano = used_cny_nano + ?,
                        used_requests = used_requests + ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        group["tokens"],
                        group["cny_nano"],
                        count,
                        group["tokens"],
                        group["cny_nano"],
                        count,
                        _now(),
                        group["budget_id"],
                    ),
                )
                recovered += count
            if recovered:
                connection.execute(
                    """
                    UPDATE requests SET
                        status = 'uncertain',
                        actual_input = input_estimate,
                        actual_output = max_output,
                        actual_tokens = reserved_tokens,
                        actual_cny_nano = reserved_cny_nano,
                        error_type = ?,
                        finished_at = ?
                    WHERE status = 'reserved'
                    """,
                    (error_type, _now()),
                )
            connection.commit()
        return recovered

    def reserve(
        self,
        *,
        request_id: str,
        budget_id: str,
        alias: str,
        input_estimate: int,
        max_output: int,
        input_nano_per_token: int,
        output_nano_per_token: int,
    ) -> Reservation:
        reserved_tokens = input_estimate + max_output
        reserved_cost = input_estimate * input_nano_per_token + max_output * output_nano_per_token
        reservation = Reservation(
            request_id=request_id,
            budget_id=budget_id,
            alias=alias,
            input_estimate=input_estimate,
            max_output=max_output,
            reserved_tokens=reserved_tokens,
            reserved_cny_nano=reserved_cost,
        )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(f"未知预算：{budget_id}")

            checks = (
                ("token", row["used_tokens"], row["reserved_tokens"], reserved_tokens, row["token_limit"]),
                ("cny_nano", row["used_cny_nano"], row["reserved_cny_nano"], reserved_cost, row["cny_limit_nano"]),
                ("request", row["used_requests"], row["reserved_requests"], 1, row["request_limit"]),
            )
            for dimension, used, reserved, requested, limit in checks:
                if used + reserved + requested > limit:
                    connection.rollback()
                    raise BudgetExceeded(dimension, used, reserved, requested, limit)

            connection.execute(
                """
                INSERT INTO requests (
                    request_id, budget_id, alias, status, input_estimate,
                    max_output, reserved_tokens, reserved_cny_nano, created_at
                ) VALUES (?, ?, ?, 'reserved', ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    budget_id,
                    alias,
                    input_estimate,
                    max_output,
                    reserved_tokens,
                    reserved_cost,
                    _now(),
                ),
            )
            connection.execute(
                """
                UPDATE budgets SET
                    reserved_tokens = reserved_tokens + ?,
                    reserved_cny_nano = reserved_cny_nano + ?,
                    reserved_requests = reserved_requests + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (reserved_tokens, reserved_cost, _now(), budget_id),
            )
            connection.commit()
        return reservation

    def settle(
        self,
        reservation: Reservation,
        *,
        actual_input: int,
        actual_output: int,
        input_nano_per_token: int,
        output_nano_per_token: int,
        status: str = "complete",
        error_type: str | None = None,
    ) -> None:
        actual_input = max(0, int(actual_input))
        actual_output = max(0, int(actual_output))
        self._finish(
            reservation,
            actual_input=actual_input,
            actual_output=actual_output,
            actual_tokens=actual_input + actual_output,
            actual_cost=actual_input * input_nano_per_token + actual_output * output_nano_per_token,
            status=status,
            error_type=error_type,
        )

    def settle_reserved(
        self,
        reservation: Reservation,
        *,
        status: str,
        error_type: str | None = None,
    ) -> None:
        """用预留值结算缺少 usage 的流式或结果不确定请求。"""
        self._finish(
            reservation,
            actual_input=reservation.input_estimate,
            actual_output=reservation.max_output,
            actual_tokens=reservation.reserved_tokens,
            actual_cost=reservation.reserved_cny_nano,
            status=status,
            error_type=error_type,
        )

    def _finish(
        self,
        reservation: Reservation,
        *,
        actual_input: int,
        actual_output: int,
        actual_tokens: int,
        actual_cost: int,
        status: str,
        error_type: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM requests WHERE request_id = ?",
                (reservation.request_id,),
            ).fetchone()
            if row is None or row["status"] != "reserved":
                connection.rollback()
                raise RuntimeError("请求不存在或已经结算")
            connection.execute(
                """
                UPDATE budgets SET
                    reserved_tokens = reserved_tokens - ?,
                    reserved_cny_nano = reserved_cny_nano - ?,
                    reserved_requests = reserved_requests - 1,
                    used_tokens = used_tokens + ?,
                    used_cny_nano = used_cny_nano + ?,
                    used_requests = used_requests + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    reservation.reserved_tokens,
                    reservation.reserved_cny_nano,
                    actual_tokens,
                    actual_cost,
                    _now(),
                    reservation.budget_id,
                ),
            )
            connection.execute(
                """
                UPDATE requests SET
                    status = ?, actual_input = ?, actual_output = ?,
                    actual_tokens = ?, actual_cny_nano = ?, error_type = ?,
                    finished_at = ?
                WHERE request_id = ?
                """,
                (
                    status,
                    actual_input,
                    actual_output,
                    actual_tokens,
                    actual_cost,
                    error_type,
                    _now(),
                    reservation.request_id,
                ),
            )
            connection.commit()

    def release(self, reservation: Reservation, *, error_type: str) -> None:
        """仅用于尚未交给上游模型的本地失败。"""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM requests WHERE request_id = ?",
                (reservation.request_id,),
            ).fetchone()
            if row is None or row["status"] != "reserved":
                connection.rollback()
                raise RuntimeError("请求不存在或已经结算")
            connection.execute(
                """
                UPDATE budgets SET
                    reserved_tokens = reserved_tokens - ?,
                    reserved_cny_nano = reserved_cny_nano - ?,
                    reserved_requests = reserved_requests - 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    reservation.reserved_tokens,
                    reservation.reserved_cny_nano,
                    _now(),
                    reservation.budget_id,
                ),
            )
            connection.execute(
                """
                UPDATE requests SET status = 'released', error_type = ?, finished_at = ?
                WHERE request_id = ?
                """,
                (error_type, _now(), reservation.request_id),
            )
            connection.commit()

    def status(self, budget_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
        if row is None:
            raise KeyError(f"未知预算：{budget_id}")
        result = dict(row)
        result["cny_limit"] = result["cny_limit_nano"] / NANOCNY_PER_CNY
        result["used_cny"] = result["used_cny_nano"] / NANOCNY_PER_CNY
        result["reserved_cny"] = result["reserved_cny_nano"] / NANOCNY_PER_CNY
        for key in ("cny_limit_nano", "used_cny_nano", "reserved_cny_nano"):
            result.pop(key)
        return result

    def available(self, budget_id: str) -> dict[str, int | float]:
        """Return spendable balances after committed and in-flight usage."""
        status = self.status(budget_id)
        return {
            "tokens": status["token_limit"]
            - status["used_tokens"]
            - status["reserved_tokens"],
            "cny": status["cny_limit"] - status["used_cny"] - status["reserved_cny"],
            "requests": status["request_limit"]
            - status["used_requests"]
            - status["reserved_requests"],
        }

    def recent(self, budget_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT request_id, alias, status, input_estimate, max_output,
                       actual_input, actual_output, actual_tokens, actual_cny_nano,
                       error_type, created_at, finished_at
                FROM requests WHERE budget_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (budget_id, max(1, min(int(limit), 100))),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            value = item.pop("actual_cny_nano")
            item["actual_cny"] = None if value is None else value / NANOCNY_PER_CNY
            results.append(item)
        return results

    def update_limits(
        self,
        budget_id: str,
        *,
        total_tokens: int,
        total_cny_nano: int,
        total_requests: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(f"未知预算：{budget_id}")
            checks = (
                (total_tokens, row["used_tokens"] + row["reserved_tokens"], "token"),
                (total_cny_nano, row["used_cny_nano"] + row["reserved_cny_nano"], "金额"),
                (total_requests, row["used_requests"] + row["reserved_requests"], "请求数"),
            )
            for limit, committed, name in checks:
                if limit < committed:
                    connection.rollback()
                    raise ValueError(f"{name}上限不能低于已使用与已预留之和 {committed}")
            connection.execute(
                """
                UPDATE budgets SET token_limit = ?, cny_limit_nano = ?,
                    request_limit = ?, updated_at = ? WHERE id = ?
                """,
                (total_tokens, total_cny_nano, total_requests, _now(), budget_id),
            )
            connection.commit()

    def reset(self, budget_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT reserved_requests FROM budgets WHERE id = ?", (budget_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(f"未知预算：{budget_id}")
            if row["reserved_requests"]:
                connection.rollback()
                raise RuntimeError("仍有进行中的请求，不能重置")
            connection.execute("DELETE FROM requests WHERE budget_id = ?", (budget_id,))
            connection.execute(
                """
                UPDATE budgets SET used_tokens = 0, used_cny_nano = 0,
                    used_requests = 0, updated_at = ? WHERE id = ?
                """,
                (_now(), budget_id),
            )
            connection.commit()
