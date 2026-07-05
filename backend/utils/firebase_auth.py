"""
Firebase Authentication Utility
Handles user authentication, signup, and session management using Firebase
"""

import requests
import firebase_admin
from firebase_admin import credentials, auth, firestore
from typing import Tuple, Optional, Dict, Any
import os


class FirebaseAuthManager:
    """Manages Firebase authentication operations"""
    
    def __init__(self, credentials_path: str, web_api_key: str):
        """
        Initialize Firebase Auth Manager
        
        Args:
            credentials_path: Path to Firebase service account JSON file
            web_api_key: Firebase Web API key from Firebase Console
        """
        self.web_api_key = web_api_key
        
        # Initialize Firebase Admin SDK
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(credentials_path)
                firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            print("✅ Firebase initialized successfully!")
        except Exception as e:
            print(f"⚠️ Firebase initialization error: {e}")
            self.db = None
    
    def verify_password(self, email: str, password: str) -> Tuple[bool, Optional[str], Optional[str], Optional[Dict]]:
        """
        Verify user password using Firebase REST API
        
        Args:
            email: User email address
            password: User password
            
        Returns:
            Tuple of (success, error_code, error_message, user_data)
        """
        try:
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.web_api_key}"
            
            payload = {
                "email": email,
                "password": password,
                "returnSecureToken": True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                user_data = response.json()
                return True, None, None, user_data
            else:
                error_data = response.json().get('error', {})
                error_code = error_data.get('message', 'UNKNOWN_ERROR')
                
                error_messages = {
                    'EMAIL_NOT_FOUND': 'No account found with this email address.',
                    'INVALID_PASSWORD': 'Incorrect password.',
                    'USER_DISABLED': 'This account has been disabled.',
                    'TOO_MANY_ATTEMPTS_TRY_LATER': 'Too many failed attempts. Try again later.',
                    'INVALID_EMAIL': 'Invalid email address format.',
                    'MISSING_PASSWORD': 'Password is required.',
                }
                
                error_message = error_messages.get(error_code, f'Authentication failed: {error_code}')
                return False, error_code, error_message, None
                
        except requests.exceptions.ConnectionError:
            return False, 'CONNECTION_ERROR', 'Cannot connect to authentication service.', None
        except requests.exceptions.Timeout:
            return False, 'TIMEOUT', 'Authentication service timeout.', None
        except Exception as e:
            print(f"Password verification error: {e}")
            return False, 'UNKNOWN_ERROR', f'Authentication error: {str(e)}', None
    
    def create_user(self, email: str, password: str, display_name: str) -> Tuple[bool, Optional[str], Optional[Any]]:
        """
        Create a new user in Firebase Auth
        
        Args:
            email: User email address
            password: User password (min 6 characters)
            display_name: User's full name
            
        Returns:
            Tuple of (success, error_message, firebase_user)
        """
        try:
            # Check if user already exists
            try:
                existing_user = auth.get_user_by_email(email)
                if existing_user:
                    return False, 'An account with this email already exists.', None
            except auth.UserNotFoundError:
                pass  # User doesn't exist, which is what we want
            
            # Create user
            firebase_user = auth.create_user(
                email=email,
                password=password,
                display_name=display_name
            )
            
            print(f"✅ Created Firebase Auth user: {firebase_user.uid}")
            return True, None, firebase_user
            
        except auth.EmailAlreadyExistsError:
            return False, 'An account with this email already exists.', None
        except Exception as e:
            print(f"❌ Firebase Auth user creation failed: {e}")
            return False, f'Failed to create account: {str(e)}', None
    
    def get_user_by_email(self, email: str) -> Tuple[bool, Optional[str], Optional[Any]]:
        """
        Get user from Firebase Auth by email
        
        Args:
            email: User email address
            
        Returns:
            Tuple of (success, error_message, firebase_user)
        """
        try:
            firebase_user = auth.get_user_by_email(email)
            return True, None, firebase_user
        except auth.UserNotFoundError:
            return False, 'User not found', None
        except Exception as e:
            print(f"Error getting user: {e}")
            return False, str(e), None
    
    def delete_user(self, uid: str) -> Tuple[bool, Optional[str]]:
        """
        Delete a user from Firebase Auth
        
        Args:
            uid: User ID
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            auth.delete_user(uid)
            return True, None
        except Exception as e:
            print(f"Error deleting user: {e}")
            return False, str(e)
    
    def create_user_document(self, uid: str, user_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Create user document in Firestore
        
        Args:
            uid: User ID
            user_data: User data to store
            
        Returns:
            Tuple of (success, error_message)
        """
        if not self.db:
            return False, "Firestore not initialized"
        
        try:
            self.db.collection('users').document(uid).set(user_data)
            return True, None
        except Exception as e:
            print(f"Error creating user document: {e}")
            return False, str(e)
    
    def get_user_document(self, uid: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Get user document from Firestore
        
        Args:
            uid: User ID
            
        Returns:
            Tuple of (success, error_message, user_data)
        """
        if not self.db:
            return False, "Firestore not initialized", None
        
        try:
            user_doc = self.db.collection('users').document(uid).get()
            if user_doc.exists:
                return True, None, user_doc.to_dict()
            else:
                return False, "User document not found", None
        except Exception as e:
            print(f"Error getting user document: {e}")
            return False, str(e), None
    
    def update_user_document(self, uid: str, update_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Update user document in Firestore
        
        Args:
            uid: User ID
            update_data: Data to update
            
        Returns:
            Tuple of (success, error_message)
        """
        if not self.db:
            return False, "Firestore not initialized"
        
        try:
            self.db.collection('users').document(uid).update(update_data)
            return True, None
        except Exception as e:
            print(f"Error updating user document: {e}")
            return False, str(e)


    def generate_password_reset_link(self, email: str) -> Optional[str]:
        """
        Generate a password reset link using Firebase Admin SDK.
        No email is sent by Firebase - link is passed to Mailgun for branded delivery.
        
        Args:
            email: User email address
            
        Returns:
            The Firebase reset link string (contains oobCode), or None if failed
        """
        try:
            link = auth.generate_password_reset_link(email)
            return link
        except Exception as e:
            print(f"Error generating reset link: {e}")
            return None

    def generate_email_verification_link(self, email: str) -> Optional[str]:
        """
        Generate an email verification link using Firebase Admin SDK.
        No email is sent by Firebase - link is passed to Mailgun for branded delivery.
        
        Args:
            email: User email address
            
        Returns:
            The Firebase verification link string (contains oobCode), or None if failed
        """
        try:
            link = auth.generate_email_verification_link(email)
            return link
        except Exception as e:
            print(f"Error generating email verification link: {e}")
            return None

    def confirm_email_verification(self, oob_code: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Confirm email verification using the OOB code from the email
        
        Args:
            oob_code: The out-of-band code sent to the user
            
        Returns:
            Tuple of (success, error_code, error_message)
        """
        try:
            # Firebase Auth REST API endpoint for verification
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={self.web_api_key}"
            
            payload = {
                "oobCode": oob_code
            }
            
            print(f"🔄 Backend calling Firebase Verify Email REST API...")
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return True, None, None
            else:
                print(f"❌ Firebase verification failed with status {response.status_code}")
                print(f"❌ Response text: {response.text}")
                
                try:
                    error_data = response.json().get('error', {})
                    error_code = error_data.get('message', 'UNKNOWN_ERROR')
                except Exception:
                    # In case response isn't JSON
                    error_code = f"HTTP_{response.status_code}"
                
                error_messages = {
                    'EXPIRED_OOB_CODE': 'The verification link has expired.',
                    'INVALID_OOB_CODE': 'The verification link is invalid.',
                    'USER_DISABLED': 'This account has been disabled.',
                    'USER_NOT_FOUND': 'No account found for this verification link.',
                }
                
                error_message = error_messages.get(error_code, f'Failed to verify email: {error_code}')
                return False, error_code, error_message
                
        except Exception as e:
            print(f"Confirm email verification error: {e}")
            return False, 'UNKNOWN_ERROR', str(e)

    def reset_password(self, oob_code: str, new_password: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Reset user password using the OOB code from the email
        
        Args:
            oob_code: The out-of-band code sent to the user
            new_password: The new password
            
        Returns:
            Tuple of (success, error_code, error_message)
        """
        try:
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:resetPassword?key={self.web_api_key}"
            
            payload = {
                "oobCode": oob_code,
                "newPassword": new_password
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return True, None, None
            else:
                error_data = response.json().get('error', {})
                error_code = error_data.get('message', 'UNKNOWN_ERROR')
                
                error_messages = {
                    'EXPIRED_OOB_CODE': 'The password reset link has expired.',
                    'INVALID_OOB_CODE': 'The password reset link is invalid.',
                    'USER_DISABLED': 'This account has been disabled.',
                    'USER_NOT_FOUND': 'No account found for this reset link.',
                    'WEAK_PASSWORD': 'The new password is too weak.',
                }
                
                error_message = error_messages.get(error_code, f'Failed to reset password: {error_code}')
                return False, error_code, error_message
                
        except Exception as e:
            print(f"Reset password error: {e}")
            return False, 'UNKNOWN_ERROR', str(e)


# Singleton instance
_firebase_auth_manager: Optional[FirebaseAuthManager] = None


def get_firebase_auth_manager(credentials_path: str = None, web_api_key: str = None) -> FirebaseAuthManager:
    """
    Get or create Firebase Auth Manager singleton
    
    Args:
        credentials_path: Path to Firebase credentials (required on first call)
        web_api_key: Firebase Web API key (required on first call)
        
    Returns:
        FirebaseAuthManager instance
    """
    global _firebase_auth_manager
    
    if _firebase_auth_manager is None:
        if not credentials_path or not web_api_key:
            raise ValueError("credentials_path and web_api_key required for first initialization")
        _firebase_auth_manager = FirebaseAuthManager(credentials_path, web_api_key)
    
    return _firebase_auth_manager
