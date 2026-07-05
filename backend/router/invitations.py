"""User Invitations Router - Handles invite-based user registration"""

from sqlalchemy.orm import Session
from typing import Dict, Any, List
from database import get_db
from fastapi import Depends, APIRouter, HTTPException, status
from sqlalchemy import text
from schemas import (
    InvitationCreate,
    InvitationVerify,
    InvitationAccept,
    InvitationOut,
    MessageResponse,
)
import uuid
import secrets
from datetime import datetime, timedelta
import hashlib
from utils.email_service import send_invitation_email
from utils.firebase_auth import get_firebase_auth_manager
from utils.mailgun_service import get_mailgun_service
from utils.license_enforcement import enforce_user_limit
from utils.audit_logger import log_admin_action, ACTION_USER_INVITED
import os
from pathlib import Path
import json

router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _hexify(val):
    """Convert UUID objects and binary data to hex strings for PostgreSQL"""
    if isinstance(val, uuid.UUID):
        return str(val)
    elif isinstance(val, (bytes, bytearray)):
        return val.hex()
    return val


def generate_invite_token() -> str:
    """Generate a secure random invitation token"""
    return secrets.token_hex(32)


def hash_password(password: str) -> str:
    """Simple password hashing (in production, use bcrypt or similar)"""
    return hashlib.sha256(password.encode()).hexdigest()


def _update_license_counts(db: Session, role: str, delta: int, update_total_user: bool = True):
    """
    Update license data counts when users are added/removed or roles change

    Args:
        db: Database session
        role: User role (ADMIN, ANALYST, VIEWER)
        delta: +1 for add, -1 for remove
        update_total_user: Whether to update total_user count (True for add/remove, False for role change)
    """
    try:
        # Get current license data
        sel_q = text(
            "SELECT data FROM instance01.data_collection WHERE title = 'license'"
        )
        result = db.execute(sel_q).fetchone()
        if not result:
            return

        # Ensure we have a dict (PostgreSQL returns JSONB as dict)
        license_data = result[0] if isinstance(result[0], dict) else json.loads(result[0])

        # Update counts based on role
        if role == "ADMIN":
            license_data["active_admin"] = str(int(license_data.get("active_admin", "0")) + delta)
        elif role == "ANALYST":
            license_data["active_analyst"] = str(int(license_data.get("active_analyst", "0")) + delta)
        else:  # VIEWER
            license_data["active_viewer"] = str(int(license_data.get("active_viewer", "0")) + delta)

        # Update total active users (sum of all role counts)
        license_data["total_active_user"] = str(
            int(license_data.get("active_admin", "0")) +
            int(license_data.get("active_analyst", "0")) +
            int(license_data.get("active_viewer", "0"))
        )

        # Update total users (all users regardless of role) when adding/removing
        if update_total_user:
            license_data["total_user"] = str(int(license_data.get("total_user", "0")) + delta)

        # Save updated license data
        upd_q = text(
            "UPDATE instance01.data_collection SET data = CAST(:data AS jsonb) WHERE title = 'license'"
        )
        db.execute(upd_q, {"data": json.dumps(license_data)})
    except Exception as exc:
        print(f"Error updating license counts: {exc}")
        raise


# ---------------------------------------------------------------------------
# CRUD ENDPOINTS
# ---------------------------------------------------------------------------


@router.post("/create", response_model=MessageResponse)
def create_invitation(
    payload: InvitationCreate, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Create a new user invitation and send invite email.
    
    **HTTP Method:** POST
    **Path:** /api/v1/invitations/create
    
    **Parameters:**
    - payload: InvitationCreate - Invitation details
    
    **Returns:**
    - MessageResponse with invitation token and details
    
    **Example Request:**
    ```json
    {
      "email": "newuser@example.com",
      "role": "VIEWER",
      "invited_by": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Invitation sent successfully",
      "data": {
        "invite_token": "abc123...",
        "invite_url": "http://localhost:5173/invite-signup?token=abc123..."
      }
    }
    ```
    """
    try:
        print(f"[Invitations] Creating invitation for: {payload.email}")
        print(f"[Invitations] Payload: role={payload.role}, invited_by={payload.invited_by}")
        
        # Enforce license limit before creating invitation
        enforce_user_limit(db, payload.role)
        
        # Check if user already exists
        check_q = text(
            """
            SELECT id FROM instance01.mtd_users
            WHERE email = :email
            """
        )
        existing_user = db.execute(check_q, {"email": payload.email}).fetchone()
        print(f"[Invitations] Existing user check: {existing_user}")
        
        if existing_user:
            print(f"[Invitations] User already exists: {payload.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Check if there's already a pending invitation
        check_invite_q = text(
            """
            SELECT id FROM instance01.mtd_user_invitations
            WHERE email = :email AND status = 'pending'
            """
        )
        existing_invite = db.execute(check_invite_q, {"email": payload.email}).fetchone()
        print(f"[Invitations] Existing invite check: {existing_invite}")
        
        if existing_invite:
            print(f"[Invitations] Pending invitation already exists: {payload.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation already sent to this email"
            )
        
        # Generate invitation token
        invite_token = generate_invite_token()
        invitation_id = str(uuid.uuid4())
        print(f"[Invitations] Generated token: {invite_token[:20]}...")
        print(f"[Invitations] Invitation ID: {invitation_id}")
        
        # Set expiration (7 days from now)
        expires_at = datetime.utcnow() + timedelta(days=7)
        print(f"[Invitations] Expires at: {expires_at}")
        
        # Validate and convert invited_by parameter
        invited_by = payload.invited_by
        print(f"[Invitations] Invited_by: {invited_by}")
            
        # Final validation and debug logging
        # Final debug logging
        print(f"[Invitations] Final invited_by value before query: {invited_by}")
            
        # Check if inviter exists
        inviter_q = text(
            """
            SELECT id FROM instance01.mtd_users
            WHERE id = :uid
            """
        )
        print(f"[Invitations] Inviter exists query: {inviter_q}")
        print(f"[Invitations] Inviter exists query parameters: {invited_by}")
        inviter_exists = db.execute(inviter_q, {"uid": invited_by}).fetchone()
        print(f"[Invitations] Inviter exists check: {inviter_exists}")
        
        if not inviter_exists:
            print(f"[Invitations] ERROR: Inviter does not exist: {invited_by}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Inviter {invited_by} does not exist"
            )
            
        # Insert invitation
        print(f"[Invitations] Inserting invitation into database...")
        insert_q = text(
            """
            INSERT INTO instance01.mtd_user_invitations(
                id, email, role, invited_by, invite_token, status, 
                created_at, expires_at
            )
            VALUES (
                CAST(:id AS uuid), :email, :role, :invited_by, 
                :invite_token, 'pending', CURRENT_TIMESTAMP, :expires_at
            )
            """
        )
        print(f"[Invitations] Insert query parameters: id={invitation_id}, email={payload.email}, role={payload.role}, invited_by={invited_by}, invite_token={invite_token}, expires_at={expires_at}")
        db.execute(insert_q, {
            "id": invitation_id,
            "email": payload.email,
            "role": payload.role,
            "invited_by": invited_by,
            "invite_token": invite_token,
            "expires_at": expires_at
        })
        log_admin_action(db, ACTION_USER_INVITED, actor_id=str(payload.invited_by), target_type="USER", target_id=payload.email, details={"role": payload.role})
        db.commit()
        print(f"[Invitations] Invitation inserted successfully")
        
        # Send email with invitation link
        frontend_url = "http://localhost:5173"  # Get from env in production
        invite_url = f"{frontend_url}/signup?invite_token={invite_token}"
        print(f"[Invitations] Generated invite URL: {invite_url}")
        
        # Get inviter's name (optional, for better email)
        inviter_name = "Admin"
        try:
            inviter_q = text(
                """
                SELECT name FROM instance01.mtd_users
                WHERE id = :uid
                """
            )
            inviter_result = db.execute(inviter_q, {"uid": payload.invited_by}).fetchone()
            if inviter_result:
                inviter_name = inviter_result[0]
                print(f"[Invitations] Inviter name: {inviter_name}")
        except Exception as e:
            print(f"[Invitations] Could not fetch inviter name: {e}")
            pass
        
        # Send invitation email via Mailgun
        print(f"[Invitations] Sending invitation email to {payload.email} via Mailgun...")
        try:
            mailgun = get_mailgun_service()
            email_result = mailgun.send_team_invitation(
                email=payload.email,
                invite_link=invite_url,
                invited_by_name=inviter_name,
                role=payload.role
            )
            email_sent = email_result.get("success", False)
            print(f"[Invitations] Email sent status: {email_sent}")
            if not email_sent:
                print(f"[Invitations] Mailgun error: {email_result.get('error')}")
        except Exception as e:
            print(f"Warning: Failed to send email via Mailgun: {e}")
            # Fallback to stdout log
            send_invitation_email(
                recipient_email=payload.email,
                invite_url=invite_url,
                invited_by_name=inviter_name,
                role=payload.role
            )
        
        response_data = {
            "message": "Invitation sent successfully",
            "data": {
                "invite_token": invite_token,
                "invite_url": invite_url,
                "email": payload.email
            }
        }
        print(f"[Invitations] Returning response: {response_data}")
        return response_data
    except HTTPException as http_exc:
        print(f"[Invitations] HTTP Exception: {http_exc.detail}")
        raise
    except Exception as exc:
        db.rollback()
        print(f"[Invitations] ERROR in create_invitation: {exc}")
        print(f"[Invitations] Exception type: {type(exc).__name__}")
        import traceback
        print(f"[Invitations] Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create invitation: {str(exc)}"
        )


@router.post("/verify", response_model=MessageResponse)
def verify_invitation(
    payload: InvitationVerify, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Verify an invitation token and return invitation details.
    
    **HTTP Method:** POST
    **Path:** /api/v1/invitations/verify
    
    **Parameters:**
    - payload: InvitationVerify - Token to verify
    
    **Returns:**
    - MessageResponse with invitation details
    
    **Example Request:**
    ```json
    {
      "token": "abc123..."
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Valid invitation",
      "data": {
        "email": "newuser@example.com",
        "role": "VIEWER",
        "expires_at": "2025-01-31T12:00:00"
      }
    }
    ```
    """
    try:
        # Fetch invitation
        select_q = text(
            """
            SELECT id, email, role, invited_by, invite_token, status, 
                   created_at, expires_at, accepted_at
            FROM instance01.mtd_user_invitations
            WHERE invite_token = :token
            """
        )
        print(f"[Invitations] Verify query parameters: token={payload.token}")
        result = db.execute(select_q, {"token": payload.token}).fetchone()
        
        if not result:
            print(f"[Invitations] Token not found in database: {payload.token}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invitation token"
            )
        
        invitation = result._asdict() if hasattr(result, "_asdict") else dict(zip(result.keys(), result))
        
        # Convert UUIDs to strings
        for k, v in invitation.items():
            invitation[k] = _hexify(v)
        
        # Check if already accepted
        if invitation['status'] == 'accepted':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation has already been accepted"
            )
        
        # Check if expired
        expires_at = datetime.fromisoformat(str(invitation['expires_at']))
        if datetime.utcnow() > expires_at:
            # Update status to expired
            update_q = text(
                """
                UPDATE instance01.mtd_user_invitations
                SET status = 'expired'
                WHERE invite_token = :token
                """
            )
            print(f"[Invitations] Update query parameters: token={payload.token}")
            db.execute(update_q, {"token": payload.token})
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation has expired"
            )
        
        return {
            "message": "Valid invitation",
            "data": {
                "email": invitation['email'],
                "role": invitation['role'],
                "expires_at": str(invitation['expires_at'])
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error in verify_invitation: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify invitation: {str(exc)}"
        )


@router.post("/accept", response_model=MessageResponse)
def accept_invitation(
    payload: InvitationAccept, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Accept an invitation and create the user account.
    
    **HTTP Method:** POST
    **Path:** /api/v1/invitations/accept
    
    **Parameters:**
    - payload: InvitationAccept - Token, username, and password
    
    **Returns:**
    - MessageResponse with user creation confirmation
    
    **Example Request:**
    ```json
    {
      "token": "abc123...",
      "username": "John Doe",
      "password": "securepassword123"
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Account created successfully",
      "data": {
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "newuser@example.com"
      }
    }
    ```
    """
    print(f"\n{'='*60}")
    print(f"🔵 INVITATION ACCEPTANCE STARTED")
    print(f"Token: {payload.token[:20]}...")
    print(f"Username: {payload.username}")
    print(f"Password provided: {'Yes' if payload.password else 'No'}")
    print(f"{'='*60}\n")
    
    try:
        firebase_manager = get_firebase_auth_manager(
            Path(__file__).parent.parent / "config" / "firebase-credentials.json",
            os.getenv("FIREBASE_WEB_API_KEY")
        )
        print("✅ Firebase manager initialized")
        
        # Verify invitation first
        print("🔄 Verifying invitation token...")
        select_q = text(
            """
            SELECT id, email, role, invited_by, invite_token, status, 
                   created_at, expires_at
            FROM instance01.mtd_user_invitations
            WHERE invite_token = :token
            """
        )
        print(f"[Invitations] Verify query parameters: token={payload.token}")
        result = db.execute(select_q, {"token": payload.token}).fetchone()
        
        if not result:
            print("❌ Invitation token not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invitation token"
            )
        
        invitation = result._asdict() if hasattr(result, "_asdict") else dict(zip(result.keys(), result))
        
        # Convert UUIDs to strings
        for k, v in invitation.items():
            invitation[k] = _hexify(v)
        
        print(f"✅ Invitation found for: {invitation['email']}")
        print(f"   Role: {invitation['role']}")
        print(f"   Status: {invitation['status']}")
        
        # Check if already accepted
        if invitation['status'] == 'accepted':
            print("❌ Invitation already accepted")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation has already been accepted"
            )
        
        # Check if expired
        expires_at = datetime.fromisoformat(str(invitation['expires_at']))
        if datetime.utcnow() > expires_at:
            print("❌ Invitation expired")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation has expired"
            )
        
        # Create user account in Firebase with provided password
        print("\n🔄 Creating Firebase user with provided password...")
        success, error_msg, firebase_user = firebase_manager.create_user(
            invitation['email'],
            payload.password,  # Use the password provided by the user
            payload.username
        )
        
        if not success:
            print(f"❌ Firebase user creation failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create Firebase user: {error_msg}"
            )
        
        print(f"✅ Firebase user created: {firebase_user.uid}")
        
        # Create user document in Firestore
        print("🔄 Creating Firestore document...")
        user_data = {
            "email": invitation['email'],
            "name": payload.username,
            "role": invitation['role'],
            "created_at": datetime.utcnow().isoformat(),
            "auth_method": "invitation"
        }
        firebase_manager.create_user_document(firebase_user.uid, user_data)
        print("✅ Firestore document created")
        
        # Create user in database - Use Firebase UID instead of generating new UUID
        print("\n🔄 Creating PostgreSQL user...")
        
        insert_user_q = text(
            """
            INSERT INTO instance01.mtd_users(id, name, email, role)
            VALUES (:id, :name, :email, :role)
            """
        )
        print(f"[Invitations] Insert query parameters: id={firebase_user.uid}, name={payload.username}, email={invitation['email']}, role={invitation['role']}")
        db.execute(insert_user_q, {
            "id": firebase_user.uid,  # Use Firebase UID for consistency
            "name": payload.username,
            "email": invitation['email'],
            "role": invitation['role']
        })
        print(f"✅ PostgreSQL user created with ID: {firebase_user.uid}")

        # Update license counts for the new user
        print("🔄 Updating license counts...")
        _update_license_counts(db, invitation['role'], 1, update_total_user=True)
        print("✅ License counts updated")

        # Update invitation status
        print("🔄 Updating invitation status...")
        update_invite_q = text(
            """
            UPDATE instance01.mtd_user_invitations
            SET status = 'accepted', accepted_at = CURRENT_TIMESTAMP
            WHERE invite_token = :token
            """
        )
        print(f"[Invitations] Update query parameters: token={payload.token}")
        db.execute(update_invite_q, {"token": payload.token})
        
        db.commit()
        print("✅ Database committed")
        
        print(f"\n✅ INVITATION ACCEPTANCE COMPLETED")
        print(f"{'='*60}\n")
        
        return {
            "message": "Account created successfully",
            "data": {
                "user_id": firebase_user.uid,  # Return Firebase UID
                "email": invitation['email'],
                "role": invitation['role']
            }
        }
    except HTTPException as he:
        print(f"❌ HTTP Exception: {he.detail}")
        print(f"{'='*60}\n")
        raise
    except Exception as exc:
        db.rollback()
        print(f"❌ Unexpected error in accept_invitation: {exc}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        print(f"{'='*60}\n")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to accept invitation: {str(exc)}"
        )


@router.get("/list", response_model=List[InvitationOut])
def list_invitations(
    status_filter: str = None, db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    List all invitations, optionally filtered by status.
    
    **HTTP Method:** GET
    **Path:** /api/v1/invitations/list
    
    **Query Parameters:**
    - status_filter: Optional status filter (pending, accepted, expired)
    
    **Returns:**
    - List of invitations
    
    **Example Request:**
    ```
    GET /api/v1/invitations/list?status_filter=pending
    ```
    
    **Example Response:**
    ```json
    [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "newuser@example.com",
        "role": "VIEWER",
        "invited_by": "660e8400-e29b-41d4-a716-446655440000",
        "invite_token": "abc123...",
        "status": "pending",
        "created_at": "2025-01-24T12:00:00",
        "expires_at": "2025-01-31T12:00:00",
        "accepted_at": null
      }
    ]
    ```
    """
    try:
        if status_filter:
            query = text(
                """
                SELECT id, email, role, invited_by, invite_token, status,
                       created_at, expires_at, accepted_at
                FROM instance01.mtd_user_invitations
                WHERE status = :status
                ORDER BY created_at DESC
                """
            )
            print(f"[Invitations] List query parameters: status={status_filter}")
            rows = db.execute(query, {"status": status_filter}).fetchall()
        else:
            query = text(
                """
                SELECT id, email, role, invited_by, invite_token, status,
                       created_at, expires_at, accepted_at
                FROM instance01.mtd_user_invitations
                ORDER BY created_at DESC
                """
            )
            rows = db.execute(query).fetchall()
        
        invitations = []
        for row in rows:
            invite_dict = (
                row._asdict() if hasattr(row, "_asdict") else dict(zip(row.keys(), row))
            )
            for k, v in invite_dict.items():
                invite_dict[k] = _hexify(v) if v is not None else None
            invitations.append(invite_dict)
        
        return invitations
    except Exception as exc:
        print(f"Error in list_invitations: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list invitations: {str(exc)}"
        )


@router.delete("/revoke/{token}", response_model=MessageResponse)
def revoke_invitation(token: str, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Revoke a pending invitation.
    
    **HTTP Method:** DELETE
    **Path:** /api/v1/invitations/revoke/{token}
    
    **Parameters:**
    - token: Invitation token to revoke
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```
    DELETE /api/v1/invitations/revoke/abc123...
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Invitation revoked successfully",
      "data": null
    }
    ```
    """
    try:
        # Check if invitation exists and is pending
        check_q = text(
            """
            SELECT status FROM instance01.mtd_user_invitations
            WHERE invite_token = :token
            """
        )
        print(f"[Invitations] Revoke query parameters: token={token}")
        result = db.execute(check_q, {"token": token}).fetchone()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found"
            )
        
        if result[0] != 'pending':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only revoke pending invitations"
            )
        
        # Delete the invitation
        delete_q = text(
            """
            DELETE FROM instance01.mtd_user_invitations
            WHERE invite_token = :token
            """
        )
        print(f"[Invitations] Delete query parameters: token={token}")
        db.execute(delete_q, {"token": token})
        db.commit()
        
        return {
            "message": "Invitation revoked successfully",
            "data": None
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        print(f"Error in revoke_invitation: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke invitation: {str(exc)}"
        )
