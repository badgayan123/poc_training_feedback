import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # MongoDB Configuration
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://niteshbadgayan:Ganapati%40123@cluster0.lw4vz.mongodb.net/feedback_analysis?retryWrites=true&w=majority&appName=Cluster0')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'feedback_analysis')
    COLLECTION_NAME = os.getenv('COLLECTION_NAME', 'feedbacks')
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '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')
    
    # Admin Configuration
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'niteshbadgayan@kpmg.com')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Ganapati@123')
