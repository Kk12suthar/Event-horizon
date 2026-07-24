"""Authentication Service Router"""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime
import os
import re
import uuid
from typing import Optional
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from utils.mailgun_service import get_mailgun_service


from dataModels.authModels import (
    SignupRequest,
    SigninRequest,
    AuthResponse,
    UserProfile,
    ErrorResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest
)
from utils.firebase_auth import get_firebase_auth_manager
from utils.authentication import (
    create_access_token,
    decode_access_token,
    validate_email,
    validate_password_strength,
    create_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from utils.refresh_token_db import store_refresh_token
from utils.rate_limit_tracker import (
    record_failed_login,
    is_account_locked,
    clear_login_attempts
)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
security = HTTPBearer()

# Import limiter for rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Firebase configuration - Update these with your actual values
FIREBASE_CREDENTIALS_PATH = Path(__file__).parent.parent / "firebase-credentials.json"
FIREBASE_WEB_API_KEY = os.getenv(
    "FIREBASE_WEB_API_KEY",
    "your-firebase-web-api-key"  # Update this from Firebase Console
)


def get_firebase_manager():
    """Get Firebase Auth Manager instance"""
    try:
        return get_firebase_auth_manager(FIREBASE_CREDENTIALS_PATH, FIREBASE_WEB_API_KEY)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Firebase initialization failed: {str(e)}"
        )


def extract_tenant_from_email(email: str) -> Optional[str]:
    """Extract tenant (company domain) from email address"""
    try:
        if '@' not in email:
            return None
        
        domain = email.split('@')[1].lower()
        # Convert domain to valid identifier
        tenant_name = re.sub(r'[^a-z0-9-]', '-', domain.replace('.', '-'))
        tenant_name = re.sub(r'^-+|-+$', '', tenant_name)
        return tenant_name[:50]
    except Exception as e:
        print(f"Error extracting tenant: {e}")
        return None


def is_personal_email(email: str) -> bool:
    """Check if email is from a personal/consumer email provider"""
    if not email or '@' not in email:
        return False
    
    domain = email.split('@')[1].lower()
    personal_domains = {
        'gmail.com', 'googlemail.com',
        'yahoo.com', 'yahoo.co.uk', 'yahoo.co.in',
        'hotmail.com', 'outlook.com', 'live.com',
        'aol.com', 'protonmail.com', 'icloud.com'
    }
    
    return domain in personal_domains


@router.post("/signup", response_model=AuthResponse)
@limiter.limit("5/hour")
async def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)):
    """
    Register a new user account
    
    Rate limit: 5 requests per hour (prevents spam signups)
    
    **Request Body:**
    - email: User email address
    - password: Password (minimum 6 characters)
    - full_name: User's full name
    - plan: Account plan ("demo" or "pro", default: "demo")
    
    **Returns:**
    - success: Boolean indicating success
    - message: Success/error message
    - access_token: JWT access token
    - user: User profile data
    
    **Error Cases:**
    - 400: Invalid input or personal email with pro plan
    - 409: Email already exists
    - 500: Server error
    """
    print(f"\n{'='*60}")
    print(f"🔵 SIGNUP REQUEST STARTED")
    print(f"Email: {payload.email}")
    print(f"Name: {payload.full_name}")
    print(f"Plan: {payload.plan}")
    print(f"{'='*60}\n")
    
    try:
        normalized_email = payload.email.strip().lower()
        if is_dev_gmail_signin_enabled() and is_gmail_email(normalized_email):
            print("Using local Gmail dev sign-in path")
            return create_dev_gmail_signin_response(normalized_email, request)

        firebase_manager = get_firebase_manager()
        print("✅ Firebase manager initialized")
        
        # Validate email
        if not validate_email(payload.email):
            print("❌ Email validation failed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )
        
        print("✅ Email validation passed")
        
        # Validate password strength
        is_valid, error_msg = validate_password_strength(payload.password)
        print(f"Password validation: {is_valid}")
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        
        # Personal accounts are accepted, but are always placed on the demo plan.
        plan = "demo" if is_personal_email(payload.email) else payload.plan
        print(f"Final plan: {plan}")
        
        # Create user in Firebase
        print("🔄 Creating user in Firebase Auth...")
        success, error_msg, firebase_user = firebase_manager.create_user(
            payload.email,
            payload.password,
            payload.full_name
        )
        
        if not success:
            print(f"❌ Firebase user creation failed: {error_msg}")
            status_code = status.HTTP_409_CONFLICT if "already exists" in error_msg else status.HTTP_500_INTERNAL_SERVER_ERROR
            raise HTTPException(status_code=status_code, detail=error_msg)
        
        print(f"✅ Firebase user created: {firebase_user.uid}")
        
        # Extract tenant information
        tenant = extract_tenant_from_email(payload.email)
        print(f"Tenant: {tenant}")
        
        # Create user document in Firestore
        user_data = {
            "email": payload.email,
            "name": payload.full_name,
            "plan": plan,
            "tenant": tenant,
            "created_at": datetime.utcnow().isoformat(),
            "auth_method": "email_signup"
        }
        
        print("🔄 Creating user document in Firestore...")
        firebase_manager.create_user_document(firebase_user.uid, user_data)
        print("✅ Firestore document created")
        
        # Create user in PostgreSQL database
        print("\n🔄 Creating user in PostgreSQL...")
        try:
            # Determine default role based on plan
            default_role = "ADMIN"
            print(f"Default role: {default_role}")
            
            # Check if user already exists in PostgreSQL
            check_user_q = text(
                """
                SELECT id FROM instance01.mtd_users WHERE email = :email
                """
            )
            existing_user = db.execute(check_user_q, {"email": payload.email}).fetchone()
            print(f"Existing user check: {existing_user is not None}")
            
            if not existing_user:
                print(f"Inserting new user with ID: {firebase_user.uid}")
                insert_user_q = text(
                    """
                    INSERT INTO instance01.mtd_users(id, name, email, role)
                    VALUES (:id, :name, :email, :role)
                    """
                )
                db.execute(insert_user_q, {
                    "id": firebase_user.uid,
                    "name": payload.full_name,
                    "email": payload.email,
                    "role": default_role
                })
                db.commit()
                print(f"✅ PostgreSQL user created successfully")
                print(f"   - ID: {firebase_user.uid}")
                print(f"   - Email: {payload.email}")
                print(f"   - Role: {default_role}")
            else:
                print(f"ℹ️ PostgreSQL user already exists: {payload.email}")
        except Exception as db_error:
            print(f"❌ PostgreSQL user creation failed: {db_error}")
            print(f"   Error type: {type(db_error).__name__}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            # Don't fail the signup if PostgreSQL insert fails
            db.rollback()
        
        # Create path for verification link
        domain_address = os.getenv("DOMAIN_ADDRESS", "http://localhost:5173").rstrip("/")
        
        # Generate verification link
        print("\n📧 Generating email verification link...")
        firebase_verify_link = firebase_manager.generate_email_verification_link(payload.email)
        
        if firebase_verify_link:
            # Parse oobCode
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(firebase_verify_link)
            oob_code = parse_qs(parsed_url.query).get('oobCode', [None])[0]
            
            if oob_code:
                custom_verify_link = f"{domain_address}/verify-email?oobCode={oob_code}"
                print(f"🔗 Custom verification link: {custom_verify_link}")
                
                # Send verification email via Mailgun
                mailgun = get_mailgun_service()
                email_result = mailgun.send_verification_email(
                    email=payload.email,
                    full_name=payload.full_name,
                    verification_link=custom_verify_link
                )
                
                if email_result["success"]:
                    print(f"✅ Verification email sent successfully")
                else:
                    print(f"⚠️ Verification email send failed: {email_result['error']}")
        
        # Prepare response - DO NOT include tokens if email verification is required
        print("\n📦 Preparing response...")
        user_profile = {
            "uid": firebase_user.uid,
            "email": payload.email,
            "name": payload.full_name,
            "plan": plan,
            "tenant": tenant
        }
        
        # In this flow, we stop here and ask user to verify email
        return AuthResponse(
            success=True,
            message="Account created! Please check your email to verify your account before signing in.",
            access_token=None,  # No token until verified
            user=user_profile
        )
        
    except HTTPException as he:
        print(f"❌ HTTP Exception: {he.detail}")
        print(f"{'='*60}\n")
        raise
    except Exception as e:
        print(f"❌ Unexpected signup error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        print(f"{'='*60}\n")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sign-up failed: {str(e)}"
        )



def is_dev_gmail_signin_enabled() -> bool:
    """Allow local Gmail sign-in only when explicitly enabled outside production."""
    enabled = os.getenv("ENABLE_DEV_GMAIL_SIGNIN", "false").lower() in {"1", "true", "yes", "on"}
    environment = os.getenv("ENVIRONMENT", "development").lower()
    return enabled and environment != "production"


def is_gmail_email(email: str) -> bool:
    domain = email.strip().lower().split("@")[-1]
    return domain in {"gmail.com", "googlemail.com"}


def dev_display_name(email: str) -> str:
    local_part = email.split("@")[0] or "gmail-user"
    words = [word for word in re.split(r"[._-]+", local_part) if word]
    return " ".join(word.capitalize() for word in words) or "Gmail User"


def ensure_dev_gmail_user(uid: str, email: str, name: str) -> None:
    db_gen = get_db()
    db = next(db_gen)
    try:
        existing = db.execute(
            text("SELECT id FROM instance01.mtd_users WHERE email = :email"),
            {"email": email},
        ).fetchone()
        if not existing:
            db.execute(
                text(
                    """
                    INSERT INTO instance01.mtd_users(id, name, email, role)
                    VALUES (:id, :name, :email, :role)
                    """
                ),
                {"id": uid, "name": name, "email": email, "role": "ADMIN"},
            )
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


def create_dev_gmail_signin_response(email: str, request: Request) -> dict:
    normalized_email = email.strip().lower()
    uid = f"dev-gmail-{re.sub(r'[^a-z0-9]+', '-', normalized_email).strip('-')}"
    display_name = dev_display_name(normalized_email)
    tenant = extract_tenant_from_email(normalized_email)
    user_plan = "demo"

    ensure_dev_gmail_user(uid, normalized_email, display_name)

    token_data = {
        "sub": uid,
        "email": normalized_email,
        "name": display_name,
        "plan": user_plan,
        "tenant": tenant,
        "auth_method": "dev_gmail",
    }
    access_token = create_access_token(token_data)
    family_id = str(uuid.uuid4())
    refresh_token, refresh_token_hash = create_refresh_token(uid, family_id)

    try:
        db_gen = get_db()
        db = next(db_gen)
        try:
            from datetime import timedelta
            expires_at = datetime.utcnow() + timedelta(days=7)
            store_refresh_token(
                db=db,
                user_id=uid,
                token_hash=refresh_token_hash,
                family_id=family_id,
                expires_at=expires_at,
                user_agent=request.headers.get("user-agent"),
                ip_address=request.client.host if request.client else None,
            )
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    except Exception as exc:
        print(f"Warning: Could not store dev Gmail refresh token: {exc}")

    return {
        "success": True,
        "message": "Signed in with local Gmail dev account.",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "token_type": "bearer",
        "user": {
            "uid": uid,
            "email": normalized_email,
            "name": display_name,
            "plan": user_plan,
            "tenant": tenant,
        },
    }
@router.post("/signin", response_model=AuthResponse)
@limiter.limit("10/minute")
async def signin(request: Request, payload: SigninRequest):
    """
    Sign in an existing user
    
    Rate limit: 10 requests per minute (prevents brute force)
    
    **Request Body:**
    - email: User email address
    - password: User password
    
    **Returns:**
    - success: Boolean indicating success
    - message: Success/error message
    - access_token: JWT access token
    - user: User profile data
    
    **Error Cases:**
    - 400: Invalid input
    - 401: Invalid credentials
    - 403: Account disabled
    - 429: Too many attempts
    - 500: Server error
    """
    print(f"\n{'='*60}")
    print(f"🔵 SIGNIN REQUEST STARTED")
    print(f"Email: {payload.email}")
    print(f"{'='*60}\n")
    
    try:
        normalized_email = payload.email.strip().lower()
        if is_dev_gmail_signin_enabled() and is_gmail_email(normalized_email):
            print("Using local Gmail dev sign-in path")
            return create_dev_gmail_signin_response(normalized_email, request)

        firebase_manager = get_firebase_manager()
        print("✅ Firebase manager initialized")
        
        # Validate email
        if not validate_email(payload.email):
            print("❌ Email validation failed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )
        
        print("✅ Email validation passed")
        
        # Check if account is locked due to too many failed attempts
        is_locked, remaining_minutes = is_account_locked(payload.email)
        if is_locked:
            print(f"❌ Account locked: {payload.email} - {remaining_minutes} minutes remaining")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed login attempts. Account locked. Please try again in {remaining_minutes} minute(s)."
            )
        
        # Verify password with Firebase
        print("🔄 Verifying password with Firebase...")
        auth_success, error_code, error_message, firebase_auth_data = firebase_manager.verify_password(
            payload.email,
            payload.password
        )
        
        if not auth_success:
            print(f"❌ Firebase authentication failed: {error_code} - {error_message}")
            
            # Record failed login attempt
            record_failed_login(payload.email)
            print(f"⚠️ Failed login attempt recorded for: {payload.email}")
            
            # Map error codes to HTTP status codes
            status_map = {
                'EMAIL_NOT_FOUND': status.HTTP_401_UNAUTHORIZED,
                'INVALID_PASSWORD': status.HTTP_401_UNAUTHORIZED,
                'USER_DISABLED': status.HTTP_403_FORBIDDEN,
                'TOO_MANY_ATTEMPTS_TRY_LATER': status.HTTP_429_TOO_MANY_REQUESTS,
            }
            
            status_code = status_map.get(error_code, status.HTTP_401_UNAUTHORIZED)
            raise HTTPException(status_code=status_code, detail=error_message)
        
        print("✅ Firebase authentication successful")
        
        # Get user from Firebase Auth
        print("🔄 Fetching user from Firebase Auth...")
        success, error_msg, firebase_user = firebase_manager.get_user_by_email(payload.email)
        
        if not success:
            print(f"⚠️ Could not fetch Firebase user: {error_msg}")
            # Fallback: use data from REST API response
            uid = firebase_auth_data.get('localId', payload.email.replace('@', '_at_').replace('.', '_'))
            display_name = payload.email.split('@')[0]
            print(f"Using fallback UID: {uid}")
        else:
            uid = firebase_user.uid
            display_name = firebase_user.display_name or payload.email.split('@')[0]
            print(f"✅ Firebase user found: {uid}")
            
            # Check if email is verified
            if not firebase_user.email_verified:
                print(f"❌ Email not verified for: {payload.email}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Please verify your email address before signing in. Check your inbox for the verification link."
                )
        
        # Get user data from Firestore
        print("\n🔄 Fetching user data from Firestore...")
        user_plan = "pro"  # Default
        tenant = extract_tenant_from_email(payload.email)
        
        success, error_msg, user_data = firebase_manager.get_user_document(uid)
        if success and user_data:
            user_plan = user_data.get('plan', 'pro')
            tenant = user_data.get('tenant', tenant)
            print(f"✅ Firestore data found - Plan: {user_plan}, Tenant: {tenant}")
        else:
            print(f"⚠️ Firestore data not found: {error_msg}. Using defaults.")
        
        # Clear login attempts on successful authentication
        clear_login_attempts(payload.email)
        print("✅ Login attempts cleared for successful authentication")
        
        # Create JWT access token
        token_data = {
            "sub": uid,
            "email": payload.email,
            "name": display_name,
            "plan": user_plan,
            "tenant": tenant
        }
        access_token = create_access_token(token_data)
        print("✅ JWT access token created")
        
        # Create refresh token
        import uuid
        from datetime import timedelta
        family_id = str(uuid.uuid4())
        refresh_token, refresh_token_hash = create_refresh_token(uid, family_id)
        
        # Store refresh token in database
        expires_at = datetime.utcnow() + timedelta(days=7)
        try:
            from database import get_db
            db_gen = get_db()
            db = next(db_gen)
            store_refresh_token(
                db=db,
                user_id=uid,
                token_hash=refresh_token_hash,
                family_id=family_id,
                expires_at=expires_at
            )
            print("✅ Refresh token created and stored")
        except Exception as e:
            print(f"⚠️ Warning: Could not store refresh token: {e}")
            # Continue anyway - user can still sign in with access token
        
        # Prepare response
        print("\n📦 Preparing response...")
        user_profile = {
            "uid": uid,
            "email": payload.email,
            "name": display_name,
            "plan": user_plan,
            "tenant": tenant
        }
        
        response = AuthResponse(
            success=True,
            message=f"Welcome back! Signed in to {tenant} tenant.",
            access_token=access_token,
            user=user_profile
        )
        
        # Add refresh token to response
        response_dict = response.dict()
        response_dict["refresh_token"] = refresh_token
        response_dict["expires_in"] = ACCESS_TOKEN_EXPIRE_MINUTES * 60
        
        print(f"✅ SIGNIN COMPLETED SUCCESSFULLY")
        print(f"{'='*60}\n")
        return response_dict
        
    except HTTPException as he:
        print(f"❌ HTTP Exception: {he.detail}")
        print(f"{'='*60}\n")
        raise
    except Exception as e:
        print(f"❌ Unexpected signin error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        print(f"{'='*60}\n")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sign-in failed: {str(e)}"
        )


@router.get("/me", response_model=UserProfile)
@limiter.limit("100/minute")
async def get_current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get current authenticated user profile
    
    Rate limit: 100 requests per minute
    
    **Headers:**
    - Authorization: Bearer {access_token}
    
    **Returns:**
    - User profile data
    
    **Error Cases:**
    - 401: Invalid or expired token
    - 404: User not found
    - 500: Server error
    """
    try:
        # Decode JWT token
        token_data = decode_access_token(credentials.credentials)
        
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        
        firebase_manager = get_firebase_manager()
        
        # Get user from Firestore
        uid = token_data.get("sub")
        success, error_msg, user_data = firebase_manager.get_user_document(uid)
        
        if not success or not user_data:
            # Fallback to token data
            return UserProfile(
                uid=uid,
                email=token_data.get("email"),
                name=token_data.get("name"),
                plan=token_data.get("plan", "pro"),
                tenant=token_data.get("tenant")
            )
        
        return UserProfile(
            uid=uid,
            email=user_data.get("email"),
            name=user_data.get("name"),
            plan=user_data.get("plan", "pro"),
            tenant=user_data.get("tenant"),
            picture=user_data.get("picture", ""),
            created_at=user_data.get("created_at")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Get user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user: {str(e)}"
        )


@router.post("/signout")
async def signout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Sign out current user (client should delete token)
    
    **Headers:**
    - Authorization: Bearer {access_token}
    
    **Returns:**
    - Success message
    """
    # You could implement token blacklisting here if needed
    return {
        "success": True,
        "message": "Signed out successfully. Please delete your access token."
    }


@router.post("/forgot-password")
@limiter.limit("5/hour")
async def forgot_password(request: Request, payload: ForgotPasswordRequest):
    """
    Send a password reset email
    
    Rate limit: 5 requests per hour (prevents email spam)
    
    **Request Body:**
    - email: User email address
    
    **Returns:**
    - success: Boolean indicating success
    - message: Success/error message
    """
    print(f"\n{'='*60}")
    print(f"🔵 FORGOT PASSWORD REQUEST STARTED")
    print(f"Email: {payload.email}")
    print(f"{'='*60}\n")
    
    try:
        normalized_email = payload.email.strip().lower()
        if is_dev_gmail_signin_enabled() and is_gmail_email(normalized_email):
            print("Using local Gmail dev sign-in path")
            return create_dev_gmail_signin_response(normalized_email, request)

        firebase_manager = get_firebase_manager()
        mailgun = get_mailgun_service()

        # Get user details to personalise the email
        user_success, _, firebase_user = firebase_manager.get_user_by_email(payload.email)
        full_name = "User"
        if user_success and firebase_user:
            full_name = firebase_user.display_name or payload.email.split('@')[0]

        # Use Firebase Admin SDK to generate OOB code - no email is sent by Firebase
        firebase_reset_link = firebase_manager.generate_password_reset_link(payload.email)

        if not firebase_reset_link:
            print(f"❌ Failed to generate reset link for: {payload.email}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate password reset link. Please ensure the email is correct."
            )

        # Parse the oobCode out of the Firebase link
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(firebase_reset_link)
        oob_code = parse_qs(parsed_url.query).get('oobCode', [None])[0]

        if not oob_code:
            print(f"❌ Failed to extract oobCode from link")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal error processing reset link"
            )

        # Build the custom frontend reset URL
        domain_address = os.getenv("DOMAIN_ADDRESS").rstrip("/")
        custom_reset_link = f"{domain_address}/reset-password?oobCode={oob_code}"
        print(f"🔗 Custom reset link: {custom_reset_link}")

        # Send branded reset email via Mailgun
        email_result = mailgun.send_password_reset(
            email=payload.email,
            full_name=full_name,
            reset_link=custom_reset_link
        )

        if not email_result["success"]:
            print(f"❌ Mailgun failed: {email_result['error']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send reset email: {email_result['error']}"
            )

        print(f"✅ Password reset email sent via Mailgun to: {payload.email}")
        print(f"{'='*60}\n")

        return {
            "success": True,
            "message": "Password reset email sent. Please check your inbox."
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected forgot password error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send reset email: {str(e)}"
        )


@router.post("/reset-password")
async def reset_password(request: Request, payload: ResetPasswordRequest):
    """
    Complete password reset using the token from the email
    
    **Request Body:**
    - oob_code: The code from the reset link
    - new_password: The new password
    
    **Returns:**
    - success: Boolean indicating success
    - message: Success/error message
    """
    print(f"\n{'='*60}")
    print(f"🔵 RESET PASSWORD REQUEST STARTED")
    print(f"{'='*60}\n")
    
    try:
        # Validate password strength
        is_valid, error_msg = validate_password_strength(payload.new_password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
            
        firebase_manager = get_firebase_manager()
        
        # Reset password
        success, error_code, error_message = firebase_manager.reset_password(
            payload.oob_code,
            payload.new_password
        )
        
        if not success:
            print(f"❌ Failed to reset password: {error_code} - {error_message}")
            status_code = status.HTTP_400_BAD_REQUEST
            raise HTTPException(status_code=status_code, detail=error_message)
        
        print(f"✅ Password reset successfully")
        print(f"{'='*60}\n")
        
        return {
            "success": True,
            "message": "Password has been reset successfully. You can now sign in with your new password."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected reset password error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset password: {str(e)}"
        )


@router.get("/verify-email")
async def verify_email(oobCode: str):
    """
    Handle email verification from the link
    """
    print(f"\n{'='*60}")
    print(f"🔵 EMAIL VERIFICATION REQUEST STARTED")
    print(f"{'='*60}\n")
    
    try:
        normalized_email = payload.email.strip().lower()
        if is_dev_gmail_signin_enabled() and is_gmail_email(normalized_email):
            print("Using local Gmail dev sign-in path")
            return create_dev_gmail_signin_response(normalized_email, request)

        firebase_manager = get_firebase_manager()
        
        # Verify email
        success, error_code, error_message = firebase_manager.confirm_email_verification(oobCode)
        
        if not success:
            print(f"❌ Failed to verify email: {error_code} - {error_message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        
        print(f"✅ Email verified successfully")
        print(f"{'='*60}\n")
        
        return {
            "success": True,
            "message": "Email verified successfully! You can now sign in."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected email verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify email: {str(e)}"
        )
