import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # MongoDB Configuration
    MONGO_URI = os.getenv('MONGO_URI')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'feedback_analysis')
    COLLECTION_NAME = os.getenv('COLLECTION_NAME', 'feedbacks')
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    # Admin Configuration
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
    
    # Email Configuration
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
    EMAIL_FROM = os.getenv('EMAIL_FROM', EMAIL_USERNAME)
    
    # Trainer Email Mapping
    TRAINER_EMAILS = {
        'Amit Choudhary': 'choudhary.amit84@gmail.com',
        'Lijin': 'lijin.itc@gmail.com',
        'Snehasis Guha': 'snehasis.guha@example.com',  # TODO: Replace with actual email
        'Nitesh Dhar Badgayan': 'nitesh.badgayan@gmail.com',
        'Jagadish GS': 'jagadishgurushankar@gmail.com',
        'Shalini Kanagasabhapathy': 'shalini.kanagasabhapathy@example.com',  # TODO: Replace with actual email
        'Rajeev Anwar': 'anwar.rajeev02@gmail.com',
        'Devang Sareen': 'sareendev1812@gmail.com',
        'Mohan Reddy': 'mk4977275@gmail.com',
        'Ayushman Ghosh': 'ayushman.g99@gmail.com',
        'Siddharth': 'siddharth18077@gmail.com',
        'Omkar Jagtap': 'omkarjagtap9773@gmail.com'
    }