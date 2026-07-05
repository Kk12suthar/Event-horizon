from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


def sse_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=_json_default)


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return str(value)

