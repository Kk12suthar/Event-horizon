from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _RowResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _MappingRow:
    def __init__(self, **values):
        self._mapping = values


class _QuotaDb:
    def __init__(self, *, file_count=0, total_bytes=0, global_bytes=0):
        self.file_count = file_count
        self.total_bytes = total_bytes
        self.global_bytes = global_bytes
        self.calls: list[str] = []

    def execute(self, query, params=None):
        sql = str(query).lower()
        self.calls.append(sql)
        if "pg_advisory_xact_lock" in sql:
            return _ScalarResult(None)
        if "count(*) filter" in sql:
            return _RowResult(_MappingRow(file_count=self.file_count, total_bytes=self.total_bytes))
        if "select coalesce(sum" in sql:
            return _ScalarResult(self.global_bytes)
        raise AssertionError(f"Unexpected SQL: {query}")


QUOTA_ENV = {
    "UPLOAD_STORAGE_CAPACITY_BYTES": str(60 * 1024**3),
    "UPLOAD_PLANNED_USERS": "50",
    "UPLOAD_MAX_FILES_PER_USER": "3",
    "UPLOAD_STORAGE_EXPANSION_FACTOR": "5",
    "UPLOAD_STORAGE_RESERVE_PERCENT": "25",
    "UPLOAD_MIN_FREE_BYTES": str(15 * 1024**3),
    "UPLOAD_USER_QUOTA_CAP_BYTES": str(180 * 1024**2),
    "UPLOAD_FILE_SIZE_CAP_BYTES": str(60 * 1024**2),
}


class GoogleIdentityTests(unittest.TestCase):
    def test_accepts_verified_gmail_token_with_matching_nonce(self):
        from utils.google_identity import verify_google_credential

        calls = []

        def verifier(token, audience):
            calls.append((token, audience))
            return {
                "iss": "https://accounts.google.com",
                "sub": "google-subject",
                "email": "person@gmail.com",
                "email_verified": True,
                "nonce": "request-nonce",
            }

        claims = verify_google_credential("credential", "request-nonce", "client-id", verifier)
        self.assertEqual(claims["sub"], "google-subject")
        self.assertEqual(calls, [("credential", "client-id")])

    def test_rejects_nonce_mismatch(self):
        from utils.google_identity import GoogleIdentityError, verify_google_credential

        with self.assertRaises(GoogleIdentityError):
            verify_google_credential(
                "credential",
                "expected",
                "client-id",
                lambda *_: {
                    "iss": "accounts.google.com",
                    "sub": "subject",
                    "email": "person@gmail.com",
                    "email_verified": True,
                    "nonce": "different",
                },
            )

    def test_rejects_non_authoritative_email_account(self):
        from utils.google_identity import GoogleIdentityError, verify_google_credential

        with self.assertRaises(GoogleIdentityError):
            verify_google_credential(
                "credential",
                "nonce",
                "client-id",
                lambda *_: {
                    "iss": "accounts.google.com",
                    "sub": "subject",
                    "email": "person@example.com",
                    "email_verified": True,
                    "nonce": "nonce",
                },
            )


class UploadQuotaTests(unittest.TestCase):
    def test_storage_policy_resolves_to_three_files_and_180_mib(self):
        from utils.upload_quota import MIB, get_upload_quota_limits

        with patch.dict(os.environ, QUOTA_ENV, clear=False):
            limits = get_upload_quota_limits(ROOT / "uploads")

        self.assertEqual(limits.max_files, 3)
        self.assertEqual(limits.max_file_bytes, 60 * MIB)
        self.assertEqual(limits.max_total_bytes, 180 * MIB)

    def test_rejects_parallel_count_and_total_quota_overruns(self):
        from fastapi import HTTPException
        from utils.upload_quota import MIB, enforce_new_file_quota

        with patch.dict(os.environ, QUOTA_ENV, clear=False):
            with self.assertRaises(HTTPException) as count_error:
                enforce_new_file_quota(_QuotaDb(file_count=3), "user-1", MIB)
            with self.assertRaises(HTTPException) as byte_error:
                enforce_new_file_quota(_QuotaDb(file_count=2, total_bytes=170 * MIB), "user-1", 20 * MIB)

        self.assertEqual(count_error.exception.status_code, 409)
        self.assertEqual(byte_error.exception.status_code, 413)

    def test_deleted_bytes_remain_reserved_until_storage_is_removed(self):
        from utils.upload_quota import get_upload_usage

        db = _QuotaDb(file_count=1, total_bytes=125)
        self.assertEqual(get_upload_usage(db, "user-1"), {"file_count": 1, "total_bytes": 125})
        self.assertIn("!= 'failed'", db.calls[-1])
        self.assertIn("count(*) filter", db.calls[-1])

    def test_upload_start_rejects_client_user_impersonation(self):
        import utils.upload_socket_security as upload_security

        original_decoder = upload_security.decode_access_token
        try:
            upload_security.decode_access_token = lambda _: {"sub": "signed-user"}
            with patch.dict(os.environ, QUOTA_ENV, clear=False):
                with self.assertRaises(Exception) as error:
                    upload_security.authenticate_upload_start(
                        {"accessToken": "token", "userId": "other-user", "totalFiles": 1}
                    )
            self.assertEqual(getattr(error.exception, "status_code", None), 403)
        finally:
            upload_security.decode_access_token = original_decoder


if __name__ == "__main__":
    unittest.main()
