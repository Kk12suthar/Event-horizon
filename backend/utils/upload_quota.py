"""Server-authoritative upload quota calculation and enforcement."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shutil
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text


MIB = 1024 * 1024
GIB = 1024 * MIB
ACTIVE_FILE_STATUSES = ("UPLOADED", "PROCESSING", "PROCESSED", "ACTIVE")


@dataclass(frozen=True)
class UploadQuotaLimits:
    storage_capacity_bytes: int
    storage_reserve_bytes: int
    planned_users: int
    storage_expansion_factor: float
    max_files: int
    max_file_bytes: int
    max_total_bytes: int

    def public_dict(self) -> dict[str, int | float]:
        return asdict(self)


def get_upload_quota_limits(storage_path: str | Path | None = None) -> UploadQuotaLimits:
    """Derive per-user limits from disk capacity and expected DB expansion.

    A source file is retained and also materialized as a raw PostgreSQL table.
    One prepared table is allowed, so production reserves a configurable 5x
    multiplier for source + raw + prepared data and indexes/WAL overhead.
    """

    path = Path(storage_path or os.getenv("UPLOAD_STORAGE_PATH", Path(__file__).parents[1] / "uploads"))
    path.mkdir(parents=True, exist_ok=True)
    measured_capacity = shutil.disk_usage(path).total
    capacity = _positive_int("UPLOAD_STORAGE_CAPACITY_BYTES", measured_capacity)
    planned_users = _positive_int("UPLOAD_PLANNED_USERS", 50)
    max_files = _positive_int("UPLOAD_MAX_FILES_PER_USER", 3)
    expansion = _positive_float("UPLOAD_STORAGE_EXPANSION_FACTOR", 5.0)
    reserve_percent = min(90.0, max(0.0, _float("UPLOAD_STORAGE_RESERVE_PERCENT", 25.0)))
    minimum_reserve = _positive_int("UPLOAD_MIN_FREE_BYTES", 15 * GIB)
    reserve = max(minimum_reserve, int(capacity * reserve_percent / 100.0))
    usable = max(0, capacity - reserve)

    quantum = 5 * MIB
    calculated_total = _round_down(int(usable / planned_users / expansion), quantum)
    configured_total_cap = _positive_int("UPLOAD_USER_QUOTA_CAP_BYTES", 180 * MIB)
    max_total = min(calculated_total, configured_total_cap)
    configured_file_cap = _positive_int("UPLOAD_FILE_SIZE_CAP_BYTES", 60 * MIB)
    max_file = min(_round_down(max_total // max_files, quantum), configured_file_cap)
    if max_total < quantum or max_file < quantum:
        raise RuntimeError("Upload storage is too small for the configured quota policy.")

    return UploadQuotaLimits(
        storage_capacity_bytes=capacity,
        storage_reserve_bytes=reserve,
        planned_users=planned_users,
        storage_expansion_factor=expansion,
        max_files=max_files,
        max_file_bytes=max_file,
        max_total_bytes=max_total,
    )


def get_upload_usage(db: Any, user_id: str) -> dict[str, int]:
    row = db.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE UPPER(COALESCE(status, 'ACTIVE')) IN ('UPLOADED', 'PROCESSING', 'PROCESSED', 'ACTIVE')
                ) AS file_count,
                COALESCE(SUM(COALESCE(size_bytes, 0)) FILTER (
                    WHERE UPPER(COALESCE(status, 'ACTIVE')) != 'FAILED'
                ), 0) AS total_bytes
            FROM instance01.mtd_file
            WHERE uploaded_by = :user_id
            """
        ),
        {"user_id": user_id},
    ).fetchone()
    mapping = getattr(row, "_mapping", row)
    return {
        "file_count": int((mapping["file_count"] if mapping else 0) or 0),
        "total_bytes": int((mapping["total_bytes"] if mapping else 0) or 0),
    }


def get_upload_quota_snapshot(db: Any, user_id: str) -> dict[str, Any]:
    limits = get_upload_quota_limits()
    usage = get_upload_usage(db, user_id)
    return {
        "limits": limits.public_dict(),
        "usage": usage,
        "remaining": {
            "file_count": max(0, limits.max_files - usage["file_count"]),
            "total_bytes": max(0, limits.max_total_bytes - usage["total_bytes"]),
        },
        "one_prepared_table_allowed": True,
    }


def enforce_new_file_quota(db: Any, user_id: str, size_bytes: int) -> UploadQuotaLimits:
    """Lock quota accounting and reject a file before its metadata is inserted."""

    limits = get_upload_quota_limits()
    if size_bytes <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty files are not allowed.")
    if size_bytes > limits.max_file_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds the {_format_mib(limits.max_file_bytes)} per-file limit.",
        )

    # Both locks are transaction-scoped. They prevent parallel requests from
    # bypassing either the account quota or shared disk reservation.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "eventhorizon:upload:global"})
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"eventhorizon:upload:user:{user_id}"},
    )
    usage = get_upload_usage(db, user_id)
    if usage["file_count"] + 1 > limits.max_files:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Upload limit reached. Each user can keep at most {limits.max_files} files.",
        )
    if usage["total_bytes"] + size_bytes > limits.max_total_bytes:
        remaining = max(0, limits.max_total_bytes - usage["total_bytes"])
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Upload storage limit reached. {_format_mib(remaining)} remains for this account.",
        )

    global_bytes = int(
        db.execute(
            text(
                """
                SELECT COALESCE(SUM(COALESCE(size_bytes, 0)), 0)
                FROM instance01.mtd_file
                WHERE UPPER(COALESCE(status, 'ACTIVE')) != 'FAILED'
                """
            )
        ).scalar()
        or 0
    )
    projected_storage = int((global_bytes + size_bytes) * limits.storage_expansion_factor)
    usable_storage = limits.storage_capacity_bytes - limits.storage_reserve_bytes
    if projected_storage > usable_storage:
        raise HTTPException(
            status.HTTP_507_INSUFFICIENT_STORAGE,
            "Upload storage is temporarily full. No file was accepted.",
        )
    return limits


def _round_down(value: int, quantum: int) -> int:
    return max(0, value // quantum * quantum)


def _format_mib(value: int) -> str:
    return f"{value / MIB:.0f} MiB"


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")
    return value


def _positive_float(name: str, default: float) -> float:
    value = _float(name, default)
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")
    return value


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))
