from pymongo import MongoClient
from bson.objectid import ObjectId
from config import Config
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None
        self.users_collection = None
        self.forms_collection = None
        self.connect()
    
    def connect(self):
        """Establish connection to MongoDB"""
        try:
            self.client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
            self.db = self.client[Config.DATABASE_NAME]
            self.collection = self.db[Config.COLLECTION_NAME]
            # Additional collections
            self.users_collection = self.db.get_collection('users')
            self.forms_collection = self.db.get_collection('feedback_forms')
            # Test the connection
            self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            # Create a mock connection for development
            self.client = None
            self.db = None
            self.collection = None
            self.users_collection = None
            self.forms_collection = None
            logger.warning("Running in offline mode - database operations will be simulated")
    
    def close_connection(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

# Global database manager instance
db_manager = DatabaseManager()

def insert_feedback(feedback_data):
    """
    Insert feedback data into MongoDB
    
    Args:
        feedback_data (dict): Feedback data to insert
        
    Returns:
        dict: Result with success status and inserted_id or error message
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - simulating feedback insertion")
            return {"success": True, "inserted_id": "simulated_id", "message": "Offline mode - data not saved"}
        
        # Normalize key fields
        if feedback_data.get('student_name'):
            feedback_data['student_name'] = (feedback_data['student_name'] or '').strip().upper()

        # Prevent duplicate submissions for same training_id + student_name
        try:
            training_id = feedback_data.get('training_id')
            student_name = feedback_data.get('student_name')
            if training_id and student_name:
                existing = db_manager.collection.find_one({
                    'training_id': training_id,
                    'student_name': student_name
                })
                if existing:
                    return {
                        'success': False,
                        'message': 'Feedback already submitted for this student name in this training.'
                    }
        except Exception as e:
            logger.error(f"Error during duplicate check: {e}")

        # Add timestamp if not present
        if 'timestamp' not in feedback_data:
            feedback_data['timestamp'] = datetime.utcnow()
        
        # Insert the document
        result = db_manager.collection.insert_one(feedback_data)
        
        logger.info(f"Feedback inserted with ID: {result.inserted_id}")
        return {
            'success': True,
            'message': 'Feedback submitted successfully',
            'inserted_id': str(result.inserted_id)
        }
    except Exception as e:
        logger.error(f"Error inserting feedback: {e}")
        return {
            'success': False,
            'message': f'Failed to insert feedback: {str(e)}'
        }

def get_feedback(training_id=None):
    """
    Retrieve feedback from MongoDB
    
    Args:
        training_id (str, optional): Filter feedback by training_id
        
    Returns:
        dict: Result with success status and feedback data or error message
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - returning empty feedback list")
            return {"success": True, "data": [], "message": "Offline mode - no data available"}
        
        # Build query
        query = {}
        if training_id:
            query['training_id'] = training_id
        
        # Execute query
        cursor = db_manager.collection.find(query)
        feedbacks = []
        
        for doc in cursor:
            # Convert ObjectId to string for JSON serialization
            doc['_id'] = str(doc['_id'])
            feedbacks.append(doc)
        
        logger.info(f"Retrieved {len(feedbacks)} feedback records")
        return {
            'success': True,
            'message': f'Retrieved {len(feedbacks)} feedback records',
            'data': feedbacks,
            'count': len(feedbacks)
        }
    except Exception as e:
        logger.error(f"Error retrieving feedback: {e}")
        return {
            'success': False,
            'message': f'Failed to retrieve feedback: {str(e)}',
            'data': []
        }

def get_feedback_stats():
    """
    Get basic statistics about feedback data
    
    Returns:
        dict: Statistics about feedback data
    """
    try:
        total_count = db_manager.collection.count_documents({})
        
        # Get unique training IDs
        training_ids = db_manager.collection.distinct('training_id')
        
        # Get date range
        pipeline = [
            {
                '$group': {
                    '_id': None,
                    'earliest': {'$min': '$timestamp'},
                    'latest': {'$max': '$timestamp'}
                }
            }
        ]
        date_stats = list(db_manager.collection.aggregate(pipeline))
        
        stats = {
            'total_feedbacks': total_count,
            'unique_trainings': len(training_ids),
            'training_ids': training_ids
        }
        
        if date_stats:
            stats['earliest_feedback'] = date_stats[0]['earliest']
            stats['latest_feedback'] = date_stats[0]['latest']
        
        return {
            'success': True,
            'message': 'Statistics retrieved successfully',
            'data': stats
        }
    except Exception as e:
        logger.error(f"Error retrieving feedback statistics: {e}")
        return {
            'success': False,
            'message': f'Failed to retrieve statistics: {str(e)}',
            'data': {}
        }

def get_feedback_by_query(query):
    """
    Retrieve feedback from MongoDB using custom query
    
    Args:
        query (dict): MongoDB query
        
    Returns:
        dict: Result with success status and feedback data or error message
    """
    try:
        # Execute query
        cursor = db_manager.collection.find(query)
        feedbacks = []
        
        for doc in cursor:
            # Convert ObjectId to string for JSON serialization
            doc['_id'] = str(doc['_id'])
            feedbacks.append(doc)
        
        logger.info(f"Retrieved {len(feedbacks)} feedback records with query: {query}")
        return {
            'success': True,
            'data': feedbacks
        }
    except Exception as e:
        logger.error(f"Error retrieving feedback with query: {e}")
        return {
            'success': False,
            'message': f'Failed to retrieve feedback: {str(e)}'
        }

# User Management Functions
def insert_user(user_data):
    """
    Insert user data into MongoDB
    
    Args:
        user_data (dict): User data to insert
        
    Returns:
        dict: Result with success status and inserted_id or error message
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - simulating user insertion")
            return {"success": True, "inserted_id": "simulated_user_id", "message": "Offline mode - user not saved"}
        
        # Check if username already exists
        existing_user = db_manager.users_collection.find_one({'username': user_data['username']}) if db_manager.users_collection else None
        if existing_user:
            return {
                'success': False,
                'message': 'Username already exists'
            }
        
        # Add timestamp
        user_data['created_at'] = datetime.utcnow()
        user_data['is_active'] = True
        
        # Insert the document
        result = db_manager.users_collection.insert_one(user_data) if db_manager.users_collection else type('obj', (object,), {'inserted_id': 'simulated'})()
        
        logger.info(f"User inserted with ID: {result.inserted_id}")
        return {
            'success': True,
            'message': 'User created successfully',
            'inserted_id': str(result.inserted_id)
        }
    except Exception as e:
        logger.error(f"Error inserting user: {e}")
        return {
            'success': False,
            'message': f'Failed to insert user: {str(e)}'
        }

def get_users():
    """
    Retrieve all users from MongoDB
    
    Returns:
        dict: Result with success status and user data or error message
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - returning empty user list")
            return {"success": True, "data": [], "message": "Offline mode - no data available"}
        
        # Execute query
        cursor = db_manager.users_collection.find({'is_active': True}) if db_manager.users_collection else []
        users = []
        
        for doc in cursor:
            # Convert ObjectId to string for JSON serialization
            doc['_id'] = str(doc['_id'])
            users.append(doc)
        
        logger.info(f"Retrieved {len(users)} user records")
        return {
            'success': True,
            'message': f'Retrieved {len(users)} user records',
            'data': users,
            'count': len(users)
        }
    except Exception as e:
        logger.error(f"Error retrieving users: {e}")
        return {
            'success': False,
            'message': f'Failed to retrieve users: {str(e)}',
            'data': []
        }

def get_user_by_credentials(username, password):
    """
    Get user by username and password for authentication
    
    Args:
        username (str): Username
        password (str): Password
        
    Returns:
        dict: Result with success status and user data or error message
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - user authentication failed")
            return {"success": False, "message": "Database offline - authentication unavailable"}
        
        # Find user by username
        user = db_manager.users_collection.find_one({
            'username': username,
            'is_active': True
        }) if db_manager.users_collection else None
        
        if not user:
            return {
                'success': False,
                'message': 'Invalid username or password'
            }
        
        # Check password (simple comparison for now)
        if user.get('password') != password:
            return {
                'success': False,
                'message': 'Invalid username or password'
            }
        
        # Convert ObjectId to string
        user['_id'] = str(user['_id'])
        
        logger.info(f"User authenticated successfully: {username}")
        return {
            'success': True,
            'message': 'Authentication successful',
            'data': user
        }
    except Exception as e:
        logger.error(f"Error authenticating user: {e}")
        return {
            'success': False,
            'message': f'Authentication failed: {str(e)}'
        }

def update_user(user_id, update_data):
    """
    Update user data
    
    Args:
        user_id (str): User ID
        update_data (dict): Data to update
        
    Returns:
        dict: Result with success status
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - user update failed")
            return {"success": False, "message": "Database offline - update unavailable"}
        
        # Update the document
        result = db_manager.users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': update_data}
        ) if db_manager.users_collection else type('obj', (object,), {'modified_count': 1})()
        
        if result.modified_count > 0:
            logger.info(f"User updated successfully: {user_id}")
            return {
                'success': True,
                'message': 'User updated successfully'
            }
        else:
            return {
                'success': False,
                'message': 'User not found or no changes made'
            }
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        return {
            'success': False,
            'message': f'Failed to update user: {str(e)}'
        }

def delete_user(user_id):
    """
    Soft delete user (set is_active to False)
    
    Args:
        user_id (str): User ID
        
    Returns:
        dict: Result with success status
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - user deletion failed")
            return {"success": False, "message": "Database offline - deletion unavailable"}
        
        # Soft delete by setting is_active to False
        result = db_manager.users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'is_active': False}}
        ) if db_manager.users_collection else type('obj', (object,), {'modified_count': 1})()
        
        if result.modified_count > 0:
            logger.info(f"User deleted successfully: {user_id}")
            return {
                'success': True,
                'message': 'User deleted successfully'
            }
        else:
            return {
                'success': False,
                'message': 'User not found'
            }
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        return {
            'success': False,
            'message': f'Failed to delete user: {str(e)}'
        }

# -----------------------------
# Feedback Forms (Admin-generated)
# -----------------------------

def create_feedback_form(form_data: dict) -> dict:
    """
    Create a feedback form definition with metadata and questions.
    Expected keys: university_name, course_name, training_id, questions: [{type: 'choice'|'subjective', text: str}]
    Limits: up to 10 choice, up to 10 subjective, max total 20.
    """
    try:
        if db_manager.forms_collection is None:
            logger.warning("Database offline - simulating form creation")
            return {"success": True, "inserted_id": "simulated_form_id", "message": "Offline mode - form not saved"}

        university_name = (form_data.get('university_name') or '').strip()
        course_name = (form_data.get('course_name') or '').strip()
        training_id = (form_data.get('training_id') or '').strip().upper()
        # Normalize and validate questions
        raw_questions = form_data.get('questions') or []
        questions = []
        for idx, q in enumerate(raw_questions, start=1):
            qtype_raw = (q.get('type') or '').strip().lower()
            qtype = 'choice' if qtype_raw == 'choice' else ('subjective' if qtype_raw == 'subjective' else '')
            if not qtype:
                continue
            qtext_raw = q.get('text')
            qtext = (qtext_raw or '').strip()
            if not qtext:
                qtext = f"Question {idx}"
            questions.append({'type': qtype, 'text': qtext})

        # Relax validation: course_name is optional
        if not university_name or not training_id:
            return {"success": False, "message": "university_name and training_id are required"}
        if not questions:
            return {"success": False, "message": "At least one valid question is required"}

        # Validate question limits
        choice_count = sum(1 for q in questions if q.get('type') == 'choice')
        subj_count = sum(1 for q in questions if q.get('type') == 'subjective')
        if choice_count > 10 or subj_count > 10 or len(questions) > 20:
            return {"success": False, "message": "Exceeded question limits (max 10 choice, 10 subjective, 20 total)"}

        doc = {
            'university_name': university_name,
            'course_name': course_name,
            'training_id': training_id,
            'questions': questions,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_active': True
        }

        result = db_manager.forms_collection.insert_one(doc)
        return {"success": True, "inserted_id": str(result.inserted_id)}
    except Exception as e:
        logger.error(f"Error creating feedback form: {e}")
        return {"success": False, "message": f"Failed to create form: {str(e)}"}


def list_feedback_forms(group_by_university: bool = False) -> dict:
    try:
        if db_manager.forms_collection is None:
            return {"success": True, "data": []}
        cursor = db_manager.forms_collection.find({}).sort('created_at', -1)
        forms = []
        for doc in cursor:
            doc['_id'] = str(doc['_id'])
            forms.append(doc)
        if group_by_university:
            grouped = {}
            for f in forms:
                uni = f.get('university_name') or 'Unknown'
                grouped.setdefault(uni, []).append(f)
            return {"success": True, "data": grouped}
        return {"success": True, "data": forms}
    except Exception as e:
        logger.error(f"Error listing feedback forms: {e}")
        return {"success": False, "message": f"Failed to list forms: {str(e)}", "data": []}


def get_feedback_form_by_training(training_id: str) -> dict:
    try:
        if db_manager.forms_collection is None:
            return {"success": True, "data": None}
        form = db_manager.forms_collection.find_one({'training_id': (training_id or '').upper(), 'is_active': True})
        if not form:
            return {"success": True, "data": None}
        form['_id'] = str(form['_id'])
        return {"success": True, "data": form}
    except Exception as e:
        logger.error(f"Error getting feedback form by training: {e}")
        return {"success": False, "message": f"Failed to get form: {str(e)}"}


def update_feedback_form(form_id: str, update_data: dict) -> dict:
    try:
        if db_manager.forms_collection is None:
            return {"success": False, "message": "Database offline"}
        if 'questions' in update_data:
            questions = update_data.get('questions') or []
            choice_count = sum(1 for q in questions if q.get('type') == 'choice')
            subj_count = sum(1 for q in questions if q.get('type') == 'subjective')
            if choice_count > 10 or subj_count > 10 or len(questions) > 20:
                return {"success": False, "message": "Exceeded question limits (max 10 choice, 10 subjective, 20 total)"}
        update_data['updated_at'] = datetime.utcnow()
        result = db_manager.forms_collection.update_one({'_id': ObjectId(form_id)}, {'$set': update_data})
        if result.modified_count > 0:
            return {"success": True}
        return {"success": False, "message": "Form not found or no changes"}
    except Exception as e:
        logger.error(f"Error updating feedback form: {e}")
        return {"success": False, "message": f"Failed to update form: {str(e)}"}


def delete_feedback_form(form_id: str) -> dict:
    try:
        if db_manager.forms_collection is None:
            return {"success": False, "message": "Database offline"}
        result = db_manager.forms_collection.update_one({'_id': ObjectId(form_id)}, {'$set': {'is_active': False, 'updated_at': datetime.utcnow()}})
        if result.modified_count > 0:
            return {"success": True}
        return {"success": False, "message": "Form not found"}
    except Exception as e:
        logger.error(f"Error deleting feedback form: {e}")
        return {"success": False, "message": f"Failed to delete form: {str(e)}"}


def export_feedback_forms_csv() -> dict:
    try:
        forms_result = list_feedback_forms()
        if not forms_result.get('success'):
            return forms_result
        forms = forms_result.get('data') or []
        header = "University,Course,Training ID,Questions Count,Created At\n"
        rows = []
        for f in forms:
            rows.append(f"{f.get('university_name','')},{f.get('course_name','')},{f.get('training_id','')},{len(f.get('questions',[]))},{f.get('created_at','')}\n")
        csv_content = header + "".join(rows)
        return {"success": True, "csv_content": csv_content}
    except Exception as e:
        logger.error(f"Error exporting feedback forms: {e}")
        return {"success": False, "message": f"Failed to export forms: {str(e)}"}


def get_feedback_form_by_id(form_id: str) -> dict:
    """Fetch a single feedback form by ObjectId string."""
    try:
        if db_manager.forms_collection is None:
            return {"success": False, "message": "Database offline"}
        form = db_manager.forms_collection.find_one({'_id': ObjectId(form_id), 'is_active': True})
        if not form:
            return {"success": False, "message": "Form not found"}
        form['_id'] = str(form['_id'])
        return {"success": True, "data": form}
    except Exception as e:
        logger.error(f"Error getting feedback form by id: {e}")
        return {"success": False, "message": f"Failed to get form: {str(e)}"}