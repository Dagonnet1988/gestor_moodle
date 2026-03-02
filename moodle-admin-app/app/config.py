import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuración de la aplicación."""

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'

    # Base de datos Moodle (MariaDB)
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_NAME = os.getenv('DB_NAME', 'moodle')
    DB_USER = os.getenv('DB_USER', 'moodle')
    DB_PASS = os.getenv('DB_PASS', '')
    DB_PREFIX = os.getenv('DB_PREFIX', 'mdl_')
    DB_CHARSET = 'utf8mb4'

    # SMTP
    MAIL_SERVER = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('SMTP_PORT', 587))
    MAIL_USERNAME = os.getenv('SMTP_USER', '')
    MAIL_PASSWORD = os.getenv('SMTP_PASS', '')
    MAIL_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL = False
    MAIL_DEFAULT_SENDER = os.getenv('SMTP_USER', '')
    MAIL_MAX_BULK = int(os.getenv('SMTP_MAX_BULK', 10))
    # segundos de pausa entre lotes cuando se envía correo masivo
    MAIL_BULK_PAUSE_SECONDS = int(os.getenv('SMTP_BULK_PAUSE', 5))

    # Moodle
    MOODLE_URL = os.getenv('MOODLE_URL', 'http://190.71.122.76/moodle/login/index.php')
