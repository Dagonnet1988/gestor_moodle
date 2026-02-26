"""Lógica específica de Moodle para manipulación de datos."""
import time
import bcrypt
from app.services.db import execute_query, execute_insert, execute_update, table
from app.config import Config


# ============================================================
# USUARIOS
# ============================================================

def get_users(page=1, per_page=25, search=None, status=None):
    """Obtiene lista de usuarios con paginación y filtros.
    
    Args:
        page: Número de página
        per_page: Registros por página
        search: Búsqueda por nombre, apellido, email o username
        status: 'active', 'suspended' o None para todos
    
    Returns:
        Tupla (users, total_count)
    """
    where_clauses = ["u.deleted = 0", "u.id > 1"]
    params = []
    
    if search:
        where_clauses.append(
            "(u.username LIKE %s OR u.firstname LIKE %s OR u.lastname LIKE %s OR u.email LIKE %s)"
        )
        search_param = f"%{search}%"
        params.extend([search_param] * 4)
    
    if status == 'active':
        where_clauses.append("u.suspended = 0")
    elif status == 'suspended':
        where_clauses.append("u.suspended = 1")
    
    where_sql = " AND ".join(where_clauses)
    
    # Contar total
    count_result = execute_query(
        f"SELECT COUNT(*) as total FROM {table('user')} u WHERE {where_sql}",
        params
    )
    total = count_result[0]['total'] if count_result else 0
    
    # Obtener registros
    offset = (page - 1) * per_page
    users = execute_query(f"""
        SELECT u.id, u.username, u.firstname, u.lastname, u.email, 
               u.city, u.country, u.suspended, u.confirmed, u.auth,
               u.timecreated, u.lastaccess, u.institution, u.department,
               u.phone1, u.phone2, u.idnumber
        FROM {table('user')} u
        WHERE {where_sql}
        ORDER BY u.lastname, u.firstname
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])
    
    return users, total


def get_user_by_id(user_id):
    """Obtiene un usuario por su ID."""
    return execute_query(f"""
        SELECT u.id, u.username, u.firstname, u.lastname, u.email,
               u.city, u.country, u.suspended, u.confirmed, u.auth,
               u.timecreated, u.lastaccess, u.institution, u.department,
               u.phone1, u.phone2, u.idnumber, u.description
        FROM {table('user')} u
        WHERE u.id = %s AND u.deleted = 0
    """, (user_id,), fetchone=True)


def create_user(username, password, firstname, lastname, email, 
                institution='', department='', city='', country='CO',
                phone1='', phone2='', idnumber=''):
    """Crea un nuevo usuario en Moodle.
    
    Returns:
        ID del nuevo usuario
    
    Raises:
        ValueError si el username o email ya existe
    """
    # Verificar username único
    existing = execute_query(
        f"SELECT id FROM {table('user')} WHERE username = %s AND deleted = 0",
        (username,), fetchone=True
    )
    if existing:
        raise ValueError(f"El usuario '{username}' ya existe")
    
    # Verificar email único
    existing_email = execute_query(
        f"SELECT id FROM {table('user')} WHERE email = %s AND deleted = 0",
        (email,), fetchone=True
    )
    if existing_email:
        raise ValueError(f"El email '{email}' ya está en uso")
    
    # Hash de contraseña con bcrypt (compatible con Moodle)
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    # Moodle usa prefijo $2y$, Python genera $2b$, reemplazar
    password_hash_str = password_hash.decode('utf-8').replace('$2b$', '$2y$', 1)
    
    now = int(time.time())
    
    # Obtener mnethostid (normalmente es 1 para host local)
    mnet = execute_query(
        f"SELECT id FROM {table('mnet_host')} WHERE wwwroot = %s",
        (Config.MOODLE_URL,), fetchone=True
    )
    mnethostid = mnet['id'] if mnet else 1
    
    user_id = execute_insert(f"""
        INSERT INTO {table('user')} 
            (auth, confirmed, mnethostid, username, password, firstname, lastname, 
             email, city, country, institution, department, phone1, phone2, 
             idnumber, timecreated, timemodified, lang)
        VALUES 
            ('manual', 1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'es')
    """, (mnethostid, username, password_hash_str, firstname, lastname, email,
          city, country, institution, department, phone1, phone2, idnumber, now, now))
    
    return user_id


def update_user(user_id, firstname, lastname, email, 
                institution='', department='', city='', country='CO',
                phone1='', phone2='', idnumber=''):
    """Actualiza datos de un usuario existente."""
    # Verificar que el email no esté en uso por otro usuario
    existing_email = execute_query(
        f"SELECT id FROM {table('user')} WHERE email = %s AND id != %s AND deleted = 0",
        (email, user_id), fetchone=True
    )
    if existing_email:
        raise ValueError(f"El email '{email}' ya está en uso por otro usuario")
    
    now = int(time.time())
    
    return execute_update(f"""
        UPDATE {table('user')} SET
            firstname = %s, lastname = %s, email = %s,
            institution = %s, department = %s, city = %s, country = %s,
            phone1 = %s, phone2 = %s, idnumber = %s, timemodified = %s
        WHERE id = %s AND deleted = 0
    """, (firstname, lastname, email, institution, department, city, country,
          phone1, phone2, idnumber, now, user_id))


def toggle_user_suspension(user_id, suspend=True):
    """Habilita o deshabilita un usuario.
    
    Args:
        user_id: ID del usuario
        suspend: True para suspender, False para habilitar
    """
    now = int(time.time())
    return execute_update(f"""
        UPDATE {table('user')} SET suspended = %s, timemodified = %s
        WHERE id = %s AND deleted = 0
    """, (1 if suspend else 0, now, user_id))


def reset_user_password(user_id, new_password):
    """Resetea la contraseña de un usuario."""
    password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    password_hash_str = password_hash.decode('utf-8').replace('$2b$', '$2y$', 1)
    
    now = int(time.time())
    return execute_update(f"""
        UPDATE {table('user')} SET password = %s, timemodified = %s
        WHERE id = %s AND deleted = 0
    """, (password_hash_str, now, user_id))


def get_user_courses(user_id):
    """Obtiene los cursos en los que está inscrito un usuario."""
    return execute_query(f"""
        SELECT c.id, c.fullname, c.shortname, ue.status, ue.timestart, ue.timeend,
               r.shortname as role_shortname, r.name as role_name
        FROM {table('user_enrolments')} ue
        JOIN {table('enrol')} e ON e.id = ue.enrolid
        JOIN {table('course')} c ON c.id = e.courseid
        LEFT JOIN {table('role_assignments')} ra ON ra.userid = %s 
            AND ra.contextid = (
                SELECT ctx.id FROM {table('context')} ctx 
                WHERE ctx.contextlevel = 50 AND ctx.instanceid = c.id
            )
        LEFT JOIN {table('role')} r ON r.id = ra.roleid
        WHERE ue.userid = %s
        ORDER BY c.fullname
    """, (user_id, user_id))


# ============================================================
# CURSOS
# ============================================================

def get_courses(page=1, per_page=25, search=None):
    """Obtiene lista de cursos con paginación."""
    where_clauses = ["c.id > 1"]
    params = []
    
    if search:
        where_clauses.append(
            "(c.fullname LIKE %s OR c.shortname LIKE %s)"
        )
        search_param = f"%{search}%"
        params.extend([search_param] * 2)
    
    where_sql = " AND ".join(where_clauses)
    
    count_result = execute_query(
        f"SELECT COUNT(*) as total FROM {table('course')} c WHERE {where_sql}",
        params
    )
    total = count_result[0]['total'] if count_result else 0
    
    offset = (page - 1) * per_page
    courses = execute_query(f"""
        SELECT c.id, c.fullname, c.shortname, c.visible, c.startdate, c.enddate,
               cc.name as category_name,
               (SELECT COUNT(*) FROM {table('user_enrolments')} ue 
                JOIN {table('enrol')} e ON e.id = ue.enrolid 
                WHERE e.courseid = c.id AND ue.status = 0) as enrolled_count
        FROM {table('course')} c
        LEFT JOIN {table('course_categories')} cc ON cc.id = c.category
        WHERE {where_sql}
        ORDER BY c.fullname
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])
    
    return courses, total


def get_course_by_id(course_id):
    """Obtiene un curso por su ID."""
    return execute_query(f"""
        SELECT c.id, c.fullname, c.shortname, c.visible, c.startdate, c.enddate,
               c.summary, cc.name as category_name
        FROM {table('course')} c
        LEFT JOIN {table('course_categories')} cc ON cc.id = c.category
        WHERE c.id = %s
    """, (course_id,), fetchone=True)


def get_course_participants(course_id):
    """Obtiene los participantes de un curso."""
    return execute_query(f"""
        SELECT u.id, u.username, u.firstname, u.lastname, u.email,
               ue.status as enrol_status, ue.timestart, ue.timeend, ue.timecreated,
               r.shortname as role_shortname, r.name as role_name
        FROM {table('user_enrolments')} ue
        JOIN {table('enrol')} e ON e.id = ue.enrolid
        JOIN {table('user')} u ON u.id = ue.userid
        LEFT JOIN {table('context')} ctx ON ctx.contextlevel = 50 AND ctx.instanceid = e.courseid
        LEFT JOIN {table('role_assignments')} ra ON ra.userid = u.id AND ra.contextid = ctx.id
        LEFT JOIN {table('role')} r ON r.id = ra.roleid
        WHERE e.courseid = %s AND u.deleted = 0
        ORDER BY u.lastname, u.firstname
    """, (course_id,))


# ============================================================
# INSCRIPCIONES
# ============================================================

def enrol_user_in_course(user_id, course_id, role_id=5):
    """Inscribe un usuario en un curso.
    
    Args:
        user_id: ID del usuario
        course_id: ID del curso
        role_id: ID del rol (5 = student por defecto)
    
    Returns:
        ID de la inscripción
    """
    # Verificar que el usuario existe
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("Usuario no encontrado")
    
    # Verificar que el curso existe
    course = get_course_by_id(course_id)
    if not course:
        raise ValueError("Curso no encontrado")
    
    # Buscar o crear método de inscripción manual
    enrol_method = execute_query(f"""
        SELECT id FROM {table('enrol')} 
        WHERE courseid = %s AND enrol = 'manual'
    """, (course_id,), fetchone=True)
    
    if not enrol_method:
        # Crear método de inscripción manual
        enrol_id = execute_insert(f"""
            INSERT INTO {table('enrol')} (enrol, status, courseid, sortorder, timecreated, timemodified)
            VALUES ('manual', 0, %s, 0, %s, %s)
        """, (course_id, int(time.time()), int(time.time())))
    else:
        enrol_id = enrol_method['id']
    
    # Verificar si ya está inscrito
    existing = execute_query(f"""
        SELECT id FROM {table('user_enrolments')} 
        WHERE enrolid = %s AND userid = %s
    """, (enrol_id, user_id), fetchone=True)
    
    if existing:
        raise ValueError("El usuario ya está inscrito en este curso")
    
    now = int(time.time())
    
    # Crear inscripción
    ue_id = execute_insert(f"""
        INSERT INTO {table('user_enrolments')} 
            (status, enrolid, userid, timestart, timeend, modifierid, timecreated, timemodified)
        VALUES (0, %s, %s, %s, 0, 0, %s, %s)
    """, (enrol_id, user_id, now, now, now))
    
    # Asignar rol en el contexto del curso
    context = execute_query(f"""
        SELECT id FROM {table('context')} 
        WHERE contextlevel = 50 AND instanceid = %s
    """, (course_id,), fetchone=True)
    
    if context:
        # Verificar si ya tiene asignación de rol
        existing_role = execute_query(f"""
            SELECT id FROM {table('role_assignments')}
            WHERE roleid = %s AND contextid = %s AND userid = %s
        """, (role_id, context['id'], user_id), fetchone=True)
        
        if not existing_role:
            execute_insert(f"""
                INSERT INTO {table('role_assignments')} 
                    (roleid, contextid, userid, timemodified, modifierid)
                VALUES (%s, %s, %s, %s, 0)
            """, (role_id, context['id'], user_id, now))
    
    return ue_id


def unenrol_user_from_course(user_id, course_id):
    """Desinscribe un usuario de un curso."""
    # Buscar inscripción
    enrol_method = execute_query(f"""
        SELECT e.id as enrol_id FROM {table('enrol')} e
        WHERE e.courseid = %s AND e.enrol = 'manual'
    """, (course_id,), fetchone=True)
    
    if not enrol_method:
        raise ValueError("No se encontró método de inscripción manual")
    
    # Eliminar inscripción
    affected = execute_update(f"""
        DELETE FROM {table('user_enrolments')}
        WHERE enrolid = %s AND userid = %s
    """, (enrol_method['enrol_id'], user_id))
    
    # Eliminar asignación de rol
    context = execute_query(f"""
        SELECT id FROM {table('context')}
        WHERE contextlevel = 50 AND instanceid = %s
    """, (course_id,), fetchone=True)
    
    if context:
        execute_update(f"""
            DELETE FROM {table('role_assignments')}
            WHERE contextid = %s AND userid = %s
        """, (context['id'], user_id))
    
    return affected


# ============================================================
# CALIFICACIONES
# ============================================================

def get_user_grades(user_id):
    """Obtiene todas las calificaciones de un usuario en todos sus cursos."""
    return execute_query(f"""
        SELECT c.id as course_id, c.fullname as course_name, c.shortname,
               gi.itemname, gi.itemtype, gi.grademax, gi.grademin,
               gg.finalgrade, gg.rawgrade, gg.timemodified
        FROM {table('grade_grades')} gg
        JOIN {table('grade_items')} gi ON gi.id = gg.itemid
        JOIN {table('course')} c ON c.id = gi.courseid
        WHERE gg.userid = %s
        ORDER BY c.fullname, gi.sortorder
    """, (user_id,))


def get_course_grades(course_id):
    """Obtiene las calificaciones de todos los participantes de un curso."""
    return execute_query(f"""
        SELECT u.id as user_id, u.username, u.firstname, u.lastname, u.email,
               gi.id as item_id, gi.itemname, gi.itemtype, gi.grademax, gi.grademin,
               gg.finalgrade, gg.rawgrade, gg.timemodified
        FROM {table('grade_grades')} gg
        JOIN {table('grade_items')} gi ON gi.id = gg.itemid
        JOIN {table('user')} u ON u.id = gg.userid
        WHERE gi.courseid = %s AND u.deleted = 0
        ORDER BY u.lastname, u.firstname, gi.sortorder
    """, (course_id,))


def get_course_final_grades(course_id):
    """Obtiene solo la nota final del curso para cada participante."""
    return execute_query(f"""
        SELECT u.id as user_id, u.username, u.firstname, u.lastname, u.email,
               gi.grademax, gi.grademin, gg.finalgrade, gg.timemodified
        FROM {table('grade_grades')} gg
        JOIN {table('grade_items')} gi ON gi.id = gg.itemid
        JOIN {table('user')} u ON u.id = gg.userid
        WHERE gi.courseid = %s AND gi.itemtype = 'course' AND u.deleted = 0
        ORDER BY u.lastname, u.firstname
    """, (course_id,))
