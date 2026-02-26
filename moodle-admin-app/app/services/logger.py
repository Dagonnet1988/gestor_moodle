import json
from datetime import datetime
from flask import request, session
from app.services.db import get_connection, table


# Nombre de la tabla de logs (se crea en la BD de Moodle con prefijo propio)
LOG_TABLE = 'app_action_log'


def init_log_table():
    """Crea la tabla de logs si no existe."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {LOG_TABLE} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NULL,
                    username VARCHAR(255) NULL,
                    action VARCHAR(100) NOT NULL,
                    target_type VARCHAR(50) NULL,
                    target_id INT NULL,
                    details TEXT NULL,
                    ip_address VARCHAR(45) NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user_id (user_id),
                    INDEX idx_action (action),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
    finally:
        conn.close()


def log_action(action, target_type=None, target_id=None, details=None):
    """Registra una acción en la tabla de logs.
    
    Args:
        action: Tipo de acción (LOGIN, LOGOUT, CREATE_USER, EDIT_USER, 
                DISABLE_USER, ENROL_USER, UNENROL_USER, SEND_EMAIL, 
                BULK_EMAIL, EXPORT_DATA, etc.)
        target_type: Tipo de entidad afectada (user, course, enrolment, email)
        target_id: ID de la entidad afectada
        details: Diccionario con detalles adicionales (se guarda como JSON)
    """
    user_id = session.get('user_id')
    username = session.get('username', 'anonymous')
    ip_address = request.remote_addr if request else None
    
    details_json = json.dumps(details, ensure_ascii=False) if details else None
    
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                INSERT INTO {LOG_TABLE} 
                    (user_id, username, action, target_type, target_id, details, ip_address)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (user_id, username, action, target_type, target_id, details_json, ip_address))
    finally:
        conn.close()


def get_logs(page=1, per_page=50, filters=None):
    """Obtiene los logs con paginación y filtros.
    
    Args:
        page: Número de página
        per_page: Registros por página
        filters: Diccionario con filtros opcionales:
            - username: Filtrar por usuario
            - action: Filtrar por tipo de acción
            - date_from: Fecha desde (YYYY-MM-DD)
            - date_to: Fecha hasta (YYYY-MM-DD)
            - target_type: Filtrar por tipo de entidad
    
    Returns:
        Tupla (logs, total_count)
    """
    where_clauses = []
    params = []
    
    if filters:
        if filters.get('username'):
            where_clauses.append("username LIKE %s")
            params.append(f"%{filters['username']}%")
        if filters.get('action'):
            where_clauses.append("action = %s")
            params.append(filters['action'])
        if filters.get('date_from'):
            where_clauses.append("created_at >= %s")
            params.append(f"{filters['date_from']} 00:00:00")
        if filters.get('date_to'):
            where_clauses.append("created_at <= %s")
            params.append(f"{filters['date_to']} 23:59:59")
        if filters.get('target_type'):
            where_clauses.append("target_type = %s")
            params.append(filters['target_type'])
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Contar total
            cursor.execute(f"SELECT COUNT(*) as total FROM {LOG_TABLE} WHERE {where_sql}", params)
            total = cursor.fetchone()['total']
            
            # Obtener registros paginados
            offset = (page - 1) * per_page
            cursor.execute(f"""
                SELECT * FROM {LOG_TABLE} 
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, params + [per_page, offset])
            logs = cursor.fetchall()
            
            return logs, total
    finally:
        conn.close()
