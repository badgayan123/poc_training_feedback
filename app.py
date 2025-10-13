from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
from db import insert_feedback, get_feedback, get_feedback_stats, get_feedback_by_query, insert_user, get_users, get_user_by_credentials, update_user, delete_user
from config import Config
# Removed feedback_form import - using inline validation
from openai_analysis import analyze_text_feedback, analyze_comprehensive_training_feedback
from simple_admin import login_admin, verify_admin_session, logout_admin, require_admin
import logging
import json
import os
import requests
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False
)

# Enable CORS for all routes (allow credentials for session cookies)
CORS(app, supports_credentials=True)

# -----------------------------
# Active users tracking (IP + time + geo)
# -----------------------------
ACTIVE_USERS = {}
GEO_CACHE = {}
ACTIVE_WINDOW_MINUTES = 15

def _get_client_ip(req: "request") -> str:
    """Get client IP considering common proxy headers."""
    # X-Forwarded-For may contain multiple IPs, take the first
    xff = req.headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[0].strip()
    real_ip = req.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    return req.remote_addr or '0.0.0.0'

def _geo_lookup(ip: str) -> dict:
    """Lookup geolocation using a free API (no key) with basic caching."""
    if not ip or ip == '127.0.0.1' or ip.startswith('192.168.') or ip.startswith('10.'):
        return {"city": "Local", "region": "", "country": "", "latitude": None, "longitude": None}
    cached = GEO_CACHE.get(ip)
    if cached and (datetime.utcnow() - cached.get('cached_at', datetime.utcnow())) < timedelta(days=1):
        return cached['data']
    try:
        # ipapi.co is free and does not require a key
        resp = requests.get(f"https://ipapi.co/{ip}/json/", timeout=5)
        data = resp.json() if resp.ok else {}
        geo = {
            "city": data.get("city"),
            "region": data.get("region"),
            "country": data.get("country_name") or data.get("country"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
        }
        GEO_CACHE[ip] = {"data": geo, "cached_at": datetime.utcnow()}
        return geo
    except Exception:
        return {"city": None, "region": None, "country": None, "latitude": None, "longitude": None}

@app.before_request
def track_active_user():
    """Track active users by IP and last seen time; enrich with geo data lazily."""
    try:
        # Track all routes, including admin, so admin visits count too
        path = request.path or ''
        ip = _get_client_ip(request)
        now = datetime.utcnow()
        info = ACTIVE_USERS.get(ip, {})
        if not info.get('geo'):
            info['geo'] = _geo_lookup(ip)
        info['last_seen'] = now.isoformat()
        info['ip'] = ip
        ACTIVE_USERS[ip] = info
        # Clean up stale entries
        cutoff = now - timedelta(minutes=ACTIVE_WINDOW_MINUTES)
        stale = [k for k, v in ACTIVE_USERS.items() if datetime.fromisoformat(v['last_seen']) < cutoff]
        for k in stale:
            del ACTIVE_USERS[k]
    except Exception:
        # Never block requests due to tracking errors
        pass

@app.route('/heartbeat', methods=['GET'])
def heartbeat():
    """Lightweight endpoint to register activity and return ok."""
    try:
        # The before_request will already register the IP/geo
        return jsonify({"success": True, "ts": datetime.utcnow().isoformat()}), 200
    except Exception:
        return jsonify({"success": False}), 200

def validate_feedback_data(data):
    """Simple validation for feedback data"""
    errors = []
    warnings = []
    
    # Check required fields
    if not data.get('training_id'):
        errors.append('training_id is required')
    
    if not data.get('student_name'):
        warnings.append('student_name is recommended')
    else:
        try:
            name_raw = (data.get('student_name') or '').strip()
            name_upper = name_raw.upper()
            # Allow A-Z, spaces and common punctuation in names
            import re
            if not name_upper or not re.fullmatch(r"[A-Z .'-]+", name_upper):
                errors.append('student_name must be CAPITAL letters only (A-Z, spaces, . \"- )')
            else:
                # Normalize to uppercase for downstream logic
                data['student_name'] = name_upper
        except Exception:
            errors.append('invalid student_name')
    
    # Subject name is required
    if not data.get('subject_name') or not isinstance(data.get('subject_name'), str) or not data.get('subject_name').strip():
        errors.append('subject_name is required')

    # Check quantitative data
    quantitative = data.get('quantitative', {})
    if not quantitative:
        errors.append('quantitative data is required')
    else:
        # Check if we have at least some ratings
        rating_count = sum(1 for v in quantitative.values() if isinstance(v, (int, float)) and 1 <= v <= 5)
        if rating_count == 0:
            errors.append('At least one valid rating (1-5) is required in quantitative data')
    
    # Check qualitative data (optional but recommended)
    qualitative = data.get('qualitative', {})
    if not qualitative:
        warnings.append('qualitative feedback is recommended')
    
    # Log the data for debugging
    logger.info(f"Validating feedback data: {data}")
    logger.info(f"Errors: {errors}, Warnings: {warnings}")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings
    }

@app.route('/', methods=['GET'])
def serve_index():
    """Serve the main HTML page"""
    try:
        return send_file('index.html')
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error serving HTML: {str(e)}'
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'message': 'Feedback Analysis API is running',
        'version': '1.0.0'
    })

# Admin Authentication Endpoints
@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Admin login endpoint"""
    try:
        data = request.get_json()
        
        if not data or 'email' not in data or 'password' not in data:
            return jsonify({
                'success': False,
                'message': 'Email and password are required'
            }), 400
        
        email = data['email']
        password = data['password']
        
        # Authenticate admin
        result = login_admin(email, password)
        
        if result['success']:
            # Store session token in Flask session
            session['admin_token'] = result['session_token']
            session['admin_email'] = result['admin_email']
            
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'admin_email': result['admin_email']
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': result['message']
            }), 401
            
    except Exception as e:
        logger.error(f"Error in admin login: {e}")
        return jsonify({
            'success': False,
            'message': 'Login failed due to server error'
        }), 500

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    """Admin logout endpoint"""
    try:
        session_token = session.get('admin_token')
        
        if session_token:
            logout_admin(session_token)
        
        # Clear Flask session
        session.clear()
        
        return jsonify({
            'success': True,
            'message': 'Logout successful'
        }), 200
        
    except Exception as e:
        logger.error(f"Error in admin logout: {e}")
        return jsonify({
            'success': False,
            'message': 'Logout failed'
        }), 500

@app.route('/admin/status', methods=['GET'])
def admin_status():
    """Simple admin status endpoint for frontend."""
    try:
        session_token = session.get('admin_token')
        if not session_token:
            return jsonify({"success": False}), 200
        verification = verify_admin_session(session_token)
        if verification.get('success'):
            return jsonify({"success": True, "admin_email": verification.get('admin_email')}), 200
        return jsonify({"success": False}), 200
    except Exception:
        return jsonify({"success": False}), 200

@app.route('/admin/active_users', methods=['GET'])
@require_admin
def get_active_users():
    """Return currently active users (seen within ACTIVE_WINDOW_MINUTES)."""
    try:
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=ACTIVE_WINDOW_MINUTES)
        users = []
        for ip, info in ACTIVE_USERS.items():
            try:
                last_seen_dt = datetime.fromisoformat(info.get('last_seen'))
            except Exception:
                continue
            if last_seen_dt >= cutoff:
                geo = info.get('geo', {}) or {}
                users.append({
                    'ip': ip,
                    'last_seen': info.get('last_seen'),
                    'city': geo.get('city'),
                    'region': geo.get('region'),
                    'country': geo.get('country'),
                    'latitude': geo.get('latitude'),
                    'longitude': geo.get('longitude')
                })
        # Sort by last_seen desc
        users.sort(key=lambda u: u.get('last_seen') or '', reverse=True)
        return jsonify({
            'success': True,
            'active_window_minutes': ACTIVE_WINDOW_MINUTES,
            'count': len(users),
            'data': users
        }), 200
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to get active users'
        }), 500

@app.route('/admin/verify', methods=['GET'])
def admin_verify():
    """Verify admin session endpoint"""
    try:
        session_token = session.get('admin_token')
        
        if not session_token:
            return jsonify({
                'success': False,
                'message': 'No active session'
            }), 401
        
        verification = verify_admin_session(session_token)
        
        if verification['success']:
            return jsonify({
                'success': True,
                'admin_email': verification['admin_email']
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': verification['message']
            }), 401
            
    except Exception as e:
        logger.error(f"Error verifying admin session: {e}")
        return jsonify({
            'success': False,
            'message': 'Session verification failed'
        }), 500

@app.route('/admin/test', methods=['GET'])
def admin_test():
    """Test admin system endpoint"""
    try:
        return jsonify({
            'success': True,
            'message': 'Admin system is working',
            'admin_available': True
        }), 200
    except Exception as e:
        logger.error(f"Error in admin test: {e}")
        return jsonify({
            'success': False,
            'message': f'Admin test failed: {str(e)}'
        }), 500

# User Authentication Endpoints
@app.route('/user/login', methods=['POST'])
def user_login():
    """User login endpoint"""
    try:
        data = request.get_json()
        
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({
                'success': False,
                'message': 'Username and password are required'
            }), 400
        
        username = data['username']
        password = data['password']
        
        # Authenticate user
        result = get_user_by_credentials(username, password)
        
        if result['success']:
            # Store user info in Flask session
            session['user_id'] = result['data']['_id']
            session['username'] = result['data']['username']
            session['university_name'] = result['data']['university_name']
            session['training_id'] = result['data']['training_id']
            
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'user_data': {
                    'username': result['data']['username'],
                    'university_name': result['data']['university_name'],
                    'training_id': result['data']['training_id']
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': result['message']
            }), 401
            
    except Exception as e:
        logger.error(f"Error in user login: {e}")
        return jsonify({
            'success': False,
            'message': 'Login failed due to server error'
        }), 500

@app.route('/user/logout', methods=['POST'])
def user_logout():
    """User logout endpoint"""
    try:
        # Clear Flask session
        session.pop('user_id', None)
        session.pop('username', None)
        session.pop('university_name', None)
        session.pop('training_id', None)
        
        return jsonify({
            'success': True,
            'message': 'Logout successful'
        }), 200
        
    except Exception as e:
        logger.error(f"Error in user logout: {e}")
        return jsonify({
            'success': False,
            'message': 'Logout failed'
        }), 500

@app.route('/user/status', methods=['GET'])
def user_status():
    """Check user login status"""
    try:
        if 'user_id' in session:
            return jsonify({
                'success': True,
                'user_data': {
                    'username': session.get('username'),
                    'university_name': session.get('university_name'),
                    'training_id': session.get('training_id')
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Not logged in'
            }), 401
    except Exception as e:
        logger.error(f"Error checking user status: {e}")
        return jsonify({
            'success': False,
            'message': 'Status check failed'
        }), 500

# User Management Endpoints (Admin only)
@app.route('/admin/users', methods=['GET'])
@require_admin
def admin_get_users():
    """Get all users (admin only)"""
    try:
        result = get_users()
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to get users: {str(e)}'
        }), 500

@app.route('/admin/users', methods=['POST'])
@require_admin
def admin_add_user():
    """Add new user (admin only)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        # Validate required fields
        required_fields = ['username', 'password', 'university_name', 'training_id']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'message': f'{field} is required'
                }), 400
        
        # Add user
        result = insert_user(data)
        
        if result['success']:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error adding user: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to add user: {str(e)}'
        }), 500

@app.route('/admin/users/<user_id>', methods=['PUT'])
@require_admin
def admin_update_user(user_id):
    """Update user (admin only)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        # Update user
        result = update_user(user_id, data)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to update user: {str(e)}'
        }), 500

@app.route('/admin/users/<user_id>', methods=['DELETE'])
@require_admin
def admin_delete_user(user_id):
    """Delete user (admin only)"""
    try:
        result = delete_user(user_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to delete user: {str(e)}'
        }), 500

@app.route('/admin/users/export', methods=['GET'])
@require_admin
def admin_export_users():
    """Export users as CSV (admin only)"""
    try:
        result = get_users()
        
        if not result['success']:
            return jsonify(result), 500
        
        users = result['data']
        
        # Group users by university
        grouped_users = {}
        for user in users:
            university = user.get('university_name', 'Unknown')
            if university not in grouped_users:
                grouped_users[university] = []
            grouped_users[university].append(user)
        
        # Create CSV content
        csv_content = "University,Username,Password,Training ID,Created At\n"
        for university, user_list in grouped_users.items():
            for user in user_list:
                csv_content += f"{university},{user.get('username', '')},{user.get('password', '')},{user.get('training_id', '')},{user.get('created_at', '')}\n"
        
        return jsonify({
            'success': True,
            'message': 'Users exported successfully',
            'csv_content': csv_content,
            'grouped_users': grouped_users
        }), 200
        
    except Exception as e:
        logger.error(f"Error exporting users: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to export users: {str(e)}'
        }), 500

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    """
    Submit comprehensive feedback data
    
    Expected JSON format:
    {
        "training_id": "required_training_id",
        "student_name": "optional_student_name",
        "quantitative": {
            "content_quality": 4,
            "trainer_effectiveness": 5,
            "clarity_of_explanation": 4,
            "engagement_interaction": 3,
            "practical_relevance": 5
        },
        "qualitative": {
            "general_feedback": "Overall feedback text...",
            "suggestions_improvement": "Improvement suggestions...",
            "favorite_highlights": "Favorite parts...",
            "challenges_faced": "Challenges encountered...",
            "trainer_feedback": "Trainer-specific feedback...",
            "learning_outcomes": "What was learned...",
            "practical_application": "How to apply learning...",
            "additional_resources": "Additional resources needed...",
            "session_pace_timing": "Pace and timing feedback...",
            "open_ended_feedback": "Any additional comments..."
        }
    }
    """
    try:
        # Get JSON data from request
        feedback_data = request.get_json()
        
        if not feedback_data:
            return jsonify({
                'success': False,
                'message': 'No JSON data provided'
            }), 400
        
        # Validate feedback data
        validation_result = validate_feedback_data(feedback_data)
        
        if not validation_result['valid']:
            logger.error(f"Validation failed: {validation_result['errors']}")
            return jsonify({
                'success': False,
                'message': 'Validation failed',
                'errors': validation_result['errors'],
                'warnings': validation_result['warnings']
            }), 400
        
        # Normalize student name to uppercase defensively
        if feedback_data.get('student_name'):
            feedback_data['student_name'] = (feedback_data['student_name'] or '').strip().upper()

        # Normalize training_id to uppercase defensively
        if feedback_data.get('training_id'):
            feedback_data['training_id'] = (feedback_data['training_id'] or '').strip().upper()

        # Add timestamp if not present
        if 'date' not in feedback_data:
            from datetime import datetime
            feedback_data['date'] = datetime.utcnow().isoformat()
        
        # Insert feedback into database
        result = insert_feedback(feedback_data)
        
        if result['success']:
            response = result.copy()
            if validation_result['warnings']:
                response['warnings'] = validation_result['warnings']
            return jsonify(response), 201
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error in submit_feedback: {e}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/get_feedback', methods=['GET'])
def retrieve_feedback():
    """
    Retrieve feedback data
    
    Query parameters:
    - training_id (optional): Filter by specific training ID
    """
    try:
        # Get query parameters
        training_id = request.args.get('training_id')
        
        # Retrieve feedback from database
        result = get_feedback(training_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error in get_feedback: {e}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}',
            'data': []
        }), 500

@app.route('/admin/get_feedback', methods=['GET'])
def admin_get_feedback():
    """
    Admin-protected endpoint to retrieve feedback data
    
    Query parameters:
    - training_id (optional): Filter by specific training ID
    """
    try:
        # Get query parameters
        training_id = request.args.get('training_id')
        
        # Retrieve feedback from database
        result = get_feedback(training_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error in admin get_feedback: {e}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}',
            'data': []
        }), 500

@app.route('/admin/database_dashboard', methods=['GET'])
@require_admin
def get_database_dashboard_data():
    """
    Admin-protected endpoint to retrieve database dashboard data
    Returns training ID, trainer name, subject name, student name, and submission date
    """
    try:
        # Get all feedback data
        result = get_feedback()
        
        if result['success']:
            # Extract only the fields needed for database dashboard
            dashboard_data = []
            for feedback in result['data']:
                dashboard_entry = {
                    'training_id': feedback.get('training_id', 'N/A'),
                    'trainer_name': feedback.get('trainer_name', 'N/A'),
                    'subject_name': feedback.get('subject_name', 'N/A'),
                    'student_name': feedback.get('student_name', 'Anonymous'),
                    'submission_date': feedback.get('date', 'N/A'),
                    'timestamp': feedback.get('timestamp', 'N/A')
                }
                dashboard_data.append(dashboard_entry)
            
            return jsonify({
                'success': True,
                'message': f'Retrieved {len(dashboard_data)} database entries',
                'data': dashboard_data,
                'count': len(dashboard_data)
            }), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error in database dashboard: {e}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}',
            'data': []
        }), 500

@app.route('/analyze_feedback', methods=['POST'])
def analyze_feedback():
    """
    Analyze feedback text using OpenAI GPT-4
    
    Expected JSON format:
    {
        "text": "feedback text to analyze"
    }
    """
    try:
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No JSON data provided'
            }), 400
        
        if 'text' not in data:
            return jsonify({
                'success': False,
                'message': 'text field is required'
            }), 400
        
        feedback_text = data['text']
        
        # Validate text input
        if not isinstance(feedback_text, str) or len(feedback_text.strip()) < 10:
            return jsonify({
                'success': False,
                'message': 'Text must be a string with at least 10 characters'
            }), 400
        
        # Analyze using OpenAI
        analysis_result = analyze_text_feedback(feedback_text)
        
        logger.info(f"Successfully analyzed feedback text (length: {len(feedback_text)} chars)")
        
        return jsonify({
            'success': True,
            'message': 'Feedback analysis completed successfully',
            'data': {
                'original_text': feedback_text,
                'analysis': analysis_result
            }
        }), 200
        
    except ValueError as e:
        logger.warning(f"Validation error in analyze_feedback: {e}")
        return jsonify({
            'success': False,
            'message': f'Invalid input: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"Error in analyze_feedback: {e}")
        return jsonify({
            'success': False,
            'message': f'Analysis failed: {str(e)}'
        }), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get feedback statistics"""
    try:
        result = get_feedback_stats()
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error in get_stats: {e}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/feedback_form', methods=['GET'])
def get_feedback_form():
    """Get the feedback form structure for frontend rendering"""
    try:
        form_structure = FeedbackForm.get_form_structure()
        return jsonify({
            'success': True,
            'message': 'Feedback form structure retrieved successfully',
            'data': form_structure
        }), 200
    except Exception as e:
        logger.error(f"Error in get_feedback_form: {e}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/feedback_template', methods=['GET'])
def get_feedback_template():
    """Get a feedback template for a specific training"""
    try:
        training_id = request.args.get('training_id')
        student_name = request.args.get('student_name')
        
        if not training_id:
            return jsonify({
                'success': False,
                'message': 'training_id parameter is required'
            }), 400
        
        template = FeedbackForm.create_feedback_template(training_id, student_name)
        
        return jsonify({
            'success': True,
            'message': 'Feedback template created successfully',
            'data': template
        }), 200
    except Exception as e:
        logger.error(f"Error in get_feedback_template: {e}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/example_feedback', methods=['GET'])
def get_example_feedback():
    """Get example feedback data for reference"""
    try:
        example = FeedbackForm.get_example_feedback()
        return jsonify({
            'success': True,
            'message': 'Example feedback retrieved successfully',
            'data': example
        }), 200
    except Exception as e:
        logger.error(f"Error in get_example_feedback: {e}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/validate_feedback', methods=['POST'])
def validate_feedback():
    """Validate feedback data without saving it"""
    try:
        feedback_data = request.get_json()
        
        if not feedback_data:
            return jsonify({
                'success': False,
                'message': 'No JSON data provided'
            }), 400
        
        validation_result = validate_feedback_data(feedback_data)
        
        return jsonify({
            'success': True,
            'message': 'Validation completed',
            'data': validation_result
        }), 200
    except Exception as e:
        logger.error(f"Error in validate_feedback: {e}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/analyze_trainer_performance', methods=['POST'])
def analyze_trainer_performance():
    """
    Analyze trainer performance across all sessions with optional date filtering
    
    Expected JSON format:
    {
        "trainer_name": "Amit Choudhary",
        "date_from": "2024-01-01",  # Optional
        "date_to": "2024-03-31"     # Optional
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'trainer_name' not in data:
            return jsonify({
                'success': False,
                'message': 'Trainer name is required'
            }), 400
        
        trainer_name = data['trainer_name']
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        # Build query for trainer
        query = {'trainer_name': trainer_name}
        
        # Add date filtering if provided
        if date_from or date_to:
            date_filter = {}
            if date_from:
                date_filter['$gte'] = date_from
            if date_to:
                date_filter['$lte'] = date_to
            query['training_date_from'] = date_filter
        
        # Get all feedback for this trainer
        feedback_result = get_feedback_by_query(query)
        
        if not feedback_result['success']:
            return jsonify({
                'success': False,
                'message': f'Failed to retrieve feedback: {feedback_result["message"]}'
            }), 500
        
        feedbacks = feedback_result['data']
        
        if not feedbacks:
            return jsonify({
                'success': False,
                'message': f'No feedback found for trainer: {trainer_name}'
            }), 404
        
        # Analyze trainer performance
        analysis = analyze_trainer_performance_data(trainer_name, feedbacks, date_from, date_to)
        
        return jsonify({
            'success': True,
            'analysis': analysis
        }), 200
        
    except Exception as e:
        logger.error(f"Error in trainer performance analysis: {e}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/get_trainers', methods=['GET'])
def get_trainers():
    """Get list of all trainers with their session counts"""
    try:
        # Get all unique trainers
        pipeline = [
            {"$group": {
                "_id": "$trainer_name",
                "session_count": {"$sum": 1},
                "total_participants": {"$sum": 1},
                "latest_session": {"$max": "$training_date_from"},
                "earliest_session": {"$min": "$training_date_from"}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        result = db_manager.collection.aggregate(pipeline)
        trainers = []
        
        for doc in result:
            trainers.append({
                'name': doc['_id'],
                'session_count': doc['session_count'],
                'total_participants': doc['total_participants'],
                'latest_session': doc['latest_session'],
                'earliest_session': doc['earliest_session']
            })
        
        return jsonify({
            'success': True,
            'trainers': trainers
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting trainers: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to get trainers: {str(e)}'
        }), 500

@app.route('/analyze_training_feedback', methods=['POST'])
def analyze_training_feedback():
    """
    Analyze all feedback for a specific training ID using comprehensive AI analysis

    Expected JSON format:
    {
        "training_id": "TRAINING_001"
    }
    """
    try:
        data = request.get_json()

        if not data or 'training_id' not in data:
            return jsonify({
                'success': False,
                'message': 'training_id is required'
            }), 400

        training_id = data['training_id']

        # Get all feedback for this training ID
        feedback_result = get_feedback(training_id)
        
        if not feedback_result['success']:
            return jsonify({
                'success': False,
                'message': f'Error retrieving feedback: {feedback_result["message"]}'
            }), 500
            
        feedbacks = feedback_result['data']

        if not feedbacks:
            return jsonify({
                'success': False,
                'message': f'No feedback found for training ID: {training_id}'
            }), 404

        # Use the new comprehensive analysis function
        comprehensive_analysis = analyze_comprehensive_training_feedback(training_id, feedbacks)

        logger.info(f"Successfully analyzed training feedback for: {training_id} ({len(feedbacks)} records)")

        return jsonify({
            'success': True,
            'message': f'Comprehensive training feedback analysis completed for {training_id}',
            'data': comprehensive_analysis
        }), 200

    except Exception as e:
        logger.error(f"Error in analyze_training_feedback: {e}")
        return jsonify({
            'success': False,
            'message': f'Analysis failed: {str(e)}'
        }), 500

@app.route('/analyze_comprehensive_feedback', methods=['POST'])
def analyze_comprehensive_feedback():
    """
    Analyze comprehensive feedback data using OpenAI
    
    Expected JSON format:
    {
        "training_id": "TRAINING_001",
        "quantitative": {...},
        "qualitative": {...}
    }
    """
    try:
        feedback_data = request.get_json()
        
        if not feedback_data:
            return jsonify({
                'success': False,
                'message': 'No JSON data provided'
            }), 400
        
        # Validate feedback data first
        validation_result = validate_feedback_data(feedback_data)
        if not validation_result['valid']:
            return jsonify({
                'success': False,
                'message': 'Invalid feedback data',
                'errors': validation_result['errors']
            }), 400
        
        # Extract qualitative feedback for analysis
        qualitative = feedback_data.get('qualitative', {})
        
        # Combine all qualitative responses into a single text
        combined_text = ""
        for key, value in qualitative.items():
            if value and isinstance(value, str) and value.strip():
                combined_text += f"{key.replace('_', ' ').title()}: {value.strip()}\n\n"
        
        if not combined_text.strip():
            return jsonify({
                'success': False,
                'message': 'No qualitative feedback text found for analysis'
            }), 400
        
        # Analyze the combined qualitative feedback
        analysis_result = analyze_text_feedback(combined_text)
        
        # Add quantitative summary
        quantitative = feedback_data.get('quantitative', {})
        avg_rating = sum(quantitative.values()) / len(quantitative) if quantitative else 0
        
        analysis_result['quantitative_summary'] = {
            'average_rating': round(avg_rating, 2),
            'ratings': quantitative,
            'rating_scale': '1-5 (1=Poor, 5=Excellent)'
        }
        
        logger.info(f"Successfully analyzed comprehensive feedback for training: {feedback_data.get('training_id', 'Unknown')}")
        
        return jsonify({
            'success': True,
            'message': 'Comprehensive feedback analysis completed successfully',
            'data': {
                'training_id': feedback_data.get('training_id'),
                'analysis': analysis_result,
                'original_feedback': {
                    'quantitative': quantitative,
                    'qualitative': qualitative
                }
            }
        }), 200
        
    except ValueError as e:
        logger.warning(f"Validation error in analyze_comprehensive_feedback: {e}")
        return jsonify({
            'success': False,
            'message': f'Invalid input: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"Error in analyze_comprehensive_feedback: {e}")
        return jsonify({
            'success': False,
            'message': f'Analysis failed: {str(e)}'
        }), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'success': False,
        'message': 'Endpoint not found'
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    return jsonify({
        'success': False,
        'message': 'Method not allowed'
    }), 405

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({
        'success': False,
        'message': 'Internal server error'
    }), 500

def analyze_trainer_performance_data(trainer_name, feedbacks, date_from=None, date_to=None):
    """
    Analyze trainer performance data and generate comprehensive insights
    """
    try:
        # Calculate basic metrics
        total_sessions = len(set(f['training_id'] for f in feedbacks))
        total_participants = len(feedbacks)
        
        # Calculate average ratings across all sessions
        all_ratings = {}
        for feedback in feedbacks:
            if 'quantitative' in feedback:
                for metric, rating in feedback['quantitative'].items():
                    if metric not in all_ratings:
                        all_ratings[metric] = []
                    all_ratings[metric].append(rating)
        
        # Calculate averages
        avg_ratings = {}
        for metric, ratings in all_ratings.items():
            avg_ratings[metric] = sum(ratings) / len(ratings) if ratings else 0
        
        # Overall average
        overall_avg = sum(avg_ratings.values()) / len(avg_ratings) if avg_ratings else 0
        
        # Collect qualitative feedback
        qualitative_feedback = []
        for feedback in feedbacks:
            if 'qualitative' in feedback:
                for question, answer in feedback['qualitative'].items():
                    if answer and answer.strip():
                        qualitative_feedback.append(answer.strip())
        
        # Combine all qualitative feedback
        combined_qualitative = "\n\n".join(qualitative_feedback)
        
        # Simple qualitative summary without AI
        qualitative_analysis = {
            "summary": f"Analysis of {len(qualitative_feedback)} qualitative feedback responses for trainer {trainer_name}",
            "total_responses": len(qualitative_feedback),
            "response_length_avg": sum(len(f) for f in qualitative_feedback) / len(qualitative_feedback) if qualitative_feedback else 0
        }
        
        # Calculate KPIs
        kpis = calculate_kpis(feedbacks, avg_ratings, overall_avg)
        
        # Calculate session trends
        session_trends = calculate_session_trends(feedbacks)
        
        # Generate comprehensive analysis
        analysis = {
            "trainer_name": trainer_name,
            "date_range": {
                "from": date_from,
                "to": date_to
            },
            "summary": {
                "total_sessions": total_sessions,
                "total_participants": total_participants,
                "overall_average_rating": round(overall_avg, 2),
                "date_range_applied": bool(date_from or date_to)
            },
            "quantitative_analysis": {
                "average_ratings": {k: round(v, 2) for k, v in avg_ratings.items()},
                "best_performing_metric": max(avg_ratings.items(), key=lambda x: x[1])[0] if avg_ratings else None,
                "needs_improvement_metric": min(avg_ratings.items(), key=lambda x: x[1])[0] if avg_ratings else None
            },
            "qualitative_analysis": qualitative_analysis,
            "kpis": kpis,
            "session_trends": session_trends,
            "recommendations": [
                f"Focus on improving {min(avg_ratings.items(), key=lambda x: x[1])[0]}" if avg_ratings else "Continue current approach",
                f"Maintain excellence in {max(avg_ratings.items(), key=lambda x: x[1])[0]}" if avg_ratings else "Focus on all areas",
                "Review qualitative feedback for specific improvement areas"
            ],
            "performance_trends": {
                "consistency": "High" if all_ratings and max(avg_ratings.values()) - min(avg_ratings.values()) < 1.0 else "Medium",
                "overall_satisfaction": "Excellent" if overall_avg >= 4.5 else "Good" if overall_avg >= 3.5 else "Needs Improvement"
            }
        }
        
        return analysis
        
    except Exception as e:
        logger.error(f"Error analyzing trainer performance: {e}")
        return {
            "trainer_name": trainer_name,
            "error": f"Analysis failed: {str(e)}",
            "summary": {
                "total_sessions": 0,
                "total_participants": 0,
                "overall_average_rating": 0
            }
        }

def calculate_kpis(feedbacks, avg_ratings, overall_avg):
    """Calculate Key Performance Indicators for trainer"""
    try:
        # Group feedback by training_id to get session-level data
        sessions = {}
        for feedback in feedbacks:
            session_id = feedback.get('training_id', 'unknown')
            if session_id not in sessions:
                sessions[session_id] = []
            sessions[session_id].append(feedback)
        
        # Calculate average rating for each session
        session_ratings = []
        for session_id, session_feedbacks in sessions.items():
            session_avg = 0
            count = 0
            for feedback in session_feedbacks:
                if 'quantitative' in feedback:
                    session_avg += sum(feedback['quantitative'].values())
                    count += len(feedback['quantitative'])
            if count > 0:
                session_ratings.append({
                    'session_id': session_id,
                    'average_rating': session_avg / count
                })
        
        # Sort by session_id to get chronological order
        session_ratings.sort(key=lambda x: x['session_id'])
        
        # KPI 1: Average rating of last 3 sessions (target: >= 4.0)
        last_3_sessions = session_ratings[-3:] if len(session_ratings) >= 3 else session_ratings
        avg_last_3 = sum(s['average_rating'] for s in last_3_sessions) / len(last_3_sessions) if last_3_sessions else 0
        
        # KPI 2: Consistency score (inverse of variance)
        if len(session_ratings) > 1:
            ratings = [s['average_rating'] for s in session_ratings]
            variance = sum((r - overall_avg) ** 2 for r in ratings) / len(ratings)
            consistency_score = max(0, 100 - (variance * 20))  # Convert to percentage
        else:
            consistency_score = 100
        
        # KPI 3: Improvement trend (last 5 sessions)
        if len(session_ratings) >= 5:
            recent_5 = session_ratings[-5:]
            first_half = sum(s['average_rating'] for s in recent_5[:2]) / 2
            second_half = sum(s['average_rating'] for s in recent_5[-2:]) / 2
            improvement = second_half - first_half
            if improvement > 0.2:
                trend = "↗️ Improving"
            elif improvement < -0.2:
                trend = "↘️ Declining"
            else:
                trend = "➡️ Stable"
        else:
            trend = "📊 Insufficient Data"
        
        # KPI 4: Satisfaction rate (percentage of 4+ ratings)
        all_ratings = []
        for feedback in feedbacks:
            if 'quantitative' in feedback:
                all_ratings.extend(feedback['quantitative'].values())
        
        satisfaction_count = sum(1 for r in all_ratings if r >= 4)
        satisfaction_rate = (satisfaction_count / len(all_ratings) * 100) if all_ratings else 0
        
        # Additional KPIs
        # Overall Average Rating (all time)
        overall_avg_rating = sum(all_ratings) / len(all_ratings) if all_ratings else 0
        
        # Best and Worst Session Ratings
        best_session_rating = max(s['average_rating'] for s in session_ratings) if session_ratings else 0
        worst_session_rating = min(s['average_rating'] for s in session_ratings) if session_ratings else 0
        
        # Excellence Rate (4.5+ ratings)
        excellence_count = sum(1 for r in all_ratings if r >= 4.5)
        excellence_rate = (excellence_count / len(all_ratings) * 100) if all_ratings else 0
        
        # Poor Rating Rate (<3 ratings)
        poor_count = sum(1 for r in all_ratings if r < 3)
        poor_rate = (poor_count / len(all_ratings) * 100) if all_ratings else 0
        
        # Target Achievement Rate (sessions meeting 4+ average)
        target_sessions = sum(1 for s in session_ratings if s['average_rating'] >= 4)
        target_achievement_rate = (target_sessions / len(session_ratings) * 100) if session_ratings else 0
        
        # Rating Improvement Rate (trend over last 5 sessions)
        if len(session_ratings) >= 5:
            recent_5 = session_ratings[-5:]
            first_half_avg = sum(s['average_rating'] for s in recent_5[:2]) / 2
            second_half_avg = sum(s['average_rating'] for s in recent_5[-2:]) / 2
            improvement_rate = ((second_half_avg - first_half_avg) / first_half_avg * 100) if first_half_avg > 0 else 0
        else:
            improvement_rate = 0
        
        # Performance Stability (sessions within 0.5 rating variance)
        if len(session_ratings) > 1:
            ratings = [s['average_rating'] for s in session_ratings]
            mean_rating = sum(ratings) / len(ratings)
            stable_sessions = sum(1 for r in ratings if abs(r - mean_rating) <= 0.5)
            stability_rate = (stable_sessions / len(ratings) * 100)
        else:
            stability_rate = 100
        
        # Average Participants per Session
        avg_participants_per_session = len(feedbacks) / len(session_ratings) if session_ratings else 0
        
        # Monthly Growth Rate (simplified - using session order)
        if len(session_ratings) >= 2:
            first_half = session_ratings[:len(session_ratings)//2]
            second_half = session_ratings[len(session_ratings)//2:]
            first_avg = sum(s['average_rating'] for s in first_half) / len(first_half)
            second_avg = sum(s['average_rating'] for s in second_half) / len(second_half)
            monthly_growth = ((second_avg - first_avg) / first_avg * 100) if first_avg > 0 else 0
        else:
            monthly_growth = 0
        
        return {
            # Core KPIs
            "avg_rating_last_3_sessions": round(avg_last_3, 2),
            "consistency_score": round(consistency_score, 1),
            "improvement_trend": trend,
            "satisfaction_rate": round(satisfaction_rate, 1),
            
            # Performance KPIs
            "overall_avg_rating": round(overall_avg_rating, 2),
            "best_session_rating": round(best_session_rating, 2),
            "worst_session_rating": round(worst_session_rating, 2),
            "rating_improvement_rate": round(improvement_rate, 1),
            
            # Quality KPIs
            "excellence_rate": round(excellence_rate, 1),
            "poor_rating_rate": round(poor_rate, 1),
            "target_achievement_rate": round(target_achievement_rate, 1),
            
            # Growth KPIs
            "monthly_growth_rate": round(monthly_growth, 1),
            "avg_participants_per_session": round(avg_participants_per_session, 1),
            
            # Stability KPIs
            "performance_stability": round(stability_rate, 1)
        }
        
    except Exception as e:
        logger.error(f"Error calculating KPIs: {e}")
        return {
            "avg_rating_last_3_sessions": 0,
            "consistency_score": 0,
            "improvement_trend": "Error",
            "satisfaction_rate": 0
        }

def calculate_session_trends(feedbacks):
    """Calculate session-by-session trends for charting"""
    try:
        # Group feedback by training_id
        sessions = {}
        for feedback in feedbacks:
            session_id = feedback.get('training_id', 'unknown')
            if session_id not in sessions:
                sessions[session_id] = []
            sessions[session_id].append(feedback)
        
        # Calculate average rating for each session
        session_trends = []
        for session_id, session_feedbacks in sessions.items():
            session_avg = 0
            count = 0
            for feedback in session_feedbacks:
                if 'quantitative' in feedback:
                    session_avg += sum(feedback['quantitative'].values())
                    count += len(feedback['quantitative'])
            
            if count > 0:
                session_trends.append({
                    'session_id': session_id,
                    'average_rating': session_avg / count,
                    'participant_count': len(session_feedbacks)
                })
        
        # Sort by session_id for chronological order
        session_trends.sort(key=lambda x: x['session_id'])
        
        return session_trends
        
    except Exception as e:
        logger.error(f"Error calculating session trends: {e}")
        return []

if __name__ == '__main__':
    logger.info("Starting Feedback Analysis API...")
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=app.config['DEBUG']
    )