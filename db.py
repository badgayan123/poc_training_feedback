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
