from datetime import datetime
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from app.config import Config


def create_app():
    """Factory de la aplicación Flask."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Soporte para proxy inverso con prefijo (ej: /moodle)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_prefix=1)
    
    # Filtro de Jinja2 para formatear timestamps Unix
    @app.template_filter('strftime')
    def _jinja2_filter_strftime(timestamp, fmt='%d/%m/%Y %H:%M'):
        if not timestamp:
            return ''
        try:
            return datetime.fromtimestamp(int(timestamp)).strftime(fmt)
        except (ValueError, TypeError, OSError):
            return str(timestamp)
    
    # Inicializar tabla de logs
    with app.app_context():
        try:
            from app.services.logger import init_log_table
            init_log_table()
        except Exception as e:
            print(f"[WARN] No se pudo crear la tabla de logs: {e}")
    
    # Registrar blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.users import users_bp
    from app.routes.courses import courses_bp
    from app.routes.enrolments import enrolments_bp
    from app.routes.grades import grades_bp
    from app.routes.emails import emails_bp
    from app.routes.logs import logs_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(enrolments_bp)
    app.register_blueprint(grades_bp)
    app.register_blueprint(emails_bp)
    app.register_blueprint(logs_bp)
    
    return app
