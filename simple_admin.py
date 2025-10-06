"""
Simple Admin Authentication Module
Simplified version without complex database operations
"""

import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import session, request, jsonify

logger = logging.getLogger(__name__)

def _hash_password(password: str) -> str:
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

# Simple in-memory admin storage
ADMIN_CREDENTIALS = {
    "nitesh.badgayan@gmail.com": {
        "password_hash": _hash_password("Ganapati@123"),
        "is_active": True,
        "role": "admin"
    }
}

# In-memory session storage
ACTIVE_SESSIONS = {}

def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify password"""
    return _hash_password(password) == stored_hash

def login_admin(email: str, password: str) -> dict:
    """Simple admin login"""
    try:
        if email not in ADMIN_CREDENTIALS:
            return {
                "success": False,
                "message": "Invalid credentials"
            }
        
        admin = ADMIN_CREDENTIALS[email]
        
        if not admin["is_active"]:
            return {
                "success": False,
                "message": "Account deactivated"
            }
        
        # Simple password check for now
        if password != "Ganapati@123":
            return {
                "success": False,
                "message": "Invalid credentials"
            }
        
        # Create session
        session_token = secrets.token_urlsafe(32)
        ACTIVE_SESSIONS[session_token] = {
            "admin_email": email,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=24)
        }
        
        logger.info(f"Admin login successful: {email}")
        
        return {
            "success": True,
            "message": "Login successful",
            "session_token": session_token,
            "admin_email": email
        }
        
    except Exception as e:
        logger.error(f"Error during admin login: {e}")
        return {
            "success": False,
            "message": "Login failed due to server error"
        }

def verify_admin_session(session_token: str) -> dict:
    """Verify admin session"""
    try:
        if session_token not in ACTIVE_SESSIONS:
            return {
                "success": False,
                "message": "Invalid session"
            }
        
        session_data = ACTIVE_SESSIONS[session_token]
        
        if datetime.utcnow() > session_data["expires_at"]:
            # Session expired
            del ACTIVE_SESSIONS[session_token]
            return {
                "success": False,
                "message": "Session expired"
            }
        
        return {
            "success": True,
            "admin_email": session_data["admin_email"]
        }
        
    except Exception as e:
        logger.error(f"Error verifying session: {e}")
        return {
            "success": False,
            "message": "Session verification failed"
        }

def logout_admin(session_token: str) -> dict:
    """Logout admin"""
    try:
        if session_token in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[session_token]
        
        logger.info("Admin logout successful")
        
        return {
            "success": True,
            "message": "Logout successful"
        }
        
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        return {
            "success": False,
            "message": "Logout failed"
        }

def require_admin(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for session token in Flask session first
        session_token = session.get('admin_token')
        logger.info(f"Session token from Flask session: {session_token}")
        logger.info(f"Active sessions: {list(ACTIVE_SESSIONS.keys())}")
        
        if not session_token:
            logger.warning("No session token found in Flask session")
            return jsonify({
                "success": False,
                "message": "Admin authentication required"
            }), 401
        
        # Verify session
        verification = verify_admin_session(session_token)
        if not verification["success"]:
            return jsonify({
                "success": False,
                "message": verification["message"]
            }), 401
        
        # Add admin info to request context
        request.admin_email = verification["admin_email"]
        
        return f(*args, **kwargs)
    
    return decorated_function