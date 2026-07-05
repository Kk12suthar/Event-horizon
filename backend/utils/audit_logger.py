"""
Admin audit logging utility.
Logs admin actions to the admin_audit_logs table for compliance and debugging.
"""

import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Schema name from environment or default
SCHEMA = "instance01"


def _ensure_audit_table(db: Session):
    """Create the audit log table if it doesn't exist."""
    try:
        db.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA}.admin_audit_logs (
                id SERIAL PRIMARY KEY,
                action_type VARCHAR(50) NOT NULL,
                actor_id VARCHAR(64),
                target_type VARCHAR(50),
                target_id VARCHAR(256),
                details JSONB,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_audit_logs_action_type 
            ON {SCHEMA}.admin_audit_logs(action_type)
        """))
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_audit_logs_actor 
            ON {SCHEMA}.admin_audit_logs(actor_id)
        """))
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp 
            ON {SCHEMA}.admin_audit_logs(timestamp)
        """))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to ensure audit table: {e}")


def log_admin_action(
    db: Session,
    action_type: str,
    actor_id: str = None,
    target_type: str = None,
    target_id: str = None,
    details: dict = None,
):
    """
    Log an admin action to the audit table.
    
    Args:
        db: Database session
        action_type: Type of action (e.g., ACCESS_GRANTED, ROLE_CHANGED, MODEL_UPDATED)
        actor_id: UUID of the user performing the action
        target_type: Type of target (e.g., USER, PROJECT, MODEL_CONFIG)
        target_id: Identifier of the target entity
        details: Additional details as a JSON-serializable dict
    """
    try:
        insert_q = text(f"""
            INSERT INTO {SCHEMA}.admin_audit_logs 
                (action_type, actor_id, target_type, target_id, details, timestamp)
            VALUES 
                (:action_type, :actor_id, :target_type, :target_id, CAST(:details AS jsonb), :timestamp)
        """)
        db.execute(insert_q, {
            "action_type": action_type,
            "actor_id": actor_id,
            "target_type": target_type,
            "target_id": target_id,
            "details": json.dumps(details) if details else None,
            "timestamp": datetime.now(timezone.utc),
        })
        # Note: caller is responsible for commit (usually bundled with the main transaction)
    except Exception as e:
        logger.error(f"Failed to log audit action '{action_type}': {e}")
        # Non-fatal: don't break the main operation


# ── Action type constants ──────────────────────────────────────────────────

ACTION_USER_CREATED = "USER_CREATED"
ACTION_USER_INVITED = "USER_INVITED"
ACTION_USER_EDITED = "USER_EDITED"
ACTION_USER_DELETED = "USER_DELETED"
ACTION_ROLE_CHANGED = "ROLE_CHANGED"
ACTION_ACCESS_GRANTED = "ACCESS_GRANTED"
ACTION_ACCESS_REVOKED = "ACCESS_REVOKED"
ACTION_ACCESS_CHANGED = "ACCESS_CHANGED"
ACTION_MODEL_ADDED = "MODEL_ADDED"
ACTION_MODEL_REMOVED = "MODEL_REMOVED"
ACTION_MODEL_CONFIG_UPDATED = "MODEL_CONFIG_UPDATED"
ACTION_API_KEY_UPDATED = "API_KEY_UPDATED"
ACTION_LICENSE_UPDATED = "LICENSE_UPDATED"
ACTION_PROJECT_CREATED = "PROJECT_CREATED"
ACTION_PROJECT_EDITED = "PROJECT_EDITED"
ACTION_PROJECT_DELETED = "PROJECT_DELETED"
