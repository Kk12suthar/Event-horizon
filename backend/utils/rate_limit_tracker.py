"""Track login attempts to prevent brute force attacks"""

from datetime import datetime, timedelta
from typing import Dict, Tuple, List

# In-memory storage (use Redis in production for multi-server deployments)
# For single-server deployments, this is sufficient
login_attempts: Dict[str, List[datetime]] = {}

# Configuration
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def record_failed_login(email: str) -> None:
    """
    Record a failed login attempt for an email address
    
    Args:
        email: Email address that failed login
    """
    if email not in login_attempts:
        login_attempts[email] = []
    
    # Add current attempt
    login_attempts[email].append(datetime.utcnow())
    
    # Clean old attempts (older than lockout period)
    cutoff = datetime.utcnow() - timedelta(minutes=LOCKOUT_MINUTES)
    login_attempts[email] = [
        attempt for attempt in login_attempts[email]
        if attempt > cutoff
    ]


def is_account_locked(email: str) -> Tuple[bool, int]:
    """
    Check if account is locked due to too many failed attempts
    
    Args:
        email: Email address to check
        
    Returns:
        Tuple of (is_locked: bool, remaining_lockout_minutes: int)
    """
    if email not in login_attempts:
        return False, 0
    
    # Clean old attempts
    cutoff = datetime.utcnow() - timedelta(minutes=LOCKOUT_MINUTES)
    recent_attempts = [
        attempt for attempt in login_attempts[email]
        if attempt > cutoff
    ]
    
    # Update the list
    login_attempts[email] = recent_attempts
    
    # Check if locked
    if len(recent_attempts) >= MAX_ATTEMPTS:
        oldest_attempt = min(recent_attempts)
        unlock_time = oldest_attempt + timedelta(minutes=LOCKOUT_MINUTES)
        remaining_minutes = max(0, int((unlock_time - datetime.utcnow()).total_seconds() / 60))
        return True, remaining_minutes
    
    return False, 0


def clear_login_attempts(email: str) -> None:
    """
    Clear login attempts after successful login
    
    Args:
        email: Email address to clear attempts for
    """
    if email in login_attempts:
        del login_attempts[email]


def get_attempt_count(email: str) -> int:
    """
    Get current number of failed attempts for an email
    
    Args:
        email: Email address to check
        
    Returns:
        Number of recent failed attempts
    """
    if email not in login_attempts:
        return 0
    
    cutoff = datetime.utcnow() - timedelta(minutes=LOCKOUT_MINUTES)
    recent_attempts = [
        attempt for attempt in login_attempts[email]
        if attempt > cutoff
    ]
    
    return len(recent_attempts)
