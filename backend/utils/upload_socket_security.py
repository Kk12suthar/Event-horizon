"""Identity, ownership, and byte validation for the upload WebSocket."""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text

from security.policy import require_folder_access
from utils.authentication import decode_access_token
from utils.file_validation import sanitize_filename
from utils.upload_quota import get_upload_quota_limits


def authenticate_upload_start(message: dict[str, Any]) -> tuple[dict[str, Any], int]:
    token = str(message.get("accessToken") or "").strip()
    user = decode_access_token(token) if token else None
    user_id = str((user or {}).get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Upload authentication failed.")
    claimed_user = str(message.get("userId") or "").strip()
    if claimed_user and claimed_user != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Upload identity does not match the signed-in user.")

    total_files = int(message.get("totalFiles") or 0)
    limits = get_upload_quota_limits()
    if total_files <= 0 or total_files > limits.max_files:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"An upload batch must contain between 1 and {limits.max_files} files.",
        )
    return user, total_files


def authorize_upload_metadata(
    db: Any,
    message: dict[str, Any],
    user: dict[str, Any],
    upload_root: str | Path,
) -> dict[str, Any]:
    user_id = str(user["sub"])
    try:
        file_id = str(uuid.UUID(str(message.get("fileId") or "")))
        folder_id = str(uuid.UUID(str(message.get("folderId") or "")))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file or folder identifier.") from exc

    require_folder_access(folder_id, user, db, min_level="ANALYST")
    row = db.execute(
        text(
            """
            SELECT id::text, uploaded_by, parent_folder_id::text, original_name, name,
                   size_bytes, status
            FROM instance01.mtd_file
            WHERE id = CAST(:file_id AS uuid)
            FOR UPDATE
            """
        ),
        {"file_id": file_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload file reservation was not found.")
    values = row._mapping
    if str(values["uploaded_by"]) != user_id or str(values["parent_folder_id"]) != folder_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Upload file reservation does not belong to this user and folder.")
    if str(values["status"] or "").upper() != "UPLOADED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload file reservation is not active.")

    limits = get_upload_quota_limits()
    expected_size = int(values["size_bytes"] or 0)
    if expected_size <= 0 or expected_size > limits.max_file_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Reserved file size is outside the upload limit.")
    filename = sanitize_filename(str(values["original_name"] or values["name"] or message.get("fileName") or "upload.csv"))
    claimed_name = sanitize_filename(str(message.get("fileName") or filename))
    if claimed_name != filename:
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload filename does not match its reservation.")

    folder_path = Path(upload_root) / folder_id
    folder_path.mkdir(parents=True, exist_ok=True)
    file_path = folder_path / f"{file_id}_{filename}"
    resolved_root = Path(upload_root).resolve()
    resolved_path = file_path.resolve()
    if resolved_root not in resolved_path.parents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid upload path.")

    db.execute(
        text("UPDATE instance01.mtd_file SET status = 'PROCESSING' WHERE id = CAST(:file_id AS uuid)"),
        {"file_id": file_id},
    )
    db.commit()
    return {
        "file_path": resolved_path,
        "file_id": file_id,
        "folder_id": folder_id,
        "table_id": uuid.uuid4().hex,
        "table_name": os.path.splitext(filename)[0],
        "file_name": filename,
        "expected_size": expected_size,
        "received_bytes": 0,
    }


def decode_upload_chunk(file_info: dict[str, Any], message: dict[str, Any]) -> bytes:
    if message.get("encoding") != "base64":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload chunks must use base64 encoding.")
    try:
        decoded = base64.b64decode(str(message.get("data") or ""), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload chunk is not valid base64.") from exc

    max_chunk = int(os.getenv("UPLOAD_MAX_CHUNK_BYTES", str(1024 * 1024)))
    if not decoded or len(decoded) > max_chunk:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Upload chunk size is invalid.")
    projected = int(file_info.get("received_bytes") or 0) + len(decoded)
    if projected > int(file_info["expected_size"]):
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Streamed bytes exceed the reserved file size.")
    file_info["received_bytes"] = projected
    return decoded


def verify_upload_complete(file_info: dict[str, Any]) -> None:
    if int(file_info.get("received_bytes") or 0) != int(file_info.get("expected_size") or 0):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Streamed file size does not match the reserved size.")


def mark_upload_files(db: Any, file_ids: list[str], new_status: str) -> None:
    if not file_ids:
        return
    db.execute(
        text(
            """
            UPDATE instance01.mtd_file
            SET status = :status
            WHERE id::text = ANY(:file_ids)
            """
        ),
        {"status": new_status, "file_ids": file_ids},
    )
    db.commit()
