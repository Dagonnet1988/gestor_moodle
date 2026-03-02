import pymysql
from pymysql.cursors import DictCursor
from app.config import Config


def get_connection():
    """Obtiene una conexión a la base de datos MariaDB de Moodle."""
    return pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASS,
        database=Config.DB_NAME,
        charset=Config.DB_CHARSET,
        cursorclass=DictCursor,
        autocommit=True
    )


def execute_query(query, params=None, fetchone=False):
    """Ejecuta una consulta SELECT y retorna los resultados."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if params:
                # escape any '%' characters in string parameters so that the
                # underlying Python formatting (used by pymysql) does not
                # interpret them as additional placeholders.
                params = tuple(p.replace('%%','%%').replace('%','%%') if isinstance(p, str) else p
                               for p in params)
            cursor.execute(query, params)
            if fetchone:
                return cursor.fetchone()
            return cursor.fetchall()
    finally:
        conn.close()


def execute_insert(query, params=None):
    """Ejecuta una consulta INSERT y retorna el ID insertado."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if params:
                params = tuple(p.replace('%%','%%').replace('%','%%') if isinstance(p, str) else p
                               for p in params)
            cursor.execute(query, params)
            return cursor.lastrowid
    finally:
        conn.close()


def execute_update(query, params=None):
    """Ejecuta una consulta UPDATE/DELETE y retorna las filas afectadas."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if params:
                params = tuple(p.replace('%%','%%').replace('%','%%') if isinstance(p, str) else p
                               for p in params)
            cursor.execute(query, params)
            return cursor.rowcount
    finally:
        conn.close()


def table(name):
    """Retorna el nombre de tabla con el prefijo de Moodle."""
    return f"{Config.DB_PREFIX}{name}"
