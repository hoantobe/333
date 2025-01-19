import os
from dotenv import load_dotenv

# Load biến môi trường từ file .env
load_dotenv()

class Config:
    # SECRET_KEY
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for Flask application")

    # Database URI
    database_url = os.environ.get(
        'DATABASE_URL',
        'postgresql://default_user:default_pass@localhost/default_db'
    )
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload File Configuration
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    # Email Configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 465
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        raise ValueError("Email configuration is not set in environment variables.")
