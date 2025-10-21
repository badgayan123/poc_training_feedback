from pymongo import MongoClient
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
        self.connect()
    
    def connect(self):
        """Establish connection to MongoDB"""
        try:
            self.client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
            self.db = self.client[Config.DATABASE_NAME]
            self.collection = self.db[Config.COLLECTION_NAME]
            # Test the connection
            self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            # Create a mock connection for development
            self.client = None
            self.db = None
            self.collection = None
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

def delete_feedback(feedback_id):
    """
    Delete a specific feedback by ID
    
    Args:
        feedback_id (str): The ID of the feedback to delete
        
    Returns:
        dict: Result with success status and message
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - simulating feedback deletion")
            return {"success": True, "message": "Offline mode - deletion simulated"}
        
        from bson import ObjectId
        
        # Convert string ID to ObjectId
        try:
            object_id = ObjectId(feedback_id)
        except Exception:
            return {
                'success': False,
                'message': 'Invalid feedback ID format'
            }
        
        # Check if feedback exists
        existing = db_manager.collection.find_one({'_id': object_id})
        if not existing:
            return {
                'success': False,
                'message': 'Feedback not found'
            }
        
        # Delete the feedback
        result = db_manager.collection.delete_one({'_id': object_id})
        
        if result.deleted_count > 0:
            logger.info(f"Feedback deleted with ID: {feedback_id}")
            return {
                'success': True,
                'message': 'Feedback deleted successfully',
                'deleted_id': feedback_id
            }
        else:
            return {
                'success': False,
                'message': 'Failed to delete feedback'
            }
            
    except Exception as e:
        logger.error(f"Error deleting feedback: {e}")
        return {
            'success': False,
            'message': f'Failed to delete feedback: {str(e)}'
        }

def delete_feedback_by_training_id(training_id):
    """
    Delete all feedback for a specific training ID
    
    Args:
        training_id (str): The training ID to delete all feedback for
        
    Returns:
        dict: Result with success status, count of deleted records, and message
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - simulating feedback deletion by training ID")
            return {"success": True, "message": "Offline mode - deletion simulated", "deleted_count": 0}
        
        # Count existing feedback for this training ID
        count_before = db_manager.collection.count_documents({'training_id': training_id})
        
        if count_before == 0:
            return {
                'success': False,
                'message': f'No feedback found for training ID: {training_id}'
            }
        
        # Delete all feedback for this training ID
        result = db_manager.collection.delete_many({'training_id': training_id})
        
        logger.info(f"Deleted {result.deleted_count} feedback records for training ID: {training_id}")
        return {
            'success': True,
            'message': f'Successfully deleted {result.deleted_count} feedback records for training ID: {training_id}',
            'deleted_count': result.deleted_count,
            'training_id': training_id
        }
        
    except Exception as e:
        logger.error(f"Error deleting feedback by training ID: {e}")
        return {
            'success': False,
            'message': f'Failed to delete feedback: {str(e)}'
        }

# University Database Management Functions

def insert_university_course(university_data):
    """
    Insert university course data into MongoDB
    
    Args:
        university_data (dict): University course data to insert
        
    Returns:
        dict: Result with success status and inserted_id or error message
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - simulating university course insertion")
            return {"success": True, "inserted_id": "simulated_id", "message": "Offline mode - data not saved"}
        
        # Validate required fields
        required_fields = ['university_name', 'course', 'training_id']
        for field in required_fields:
            if not university_data.get(field):
                return {
                    'success': False,
                    'message': f'{field} is required'
                }
        
        # Normalize data
        university_data['university_name'] = university_data['university_name'].strip().upper()
        university_data['course'] = university_data['course'].strip().upper()
        university_data['training_id'] = university_data['training_id'].strip().upper()
        
        # Check for duplicates
        existing = db_manager.collection.find_one({
            'university_name': university_data['university_name'],
            'course': university_data['course'],
            'training_id': university_data['training_id']
        })
        
        if existing:
            return {
                'success': False,
                'message': 'This university course combination already exists'
            }
        
        # Add metadata
        university_data['created_at'] = datetime.utcnow()
        university_data['type'] = 'university_course'
        
        # Insert the document
        result = db_manager.collection.insert_one(university_data)
        
        logger.info(f"University course inserted with ID: {result.inserted_id}")
        return {
            'success': True,
            'message': 'University course added successfully',
            'inserted_id': str(result.inserted_id)
        }
    except Exception as e:
        logger.error(f"Error inserting university course: {e}")
        return {
            'success': False,
            'message': f'Failed to insert university course: {str(e)}'
        }

def get_university_courses():
    """
    Retrieve all university courses from MongoDB
    
    Returns:
        dict: Result with success status and university course data or error message
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - returning empty university courses list")
            return {"success": True, "data": [], "message": "Offline mode - no data available"}
        
        # Query for university courses
        query = {'type': 'university_course'}
        cursor = db_manager.collection.find(query)
        courses = []
        
        for doc in cursor:
            # Convert ObjectId to string for JSON serialization
            doc['_id'] = str(doc['_id'])
            courses.append(doc)
        
        logger.info(f"Retrieved {len(courses)} university course records")
        return {
            'success': True,
            'message': f'Retrieved {len(courses)} university course records',
            'data': courses,
            'count': len(courses)
        }
    except Exception as e:
        logger.error(f"Error retrieving university courses: {e}")
        return {
            'success': False,
            'message': f'Failed to retrieve university courses: {str(e)}',
            'data': []
        }

def delete_university_course(course_id):
    """
    Delete a specific university course by ID
    
    Args:
        course_id (str): The ID of the university course to delete
        
    Returns:
        dict: Result with success status and message
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - simulating university course deletion")
            return {"success": True, "message": "Offline mode - deletion simulated"}
        
        from bson import ObjectId
        
        # Convert string ID to ObjectId
        try:
            object_id = ObjectId(course_id)
        except Exception:
            return {
                'success': False,
                'message': 'Invalid course ID format'
            }
        
        # Check if course exists
        existing = db_manager.collection.find_one({'_id': object_id, 'type': 'university_course'})
        if not existing:
            return {
                'success': False,
                'message': 'University course not found'
            }
        
        # Delete the course
        result = db_manager.collection.delete_one({'_id': object_id})
        
        if result.deleted_count > 0:
            logger.info(f"University course deleted with ID: {course_id}")
            return {
                'success': True,
                'message': 'University course deleted successfully',
                'deleted_id': course_id
            }
        else:
            return {
                'success': False,
                'message': 'Failed to delete university course'
            }
            
    except Exception as e:
        logger.error(f"Error deleting university course: {e}")
        return {
            'success': False,
            'message': f'Failed to delete university course: {str(e)}'
        }

def validate_university_course(university_name, course, training_id):
    """
    Validate if a university course combination exists
    
    Args:
        university_name (str): University name to validate
        course (str): Course to validate
        training_id (str): Training ID to validate
        
    Returns:
        dict: Result with success status and validation result
    """
    try:
        if db_manager.collection is None:
            logger.warning("Database offline - simulating university course validation")
            return {"success": True, "valid": True, "message": "Offline mode - validation simulated"}
        
        # Normalize input data
        university_name = university_name.strip().upper()
        course = course.strip().upper()
        training_id = training_id.strip().upper()
        
        # Check if combination exists
        existing = db_manager.collection.find_one({
            'university_name': university_name,
            'course': course,
            'training_id': training_id,
            'type': 'university_course'
        })
        
        if existing:
            return {
                'success': True,
                'valid': True,
                'message': 'University course combination is valid'
            }
        else:
            return {
                'success': True,
                'valid': False,
                'message': 'University course combination not found'
            }
            
    except Exception as e:
        logger.error(f"Error validating university course: {e}")
        return {
            'success': False,
            'valid': False,
            'message': f'Validation failed: {str(e)}'
        }