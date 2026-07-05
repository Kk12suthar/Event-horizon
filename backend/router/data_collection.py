from sqlalchemy.orm import Session
from typing import Dict, Any
from database import get_db
from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy import text
from schemas import MessageResponse
import uuid
import json
from pathlib import Path
from dotenv import set_key
from datetime import datetime
from cryptography.fernet import Fernet, InvalidToken
import os
import base64
from utils.audit_logger import log_admin_action, ACTION_MODEL_CONFIG_UPDATED, ACTION_API_KEY_UPDATED, ACTION_LICENSE_UPDATED

#TODO Replace model config id and license id with actual values from frontend, right now they are taken from env
router = APIRouter(prefix="/api/v1/data-collection", tags=["data-collection"])

# Get encryption key from environment
ENCRYPTION_KEY = os.getenv('API_KEY_ENCRYPTION_KEY')
if not ENCRYPTION_KEY:
    raise ValueError("API_KEY_ENCRYPTION_KEY environment variable not set")

# Initialize Fernet cipher
cipher_suite = Fernet(base64.urlsafe_b64encode(ENCRYPTION_KEY.encode()[:32].ljust(32, b'\0')))

def encrypt_data(data: str) -> str:
    """Encrypt sensitive data"""
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """Decrypt sensitive data"""
    return cipher_suite.decrypt(encrypted_data.encode()).decode()

def safe_decrypt_data(value: str) -> str:
    try:
        return decrypt_data(value)
    except InvalidToken:
        return value

def mask_api_key(key: str) -> str:
    """Mask API key showing only first 4 and last 4 chars"""
    if not key or len(key) <= 8:
        return "****"
    return f"...{key[-4:]}"

# ---------------------------------------------------------------------------

def _is_valid_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _hexify(v):
    """Convert UUID objects and binary data to hex strings for PostgreSQL"""
    if isinstance(v, uuid.UUID):
        return str(v)
    elif isinstance(v, (bytes, bytearray)):
        return v.hex()
    return v


def _convert_value(value):
    """Convert value to appropriate type for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if hasattr(value, "isoformat"):  # Handles datetime objects
        return value.isoformat()
    return value


@router.get("/license/{license_id}", response_model=MessageResponse)
def get_license_data(license_id: str, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Get license data by ID.
    
    **HTTP Method:** GET
    **Path:** /api/v1/data-collection/license/{license_id}
    
    **Parameters:**
    - license_id: str - UUID of the license data record
    
    **Returns:**
    - MessageResponse with license data
    
    **Example Request:**
    ```
    GET /api/v1/data-collection/license/550e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Success",
      "data": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "license",
        "data": {
          "license_key": "ABC123",
          "license_type": "enterprise",
          "issue_date": "2024-01-01",
          "valid_till": "2025-01-01",
          "status": "active",
          "max_admin_allowed": "10",
          "max_analyst_allowed": "50",
          "max_viewer_allowed": "100",
          "active_admin": "5",
          "active_analyst": "30",
          "active_viewer": "60",
          "total_user": "160",
          "total_active_user": "95",
          "total_project": "20",
          "total_active_project": "15",
          "max_transformations_allowed": "1000",
          "max_dashboard_allowed": "500",
          "llm_models_allowed": ["gpt-4", "gemini-pro"]
        },
        "created_at": "2024-01-01T10:00:00",
        "created_by": "660e8400-e29b-41d4-a716-446655440000"
      }
    }
    ```
    
    **Error Cases:**
    - 404: License data not found
    - 500: Database error
    """
    try:
        if _is_valid_uuid(license_id):
            sel_q = text(
                "SELECT * FROM instance01.data_collection WHERE id = CAST(:id AS uuid) AND title = 'license'"
            )
            res = db.execute(sel_q, {"id": license_id}).fetchone()
        else:
            sel_q = text(
                "SELECT * FROM instance01.data_collection WHERE title = 'license' LIMIT 1"
            )
            res = db.execute(sel_q).fetchone()
        
        if not res:
            raise HTTPException(status_code=404, detail="License data not found")
        
        d = res._asdict() if hasattr(res, "_asdict") else dict(zip(res.keys(), res))
        
        # Convert values to appropriate types
        for k, v in d.items():
            if k == "created_at" and v is not None:
                d[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
            else:
                d[k] = _hexify(v)
        
        # ── Override user counts with real values from mtd_users ────────────
        try:
            count_q = text("""
                SELECT
                    COALESCE(SUM(CASE WHEN UPPER(role) = 'ADMIN' THEN 1 ELSE 0 END), 0)   AS admin_count,
                    COALESCE(SUM(CASE WHEN UPPER(role) = 'ANALYST' THEN 1 ELSE 0 END), 0) AS analyst_count,
                    COALESCE(SUM(CASE WHEN UPPER(role) = 'VIEWER' THEN 1 ELSE 0 END), 0)  AS viewer_count,
                    COUNT(*)                                                                AS total_count
                FROM instance01.mtd_users
            """)
            counts = db.execute(count_q).fetchone()
            if counts:
                admin_count   = int(counts[0])
                analyst_count = int(counts[1])
                viewer_count  = int(counts[2])
                total_count   = int(counts[3])

                # Patch the JSONB data dict (nested inside 'd')
                license_data = d.get("data", d)
                if isinstance(license_data, dict):
                    license_data["active_admin"]     = str(admin_count)
                    license_data["active_analyst"]    = str(analyst_count)
                    license_data["active_viewer"]     = str(viewer_count)
                    license_data["total_user"]        = str(total_count)
                    license_data["total_active_user"] = str(admin_count + analyst_count + viewer_count)
        except Exception as count_exc:
            print(f"Warning: could not fetch real user counts: {count_exc}")
        
        # ── Override project counts with real values from mtd_project ──────
        try:
            proj_q = text("""
                SELECT
                    COUNT(*)                                                                     AS total_project,
                    COALESCE(SUM(CASE WHEN UPPER(status) = 'ACTIVE' THEN 1 ELSE 0 END), 0)      AS active_project
                FROM instance01.mtd_project
            """)
            proj_counts = db.execute(proj_q).fetchone()
            if proj_counts:
                license_data = d.get("data", d)
                if isinstance(license_data, dict):
                    license_data["total_project"]        = str(int(proj_counts[0]))
                    license_data["total_active_project"]  = str(int(proj_counts[1]))
        except Exception as proj_exc:
            print(f"Warning: could not fetch real project counts: {proj_exc}")

        # ── Override transformation count: count transform_data_* tables ────
        try:
            transform_q = text("""
                SELECT COUNT(*) AS transformation_count
                FROM information_schema.tables
                WHERE table_schema = 'uploads'
                  AND table_name LIKE 'transform\\_data\\_%' ESCAPE '\\'
            """)
            transform_result = db.execute(transform_q).fetchone()
            if transform_result:
                license_data = d.get("data", d)
                if isinstance(license_data, dict):
                    license_data["transformations_done"] = str(int(transform_result[0]))
        except Exception as transform_exc:
            print(f"Warning: could not fetch real transformation counts: {transform_exc}")

        return MessageResponse(message="Success", data=d)
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error in get_license_data: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/license/{license_id}", response_model=MessageResponse)
def edit_license_data(
    license_id: str, 
    data: Dict[str, Any], 
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Update license data by ID.
    
    **HTTP Method:** PUT
    **Path:** /api/v1/data-collection/license/{license_id}
    
    **Parameters:**
    - license_id: str - UUID of the license data record
    - data: Dict[str, Any] - License data object to update
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    {
      "license_key": "ABC123",
      "license_type": "enterprise",
      "issue_date": "2024-01-01",
      "valid_till": "2025-01-01",
      "status": "active",
      "max_admin_allowed": "10",
      "max_analyst_allowed": "50",
      "max_viewer_allowed": "100",
      "active_admin": "5",
      "active_analyst": "30",
      "active_viewer": "60",
      "total_user": "160",
      "total_active_user": "95",
      "total_project": "20",
      "total_active_project": "15",
      "max_transformations_allowed": "1000",
      "max_dashboard_allowed": "500",
      "llm_models_allowed": ["gpt-4", "gemini-pro"]
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "License data updated successfully",
      "data": null
    }
    ```
    
    **Error Cases:**
    - 404: License data not found
    - 500: Database error
    """
    try:
        license_id=os.getenv("LICENSE_ID")
        # Check if record exists
        if _is_valid_uuid(license_id):
            check_q = text(
                "SELECT COUNT(*) as count FROM instance01.data_collection WHERE id = CAST(:id AS uuid) AND title = 'license'"
            )
            result = db.execute(check_q, {"id": license_id}).fetchone()
        else:
            check_q = text(
                "SELECT COUNT(*) as count FROM instance01.data_collection WHERE title = 'license'"
            )
            result = db.execute(check_q).fetchone()
        exists = result[0] > 0 if result else False
        
        if not exists:
            raise HTTPException(status_code=404, detail="License data not found")
        
        # Convert data to JSON string
        data_json = json.dumps(data)
        
        # Update the record
        if _is_valid_uuid(license_id):
            upd_q = text(
                "UPDATE instance01.data_collection SET data = CAST(:data AS jsonb) WHERE id = CAST(:id AS uuid) AND title = 'license'"
            )
            db.execute(upd_q, {"id": license_id, "data": data_json})
        else:
            upd_q = text(
                "UPDATE instance01.data_collection SET data = CAST(:data AS jsonb) WHERE title = 'license'"
            )
            db.execute(upd_q, {"data": data_json})
        log_admin_action(db, ACTION_LICENSE_UPDATED, target_type="LICENSE", target_id=str(license_id))
        db.commit()
        
        return MessageResponse(message="License data updated successfully", data=None)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        print(f"Error in edit_license_data: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/model-config/{config_id}", response_model=MessageResponse)
def get_model_config_data(config_id: str, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Get model configuration data by ID.
    
    **HTTP Method:** GET
    **Path:** /api/v1/data-collection/model-config/{config_id}
    
    **Parameters:**
    - config_id: str - UUID of the model config data record
    
    **Returns:**
    - MessageResponse with model config data
    
    **Example Request:**
    ```
    GET /api/v1/data-collection/model-config/550e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Success",
      "data": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "model_config",
        "data": {
          "all_models": [
            {
              "model_name": "gemini-2.5-flash",
              "model_type": "google",
              "model_api_key": "sk-***",
              "temperature": 0.7,
              "timeout": 60,
              "retries": 3,
              "streaming": true
            }
          ],
          "transformation_agents": {
            "orchestrator": "gpt5.0",
            "analysis_agent": "gemini-2.5-flash",
            "data_ops_agent": "gemini-2.5-flash",
            "search_agent": "gemini-2.5-flash"
          },
          "dashboard_agents": {
            "orchestrator": "gpt5.0",
            "code_executor_agent": "gemini-2.5-flash",
            "database_query_agent": "gemini-2.5-flash",
            "search_agent": "gemini-2.5-flash"
          },
          "default_model": "gemini-2.5-flash",
          "fallback_model": "gemini-2.0-flash",
          "default_temperature": 0.7,
          "default_timeout": 60,
          "default_retries": 3,
          "default_streaming": true
        },
        "created_at": "2024-01-01T10:00:00",
        "created_by": "660e8400-e29b-41d4-a716-446655440000"
      }
    }
    ```
    
    **Error Cases:**
    - 404: Model config data not found
    - 500: Database error
    """
    try:
        if _is_valid_uuid(config_id):
            sel_q = text(
                "SELECT * FROM instance01.data_collection WHERE id = CAST(:id AS uuid) AND title = 'model_config'"
            )
            res = db.execute(sel_q, {"id": config_id}).fetchone()
        else:
            sel_q = text(
                "SELECT * FROM instance01.data_collection WHERE title = 'model_config' LIMIT 1"
            )
            res = db.execute(sel_q).fetchone()
        
        if not res:
            raise HTTPException(status_code=404, detail="Model config data not found")
        
        d = res._asdict() if hasattr(res, "_asdict") else dict(zip(res.keys(), res))
        
        # Convert values to appropriate types
        for k, v in d.items():
            if k == "created_at" and v is not None:
                d[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
            else:
                d[k] = _hexify(v)
        
        # Decrypt and mask API keys
        if 'data' in d and isinstance(d['data'], dict):
            # Mask per-model keys (legacy format)
            if 'all_models' in d['data']:
                for model in d['data']['all_models']:
                    if 'model_api_key' in model and model['model_api_key']:
                        decrypted = safe_decrypt_data(model['model_api_key'])
                        model['model_api_key'] = mask_api_key(decrypted)
                    if 'backup_model_api_key' in model and model['backup_model_api_key']:
                        decrypted_backup = safe_decrypt_data(model['backup_model_api_key'])
                        model['backup_model_api_key'] = mask_api_key(decrypted_backup)
            
            # Mask provider-level keys (new format)
            if 'providers' in d['data']:
                for provider in d['data']['providers']:
                    if 'primary_key' in provider and provider['primary_key']:
                        decrypted = safe_decrypt_data(provider['primary_key'])
                        provider['primary_key'] = mask_api_key(decrypted)
                    if 'backup_key' in provider and provider['backup_key']:
                        decrypted = safe_decrypt_data(provider['backup_key'])
                        provider['backup_key'] = mask_api_key(decrypted)
        
        return MessageResponse(message="Success", data=d)
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error in get_model_config_data: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/model-config/{config_id}", response_model=MessageResponse)
def edit_model_config_data(
    config_id: str, 
    data: Dict[str, Any], 
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Update model configuration data by ID.
    
    **HTTP Method:** PUT
    **Path:** /api/v1/data-collection/model-config/{config_id}
    
    **Parameters:**
    - config_id: str - UUID of the model config data record
    - data: Dict[str, Any] - Model config data object to update
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    {
      "all_models": [
        {
          "model_name": "gemini-2.5-flash",
          "model_type": "google",
          "model_api_key": "sk-***",
          "temperature": 0.7,
          "timeout": 60,
          "retries": 3,
          "streaming": true
        }
      ],
      "transformation_agents": {
        "orchestrator": "gpt5.0",
        "analysis_agent": "gemini-2.5-flash",
        "data_ops_agent": "gemini-2.5-flash",
        "search_agent": "gemini-2.5-flash"
      },
      "dashboard_agents": {
        "orchestrator": "gpt5.0",
        "code_executor_agent": "gemini-2.5-flash",
        "database_query_agent": "gemini-2.5-flash",
        "search_agent": "gemini-2.5-flash"
      },
      "default_model": "gemini-2.5-flash",
      "fallback_model": "gemini-2.0-flash",
      "default_temperature": 0.7,
      "default_timeout": 60,
      "default_retries": 3,
      "default_streaming": true
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Model config data updated successfully",
      "data": null
    }
    ```
    
    **Error Cases:**
    - 404: Model config data not found
    - 500: Database error
    """
    try:
        config_id=os.getenv("MODEL_CONFIG_KEY")
        # Check if record exists
        if _is_valid_uuid(config_id):
            check_q = text(
                "SELECT COUNT(*) as count FROM instance01.data_collection WHERE id = CAST(:id AS uuid) AND title = 'model_config'"
            )
            result = db.execute(check_q, {"id": config_id}).fetchone()
        else:
            check_q = text(
                "SELECT COUNT(*) as count FROM instance01.data_collection WHERE title = 'model_config'"
            )
            result = db.execute(check_q).fetchone()
        exists = result[0] > 0 if result else False
        
        if not exists:
            raise HTTPException(status_code=404, detail="Model config data not found")
        
        # ── Model config validation ────────────────────────────────────────
        # 1. Default model must not equal fallback model
        default_model = data.get('default_model', '')
        fallback_model = data.get('fallback_model', '')
        if default_model and fallback_model and default_model == fallback_model:
            raise HTTPException(
                status_code=400,
                detail="Default model and fallback model must be different"
            )
        
        # Get existing data to compare keys and models
        if _is_valid_uuid(config_id):
            sel_q = text(
                "SELECT data FROM instance01.data_collection WHERE id = CAST(:id AS uuid) AND title = 'model_config'"
            )
            existing = db.execute(sel_q, {"id": config_id}).fetchone()
        else:
            sel_q = text(
                "SELECT data FROM instance01.data_collection WHERE title = 'model_config' LIMIT 1"
            )
            existing = db.execute(sel_q).fetchone()
        existing_data = existing[0] if existing else {}
        existing_models = {m['model_name']: m for m in existing_data.get('all_models', [])} if existing_data else {}
        existing_providers = {p['name']: p for p in existing_data.get('providers', [])} if existing_data else {}
        
        # 2. Cannot delete a model that is assigned to an agent or pipeline
        new_model_names = {m.get('model_name') for m in data.get('all_models', [])}
        assigned_models = set()
        # Check legacy per-agent config
        for agents in [data.get('transformation_agents', {}), data.get('dashboard_agents', {})]:
            if isinstance(agents, dict):
                assigned_models.update(agents.values())
        # Check new pipeline config
        for pipe in [data.get('transformation_pipeline', {}), data.get('dashboard_pipeline', {})]:
            if isinstance(pipe, dict):
                for key in ('orchestrator_model', 'sub_agent_model', 'fallback_model'):
                    val = pipe.get(key)
                    if val:
                        assigned_models.add(val)
        # Check default/fallback
        if default_model:
            assigned_models.add(default_model)
        if fallback_model:
            assigned_models.add(fallback_model)
        
        # Only block if the assigned model is missing from the NEW list BUT WAS present in the OLD list
        # This prevents blocking updates when a model was assigned but already missing from the models list
        old_model_names = set(existing_models.keys())
        orphan_models = assigned_models - new_model_names
        truly_deleted_orphans = orphan_models.intersection(old_model_names)
        
        if truly_deleted_orphans and new_model_names:  # Only validate if models list is provided
            raise HTTPException(
                status_code=400,
                detail=f"Cannot remove models that are still assigned: {', '.join(truly_deleted_orphans)}"
            )
        
        # ── Encrypt provider-level API keys (NEW format) ───────────────────
        if 'providers' in data:
            for provider in data['providers']:
                provider_name = provider.get('name', '')
                existing_provider = existing_providers.get(provider_name, {})
                
                for key_field in ('primary_key', 'backup_key'):
                    if key_field in provider and provider[key_field]:
                        key = provider[key_field]
                        if key.startswith('...') or key == '****':
                            provider[key_field] = existing_provider.get(key_field, '')
                        elif key.startswith('gAAAAA'):
                            pass  # Already encrypted
                        else:
                            # Write raw key to .env file
                            env_path = Path(__file__).parent.parent / ".env"
                            env_var_name = f"{provider_name.upper()}_API_KEY"
                            try:
                                set_key(str(env_path), env_var_name, key)
                                print(f"[DEBUG] Wrote {env_var_name} to .env file")
                            except Exception as env_exc:
                                print(f"Warning: could not write to .env file: {env_exc}")

                            provider[key_field] = encrypt_data(key)
        
        # ── Encrypt per-model API keys (LEGACY format) ─────────────────────
        if 'all_models' in data:
            for model in data['all_models']:
                model_name = model.get('model_name')
                existing_model = existing_models.get(model_name, {})
                
                # Check model_api_key
                if 'model_api_key' in model and model['model_api_key']:
                    key = model['model_api_key']
                    print(f"[DEBUG] Model: {model_name}, Key received: '{key[:20]}...' (len={len(key)})")
                    if key.startswith('...') or key == '****':
                        print(f"[DEBUG] Key is masked, keeping existing encrypted key")
                        model['model_api_key'] = existing_model.get('model_api_key', '')
                    elif key.startswith('gAAAAA'):
                        print(f"[DEBUG] Key already encrypted, keeping as-is")
                        pass  # Already encrypted
                    else:
                        print(f"[DEBUG] New raw key detected, encrypting...")
                        # We don't know the exact provider for per-model keys reliably here in legacy mode,
                        # but standard provider logic above handles the ENV setting for providers.
                        model['model_api_key'] = encrypt_data(key)
                        print(f"[DEBUG] Encrypted to: '{model['model_api_key'][:30]}...'")
                
                # Check backup_model_api_key
                if 'backup_model_api_key' in model and model['backup_model_api_key']:
                    key = model['backup_model_api_key']
                    if key.startswith('...') or key == '****':
                        model['backup_model_api_key'] = existing_model.get('backup_model_api_key', '')
                    elif key.startswith('gAAAAA'):
                        pass
                    else:
                        model['backup_model_api_key'] = encrypt_data(key)

        # Convert data to JSON string
        data_json = json.dumps(data)
        
        # Update the record
        if _is_valid_uuid(config_id):
            upd_q = text(
                "UPDATE instance01.data_collection SET data = CAST(:data AS jsonb) WHERE id = CAST(:id AS uuid) AND title = 'model_config'"
            )
            db.execute(upd_q, {"id": config_id, "data": data_json})
        else:
            upd_q = text(
                "UPDATE instance01.data_collection SET data = CAST(:data AS jsonb) WHERE title = 'model_config'"
            )
            db.execute(upd_q, {"data": data_json})
        log_admin_action(db, ACTION_MODEL_CONFIG_UPDATED, target_type="MODEL_CONFIG", target_id=str(config_id))
        db.commit()
        
        return MessageResponse(message="Model config data updated successfully", data=None)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        print(f"Error in edit_model_config_data: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/invocation-ids/{session_id}", response_model=MessageResponse)
def get_invocation_ids(session_id: uuid.UUID, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Get invocation IDs data for a given session.

    **HTTP Method:** GET
    **Path:** /api/v1/data-collection/invocation-ids/{session_id}

    **Parameters:**
    - session_id: str - UUID of the session

    **Returns:**
    - MessageResponse with invocation IDs data (JSON object mapping invocation_id to timestamp)

    **Example Request:**
    ```
    GET /api/v1/data-collection/invocation-ids/550e8400-e29b-41d4-a716-446655440000
    ```

    **Example Response:**
    ```json
    {
      "message": "Success",
      "data": {
        "invocation_id_1": "2025-01-17T10:30:45.123456",
        "invocation_id_2": "2025-01-17T10:31:22.654321",
        "invocation_id_3": "2025-01-17T10:32:15.987654"
      }
    }
    ```

    **Error Cases:**
    - 404: Invocation IDs data not found for this session
    - 500: Database error
    """
    try:
        sel_q = text(
            """
            SELECT data FROM instance01.data_collection
            WHERE id = CAST(:id AS uuid) AND title = 'invocation_ids'
            """
        )
        res = db.execute(sel_q, {"id": session_id}).fetchone()

        if not res:
            # Return empty object if no data exists yet
            return MessageResponse(
                message="No invocation IDs found for this session",
                data={}
            )

        invocation_data = res[0] if res[0] else {}

        return MessageResponse(message="Success", data=invocation_data)
    except Exception as exc:
        print(f"Error in get_invocation_ids: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/invocation-ids/{session_id}", response_model=MessageResponse)
def set_invocation_ids(
    session_id: uuid.UUID,
    data: Dict[str, str],
    db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Set/update invocation IDs data for a given session.

    **HTTP Method:** PUT
    **Path:** /api/v1/data-collection/invocation-ids/{session_id}

    **Parameters:**
    - session_id: str - UUID of the session
    - data: Dict[str, str] - JSON object mapping invocation_id to timestamp

    **Returns:**
    - MessageResponse with success message

    **Example Request:**
    ```json
    {
      "invocation_id_1": "2025-01-17T10:30:45.123456",
      "invocation_id_2": "2025-01-17T10:31:22.654321",
      "invocation_id_3": "2025-01-17T10:32:15.987654"
    }
    ```

    **Example Response:**
    ```json
    {
      "message": "Invocation IDs updated successfully",
      "data": null
    }
    ```

    **Error Cases:**
    - 500: Database error
    """
    try:
        # Check if record exists
        check_q = text(
            """
            SELECT COUNT(*) as count FROM instance01.data_collection
            WHERE id = CAST(:id AS uuid) AND title = 'invocation_ids'
            """
        )
        result = db.execute(check_q, {"id": session_id}).fetchone()
        exists = result[0] > 0 if result else False

        # Convert data to JSON string
        data_json = json.dumps(data)

        if exists:
            # Update existing record
            upd_q = text(
                """
                UPDATE instance01.data_collection
                SET data = CAST(:data AS jsonb)
                WHERE id = CAST(:id AS uuid) AND title = 'invocation_ids'
                """
            )
            db.execute(upd_q, {"id": session_id, "data": data_json})
        else:
            # Insert new record
            ins_q = text(
                """
                INSERT INTO instance01.data_collection (id, title, data, created_at, created_by)
                VALUES (
                    CAST(:id AS uuid),
                    'invocation_ids',
                    CAST(:data AS jsonb),
                    CURRENT_TIMESTAMP,
                    CAST(:created_by AS uuid)
                )
                """
            )
            # Use session_id as created_by for now (can be changed if user_id is available)
            db.execute(ins_q, {
                "id": session_id,
                "data": data_json,
                "created_by": session_id
            })

        db.commit()

        return MessageResponse(message="Invocation IDs updated successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in set_invocation_ids: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
