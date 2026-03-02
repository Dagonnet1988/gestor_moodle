"""Lógica específica de Moodle para manipulación de datos."""
import time
import bcrypt
from app.services.db import execute_query, execute_insert, execute_update, table, get_connection
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
    where_clauses = ["u.deleted = 0", "u.id > 1", "u.username NOT IN ('admin', 'guest')"]
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
        ORDER BY u.firstname, u.lastname
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])
    
    # calcular rol global más alto para cada usuario (para mostrar si se desea)
    from app.services.auth import get_role_label, get_user_top_roles
    for u in users:
        u['role_shortname'] = None
        u['role_name'] = None
        u['roles'] = []
        u['role_names'] = []
        top = get_user_top_roles(u['id'], n=2)
        if top:
            u['roles'] = [r['shortname'] for r in top]
            u['role_names'] = [r['label'] for r in top]
            u['role_shortname'] = u['roles'][0]
            u['role_name'] = ", ".join(u['role_names'])
        else:
            # no roles
            u['role_name'] = ''
    
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
                city='', country='CO', phone1=''):
    """Crea un nuevo usuario en Moodle.
    
    El identificador (idnumber) se mantendrá igual al username y el
    nombre de usuario también se sincronizará cuando se actualice.
    Si no se provee contraseña se usa el mismo valor del username/idnumber
    como contraseña por defecto para facilitar el ingreso inicial.
    
    Returns:
        ID del nuevo usuario
    
    Raises:
        ValueError si el username o email ya existe
    """
    # derivar username/idnumber cuando se envía vacío
    if not username:
        # extraer prefijo del correo (antes de @)
        username = email.split('@')[0]
    # si no se especifica password, usar el identificador
    if not password:
        password = username
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
    
    # idnumber será igual al username
    idnumber = username
    
    params = (mnethostid, username, password_hash_str, firstname, lastname, email,
          city, country, phone1, idnumber, now, now)
    query = f"""
        INSERT INTO {table('user')} 
            (auth, confirmed, mnethostid, username, password, firstname, lastname, 
             email, city, country, phone1, idnumber, timecreated, timemodified, lang)
        VALUES 
            ('manual', 1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'es')
    """
    # sanity check: number of placeholders should match len(params)
    ph = query.count('%s')
    if ph != len(params):
        raise RuntimeError(f"parameter count mismatch in create_user: {ph} placeholders vs {len(params)} params")
    user_id = execute_insert(query, params)
    
    return user_id


def update_user(user_id, firstname, lastname, email, 
                city='', country='CO', phone1='', idnumber='', username=None):
    """Actualiza datos de un usuario existente.

    Si se proporciona `username`, éste y el `idnumber` se sincronizan, ya que
    la aplicación trata ambos como el mismo campo de identificación.
    Si ``username`` / ``idnumber`` están vacíos se conservan los valores actuales.
    """
    # Verificar que el email no esté en uso por otro usuario
    existing_email = execute_query(
        f"SELECT id FROM {table('user')} WHERE email = %s AND id != %s AND deleted = 0",
        (email, user_id), fetchone=True
    )
    if existing_email:
        raise ValueError(f"El email '{email}' ya está en uso por otro usuario")
    
    now = int(time.time())
    
    # Determinar username/idnumber: si vienen vacíos, preservar los actuales
    effective_username = username or idnumber
    if not effective_username:
        current = execute_query(
            f"SELECT username, idnumber FROM {table('user')} WHERE id = %s",
            (user_id,), fetchone=True
        )
        effective_username = current['username'] if current else ''
        idnumber = current['idnumber'] if current else ''
    else:
        # Verificar que el username no esté en uso por otro usuario
        existing_uname = execute_query(
            f"SELECT id FROM {table('user')} WHERE username = %s AND id != %s AND deleted = 0",
            (effective_username, user_id), fetchone=True
        )
        if existing_uname:
            raise ValueError(f"El nombre de usuario '{effective_username}' ya está en uso por otro usuario")
        idnumber = effective_username
    
    return execute_update(f"""
        UPDATE {table('user')} SET
            firstname = %s, lastname = %s, email = %s,
            city = %s, country = %s,
            phone1 = %s, idnumber = %s, username = %s, timemodified = %s
        WHERE id = %s AND deleted = 0
    """, (firstname, lastname, email, city, country,
          phone1, idnumber, effective_username, now, user_id))


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
    """Obtiene los cursos en los que está inscrito un usuario.

    Calcula la calificación usando la misma lógica que Moodle:
    si ``aggregateonlygraded = 1``, sólo se divide entre los ítems
    que el usuario ha intentado.
    """
    # 1) Enrolled courses
    courses = execute_query(f"""
        SELECT DISTINCT c.id, c.fullname, c.shortname, cc.name as category_name,
               ue.status, ue.timestart, ue.timeend,
               r.shortname as role_shortname, r.name as role_name
        FROM {table('user_enrolments')} ue
        JOIN {table('enrol')} e ON e.id = ue.enrolid
        JOIN {table('course')} c ON c.id = e.courseid
        LEFT JOIN {table('course_categories')} cc ON cc.id = c.category
        LEFT JOIN {table('context')} ctx ON ctx.contextlevel = 50 AND ctx.instanceid = c.id
        LEFT JOIN {table('role_assignments')} ra ON ra.userid = %s AND ra.contextid = ctx.id
        LEFT JOIN {table('role')} r ON r.id = ra.roleid
        WHERE ue.userid = %s
        ORDER BY c.fullname
    """, (user_id, user_id))

    from app.services.auth import get_role_label

    # de-duplicate (multiple roles → multiple rows)
    by_course = {}
    for row in courses:
        cid = row['id']
        if cid not in by_course:
            by_course[cid] = row

    if not by_course:
        return []

    course_ids = list(by_course.keys())

    # 2) Aggregation settings per course
    ph = ','.join(['%s'] * len(course_ids))
    cats = execute_query(f"""
        SELECT courseid, aggregateonlygraded
        FROM {table('grade_categories')}
        WHERE courseid IN ({ph}) AND depth = 1
    """, course_ids)
    only_graded_map = {c['courseid']: (c['aggregateonlygraded'] == 1) for c in cats}

    # 3) Grade items (mod type) per course
    items = execute_query(f"""
        SELECT gi.id, gi.courseid, gi.grademax
        FROM {table('grade_items')} gi
        WHERE gi.courseid IN ({ph}) AND gi.itemtype = 'mod'
    """, course_ids)
    # {course_id: {item_id: grademax}}
    course_items = {}
    for it in items:
        course_items.setdefault(it['courseid'], {})[it['id']] = float(it['grademax'] or 0)

    # 4) User grades in those items
    item_ids = [it['id'] for it in items]
    if item_ids:
        ph_items = ','.join(['%s'] * len(item_ids))
        grades = execute_query(f"""
            SELECT gg.itemid, gg.finalgrade
            FROM {table('grade_grades')} gg
            WHERE gg.userid = %s AND gg.itemid IN ({ph_items})
        """, [user_id] + item_ids)
    else:
        grades = []

    # item_id → finalgrade
    grade_map = {g['itemid']: g['finalgrade'] for g in grades}

    # 5) Compute percentage per course
    for cid, row in by_course.items():
        ci = course_items.get(cid, {})
        only_graded = only_graded_map.get(cid, True)
        total_possible = sum(ci.values())

        if only_graded:
            sum_grade = 0.0
            sum_max = 0.0
            for iid, mx in ci.items():
                fg = grade_map.get(iid)
                if fg is not None:
                    sum_grade += float(fg)
                    sum_max += mx
            if sum_max > 0:
                row['grade'] = sum_grade
                row['grademax'] = sum_max
                row['grade_pct'] = round((sum_grade / sum_max) * 100, 2)
            else:
                row['grade'] = None
                row['grademax'] = total_possible or None
                row['grade_pct'] = None
        else:
            sum_grade = sum(float(grade_map[iid]) for iid in ci if grade_map.get(iid) is not None)
            if total_possible > 0 and sum_grade > 0:
                row['grade'] = sum_grade
                row['grademax'] = total_possible
                row['grade_pct'] = round((sum_grade / total_possible) * 100, 2)
            else:
                row['grade'] = None
                row['grademax'] = total_possible or None
                row['grade_pct'] = None

        if row.get('role_shortname'):
            row['role_name'] = get_role_label(row['role_shortname'])

    return list(by_course.values())


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
        ORDER BY cc.name, c.fullname
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


def get_course_participants(course_id, status: str = 'active'):
    """Obtiene los participantes de un curso, junto con su calificación final.

    ``status`` determina qué usuarios incluir según su estado general (campo
    ``user.suspended``):

    * ``'active'`` (por defecto) → sólo usuarios no suspendidos
    * ``'suspended'`` → sólo usuarios suspendidos
    * ``'all'`` → todos los usuarios inscritos

    La calificación se calcula igual que Moodle: si la categoría del curso
    tiene ``aggregateonlygraded = 1`` (por defecto en agregación Natural),
    sólo se consideran los ítems que el usuario ha intentado para el
    denominador del porcentaje.
    """

    # ----- 1) Participantes base (sin grades) -------------------------
    enrol_sql = f"""
        SELECT DISTINCT u.id, u.username, u.firstname, u.lastname, u.email,
               ue.status as enrol_status, ue.timestart, ue.timeend, ue.timecreated,
               u.suspended as user_suspended,
               r.shortname as role_shortname, r.name as role_name
        FROM {table('user_enrolments')} ue
        JOIN {table('enrol')} e ON e.id = ue.enrolid
        JOIN {table('user')} u ON u.id = ue.userid
        LEFT JOIN {table('context')} ctx ON ctx.contextlevel = 50 AND ctx.instanceid = e.courseid
        LEFT JOIN {table('role_assignments')} ra ON ra.userid = u.id AND ra.contextid = ctx.id
        LEFT JOIN {table('role')} r ON r.id = ra.roleid
        WHERE e.courseid = %s AND u.deleted = 0
    """
    params = [course_id]
    if status == 'active':
        enrol_sql += " AND u.suspended = 0"
    elif status == 'suspended':
        enrol_sql += " AND u.suspended <> 0"
    enrolled = execute_query(enrol_sql, params)

    # de-duplicate (a user can appear twice if they have >1 role)
    by_user = {}
    for row in enrolled:
        uid = row['id']
        if uid not in by_user:
            by_user[uid] = row

    # ----- 2) Check aggregation settings for the course ----------------
    cat = execute_query(f"""
        SELECT aggregateonlygraded
        FROM {table('grade_categories')}
        WHERE courseid = %s AND depth = 1
        LIMIT 1
    """, (course_id,), fetchone=True)
    only_graded = (cat['aggregateonlygraded'] == 1) if cat else True

    # ----- 3) Grade items for the course (mod type only) ---------------
    items = execute_query(f"""
        SELECT gi.id, gi.grademax
        FROM {table('grade_items')} gi
        WHERE gi.courseid = %s AND gi.itemtype = 'mod'
    """, (course_id,))
    item_max = {it['id']: float(it['grademax'] or 0) for it in items}
    item_ids = list(item_max.keys())

    # ----- 4) Grades for enrolled users in those items -----------------
    if item_ids and by_user:
        placeholders_items = ','.join(['%s'] * len(item_ids))
        placeholders_users = ','.join(['%s'] * len(by_user))
        grades = execute_query(f"""
            SELECT gg.userid, gg.itemid, gg.finalgrade
            FROM {table('grade_grades')} gg
            WHERE gg.itemid IN ({placeholders_items})
              AND gg.userid IN ({placeholders_users})
        """, list(item_ids) + list(by_user.keys()))
    else:
        grades = []

    # Build per-user grade info: {user_id: {item_id: finalgrade}}
    user_grades = {}
    for g in grades:
        uid = g['userid']
        user_grades.setdefault(uid, {})[g['itemid']] = g['finalgrade']

    # ----- 5) Compute percentage per user ------------------------------
    total_possible = sum(item_max.values())  # for non-only-graded mode

    for uid, p in by_user.items():
        ug = user_grades.get(uid, {})
        if only_graded:
            # sum grades and max only for items the user actually has a grade
            sum_grade = 0.0
            sum_max = 0.0
            for iid, fg in ug.items():
                if fg is not None:
                    sum_grade += float(fg)
                    sum_max += item_max.get(iid, 0)
            if sum_max > 0:
                p['grade'] = sum_grade
                p['grademax'] = sum_max
                p['grade_pct'] = round((sum_grade / sum_max) * 100, 2)
            else:
                p['grade'] = None
                p['grademax'] = total_possible if total_possible else None
                p['grade_pct'] = None
        else:
            # classic mode: divide by total course possible
            sum_grade = sum(float(fg) for fg in ug.values() if fg is not None)
            if total_possible > 0 and sum_grade > 0:
                p['grade'] = sum_grade
                p['grademax'] = total_possible
                p['grade_pct'] = round((sum_grade / total_possible) * 100, 2)
            else:
                p['grade'] = None
                p['grademax'] = total_possible if total_possible else None
                p['grade_pct'] = None

    participants = list(by_user.values())
    participants.sort(key=lambda r: (
        -((r.get('grade_pct') or 0)),
        (r.get('firstname') or '').lower(),
        (r.get('lastname') or '').lower()
    ))
    return participants


def get_course_available_users(course_id):
    """Return users who can be enrolled in the given course.

    The query filters out:
    1. users marked deleted or suspended (we only consider active users)
    2. any user already enrolled in the course (based on mdl_user_enrolments).

    The returned rows contain basic identity fields so they can be displayed in
    a select box. This helper is used by the enrolment form to build the list
    of candidates when a course is selected.
    """
    sql = f"""
        SELECT u.id, u.username, u.firstname, u.lastname, u.email, u.idnumber
        FROM {table('user')} u
        WHERE u.deleted = 0
          AND u.suspended = 0
          AND u.username NOT IN ('admin','guest')
          AND u.id NOT IN (
              SELECT ue.userid FROM {table('user_enrolments')} ue
              JOIN {table('enrol')} e ON e.id = ue.enrolid
              WHERE e.courseid = %s
          )
        ORDER BY u.firstname, u.lastname
    """
    return execute_query(sql, (course_id,))


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


# ============================================================
# QUIZZES / INTENTOS
# ============================================================

def get_users_with_exhausted_attempts(course_id):
    """Devuelve un set de user_ids que han agotado intentos en al menos
    un quiz del curso (respetando overrides por usuario)."""
    rows = execute_query(f"""
        SELECT sub.userid
        FROM (
            SELECT qa.userid, q.id AS qid,
                   COALESCE(qo.attempts, q.attempts) AS max_att,
                   COUNT(*) AS used_att
            FROM {table('quiz')} q
            JOIN {table('quiz_attempts')} qa ON qa.quiz = q.id AND qa.preview = 0
            LEFT JOIN {table('quiz_overrides')} qo ON qo.quiz = q.id AND qo.userid = qa.userid
            WHERE q.course = %s
            GROUP BY qa.userid, q.id, COALESCE(qo.attempts, q.attempts)
        ) sub
        WHERE sub.max_att > 0 AND sub.used_att >= sub.max_att
    """, (course_id,))
    return {r['userid'] for r in rows}


def user_has_exhausted_attempts(course_id, user_id):
    """Devuelve True si el usuario ha agotado intentos en al menos un quiz del curso
    (respetando overrides por usuario)."""
    rows = execute_query(f"""
        SELECT 1
        FROM (
            SELECT q.id AS qid,
                   COALESCE(qo.attempts, q.attempts) AS max_att,
                   COUNT(*) AS used_att
            FROM {table('quiz')} q
            JOIN {table('quiz_attempts')} qa ON qa.quiz = q.id AND qa.preview = 0
            LEFT JOIN {table('quiz_overrides')} qo ON qo.quiz = q.id AND qo.userid = qa.userid
            WHERE q.course = %s AND qa.userid = %s
            GROUP BY q.id, COALESCE(qo.attempts, q.attempts)
        ) sub
        WHERE sub.max_att > 0 AND sub.used_att >= sub.max_att
        LIMIT 1
    """, (course_id, user_id))
    return len(rows) > 0


def get_course_quizzes(course_id):
    """Devuelve los cuestionarios de un curso.

    Retorna lista de dicts con id, name, attempts (máx intentos, 0=ilimitado).
    """
    return execute_query(f"""
        SELECT q.id, q.name, q.attempts
        FROM {table('quiz')} q
        WHERE q.course = %s
        ORDER BY q.name
    """, (course_id,))


def get_user_quiz_attempts_count(quiz_id, user_id):
    """Cuenta cuántos intentos *finalizados* tiene un usuario en un quiz."""
    row = execute_query(f"""
        SELECT COUNT(*) AS cnt
        FROM {table('quiz_attempts')} qa
        WHERE qa.quiz = %s AND qa.userid = %s AND qa.preview = 0
    """, (quiz_id, user_id), fetchone=True)
    return row['cnt'] if row else 0


def get_quiz_max_attempts_for_user(quiz_id, user_id):
    """Devuelve el máximo de intentos permitidos para un usuario en un quiz.

    Si existe un override para el usuario, se usa ese valor; de lo
    contrario se usa el valor por defecto del quiz.
    0 = intentos ilimitados.
    """
    # 1) check override
    ovr = execute_query(f"""
        SELECT qo.attempts
        FROM {table('quiz_overrides')} qo
        WHERE qo.quiz = %s AND qo.userid = %s
    """, (quiz_id, user_id), fetchone=True)
    if ovr is not None:
        return ovr['attempts']
    # 2) default from quiz
    q = execute_query(f"""
        SELECT q.attempts FROM {table('quiz')} q WHERE q.id = %s
    """, (quiz_id,), fetchone=True)
    return q['attempts'] if q else 0


def allow_extra_quiz_attempt(quiz_id, user_id):
    """Concede un intento adicional a un usuario en un quiz.

    Si ya existe un override, incrementa attempts en 1.
    Si no, crea uno con el máximo del quiz + 1.
    Retorna el nuevo valor de max attempts para ese usuario.
    """
    current_max = get_quiz_max_attempts_for_user(quiz_id, user_id)

    # Si ya es ilimitado (0) no hacemos nada
    if current_max == 0:
        return 0

    new_max = current_max + 1

    # ¿ya existe override?
    ovr = execute_query(f"""
        SELECT id FROM {table('quiz_overrides')} qo
        WHERE qo.quiz = %s AND qo.userid = %s
    """, (quiz_id, user_id), fetchone=True)

    if ovr:
        execute_update(f"""
            UPDATE {table('quiz_overrides')}
            SET attempts = %s
            WHERE id = %s
        """, (new_max, ovr['id']))
    else:
        execute_insert(f"""
            INSERT INTO {table('quiz_overrides')} (quiz, userid, attempts)
            VALUES (%s, %s, %s)
        """, (quiz_id, user_id, new_max))

    return new_max


def allow_extra_attempts_in_course(course_id, user_id):
    """Concede un intento extra en TODOS los quizzes del curso donde
    el usuario haya agotado sus intentos.

    Retorna lista de dicts con quiz name y nuevo máximo.
    """
    quizzes = get_course_quizzes(course_id)
    updated = []
    for q in quizzes:
        max_att = get_quiz_max_attempts_for_user(q['id'], user_id)
        if max_att == 0:
            # intentos ilimitados, no hace falta
            continue
        used = get_user_quiz_attempts_count(q['id'], user_id)
        if used >= max_att:
            new_max = allow_extra_quiz_attempt(q['id'], user_id)
            updated.append({'quiz_name': q['name'], 'new_max': new_max})
    return updated


def get_course_final_grades(course_id):
    """Obtiene la nota final del curso para cada participante.

    Calcula el porcentaje usando la misma lógica que Moodle:
    si ``aggregateonlygraded = 1`` sólo divide entre los ítems
    que cada usuario ha intentado.
    """
    # 1) Aggregation setting
    cat = execute_query(f"""
        SELECT aggregateonlygraded
        FROM {table('grade_categories')}
        WHERE courseid = %s AND depth = 1
        LIMIT 1
    """, (course_id,), fetchone=True)
    only_graded = (cat['aggregateonlygraded'] == 1) if cat else True

    # 2) Mod-type grade items
    items = execute_query(f"""
        SELECT gi.id, gi.grademax
        FROM {table('grade_items')} gi
        WHERE gi.courseid = %s AND gi.itemtype = 'mod'
    """, (course_id,))
    item_max = {it['id']: float(it['grademax'] or 0) for it in items}
    item_ids = list(item_max.keys())
    total_possible = sum(item_max.values())

    # 3) Enrolled users
    users = execute_query(f"""
        SELECT DISTINCT u.id as user_id, u.username, u.firstname, u.lastname, u.email
        FROM {table('user_enrolments')} ue
        JOIN {table('enrol')} e ON e.id = ue.enrolid
        JOIN {table('user')} u ON u.id = ue.userid
        WHERE e.courseid = %s AND u.deleted = 0 AND u.suspended = 0
    """, (course_id,))

    if not item_ids or not users:
        for u in users:
            u['grade_pct'] = None
            u['finalgrade'] = None
            u['grademax'] = total_possible or None
        return users

    user_ids = [u['user_id'] for u in users]
    ph_items = ','.join(['%s'] * len(item_ids))
    ph_users = ','.join(['%s'] * len(user_ids))

    # 4) All grades
    grades = execute_query(f"""
        SELECT gg.userid, gg.itemid, gg.finalgrade
        FROM {table('grade_grades')} gg
        WHERE gg.itemid IN ({ph_items}) AND gg.userid IN ({ph_users})
    """, item_ids + user_ids)

    # {user_id: {item_id: finalgrade}}
    user_grades = {}
    for g in grades:
        user_grades.setdefault(g['userid'], {})[g['itemid']] = g['finalgrade']

    # 5) Compute per user
    for u in users:
        ug = user_grades.get(u['user_id'], {})
        if only_graded:
            sum_grade = 0.0
            sum_max = 0.0
            for iid, fg in ug.items():
                if fg is not None:
                    sum_grade += float(fg)
                    sum_max += item_max.get(iid, 0)
            if sum_max > 0:
                u['finalgrade'] = sum_grade
                u['grademax'] = sum_max
                u['grade_pct'] = round((sum_grade / sum_max) * 100, 2)
            else:
                u['finalgrade'] = None
                u['grademax'] = total_possible or None
                u['grade_pct'] = None
        else:
            sum_grade = sum(float(fg) for fg in ug.values() if fg is not None)
            if total_possible > 0 and sum_grade > 0:
                u['finalgrade'] = sum_grade
                u['grademax'] = total_possible
                u['grade_pct'] = round((sum_grade / total_possible) * 100, 2)
            else:
                u['finalgrade'] = None
                u['grademax'] = total_possible or None
                u['grade_pct'] = None

    users.sort(key=lambda r: (-(r.get('grade_pct') or 0), (r.get('firstname') or '').lower(), (r.get('lastname') or '').lower()))
    return users


# ============================================================
# CLONACIÓN DE CALIFICACIONES
# ============================================================

def get_user_by_username(username):
    """Busca un usuario por su username (número de identificación)."""
    return execute_query(f"""
        SELECT id, username, firstname, lastname, email, suspended
        FROM {table('user')}
        WHERE username = %s AND deleted = 0
        LIMIT 1
    """, (username,), fetchone=True)


def get_user_grades_detail(user_id, course_ids=None):
    """Obtiene las calificaciones detalladas de un usuario.

    Retorna una lista de dicts agrupados por curso, cada uno con:
    - course_id, course_fullname, course_shortname
    - items: lista de {item_id, itemname, finalgrade, rawgrade, grademax}
    - grade_pct: porcentaje total del curso

    Si ``course_ids`` es una lista, filtra solo esos cursos.
    """
    # Cursos donde está inscrito
    enrol_sql = f"""
        SELECT DISTINCT e.courseid, c.fullname, c.shortname
        FROM {table('user_enrolments')} ue
        JOIN {table('enrol')} e ON e.id = ue.enrolid
        JOIN {table('course')} c ON c.id = e.courseid
        WHERE ue.userid = %s AND c.id != 1
    """
    params = [user_id]
    if course_ids:
        ph = ','.join(['%s'] * len(course_ids))
        enrol_sql += f" AND e.courseid IN ({ph})"
        params.extend(course_ids)
    enrol_sql += " ORDER BY c.fullname"

    courses = execute_query(enrol_sql, params)
    if not courses:
        return []

    result = []
    for c in courses:
        cid = c['courseid']
        # Items del curso (solo mod, no el total del curso)
        items = execute_query(f"""
            SELECT gi.id AS item_id, gi.itemname, gi.itemmodule, gi.grademax,
                   gg.rawgrade, gg.finalgrade
            FROM {table('grade_items')} gi
            LEFT JOIN {table('grade_grades')} gg ON gg.itemid = gi.id AND gg.userid = %s
            WHERE gi.courseid = %s AND gi.itemtype = 'mod'
            ORDER BY gi.sortorder
        """, (user_id, cid))

        # Calcular porcentaje
        sum_grade = 0.0
        sum_max = 0.0
        graded_items = []
        for it in items:
            it_dict = dict(it)
            graded_items.append(it_dict)
            if it['finalgrade'] is not None:
                sum_grade += float(it['finalgrade'])
                sum_max += float(it['grademax'] or 0)

        grade_pct = round((sum_grade / sum_max) * 100, 2) if sum_max > 0 else None

        result.append({
            'course_id': cid,
            'course_fullname': c['fullname'],
            'course_shortname': c['shortname'],
            'grade_items': graded_items,
            'grade_pct': grade_pct,
            'has_grades': any(it['finalgrade'] is not None for it in graded_items),
        })

    return result


def clone_grades(source_user_id, dest_user_id, course_ids):
    """Clona calificaciones del usuario origen al destino en los cursos indicados.

    Copia:
    1. mdl_grade_grades  (notas finales por actividad/curso)
    2. Intentos de quiz completos:
       - mdl_question_usages
       - mdl_quiz_attempts
       - mdl_question_attempts
       - mdl_question_attempt_steps
       - mdl_question_attempt_step_data
       - mdl_quiz_grades

    Retorna dict con {course_id: rows_affected}.
    """
    results = {}
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for cid in course_ids:
                # ── 1. Clonar grade_grades ──────────────────────────────
                sql_gg = f"""
                    INSERT INTO {table('grade_grades')} (
                        itemid, userid, rawgrade, finalgrade,
                        timecreated, timemodified,
                        information, feedback, feedbackformat,
                        aggregationstatus, aggregationweight,
                        excluded, locked, locktime, exported, overridden, hidden
                    )
                    SELECT
                        gg_src.itemid,
                        %s AS userid,
                        gg_src.rawgrade,
                        gg_src.finalgrade,
                        UNIX_TIMESTAMP() AS timecreated,
                        UNIX_TIMESTAMP() AS timemodified,
                        gg_src.information,
                        gg_src.feedback,
                        gg_src.feedbackformat,
                        gg_src.aggregationstatus,
                        gg_src.aggregationweight,
                        gg_src.excluded,
                        gg_src.locked,
                        gg_src.locktime,
                        gg_src.exported,
                        gg_src.overridden,
                        gg_src.hidden
                    FROM {table('grade_grades')} gg_src
                    JOIN {table('grade_items')} gi ON gg_src.itemid = gi.id
                    WHERE gg_src.userid = %s
                      AND gi.courseid = %s
                      AND gg_src.finalgrade IS NOT NULL
                    ON DUPLICATE KEY UPDATE
                        rawgrade = VALUES(rawgrade),
                        finalgrade = VALUES(finalgrade),
                        timemodified = UNIX_TIMESTAMP(),
                        information = VALUES(information),
                        feedback = VALUES(feedback),
                        feedbackformat = VALUES(feedbackformat),
                        aggregationstatus = VALUES(aggregationstatus),
                        aggregationweight = VALUES(aggregationweight),
                        excluded = VALUES(excluded),
                        locked = VALUES(locked),
                        locktime = VALUES(locktime),
                        exported = VALUES(exported),
                        overridden = VALUES(overridden),
                        hidden = VALUES(hidden)
                """
                cursor.execute(sql_gg, (dest_user_id, source_user_id, cid))
                rows = cursor.rowcount

                # ── 2. Clonar intentos de quiz ──────────────────────────
                # Obtener quizzes del curso
                quizzes = execute_query(f"""
                    SELECT id FROM {table('quiz')} WHERE course = %s
                """, (cid,))

                for quiz in quizzes:
                    qid = quiz['id']

                    # Mejor intento terminado del origen (mayor sumgrades)
                    best = None
                    cursor.execute(f"""
                        SELECT id, uniqueid, attempt, layout, sumgrades,
                               timestart, timefinish
                        FROM {table('quiz_attempts')}
                        WHERE quiz = %s AND userid = %s AND state = 'finished'
                        ORDER BY sumgrades DESC LIMIT 1
                    """, (qid, source_user_id))
                    best = cursor.fetchone()
                    if not best:
                        continue

                    src_usage_id = best['uniqueid']

                    # Eliminar intentos previos del destino en este quiz
                    # (limpiar datos viejos para no acumular)
                    cursor.execute(f"""
                        SELECT id, uniqueid FROM {table('quiz_attempts')}
                        WHERE quiz = %s AND userid = %s
                    """, (qid, dest_user_id))
                    old_attempts = cursor.fetchall()
                    for oa in old_attempts:
                        _delete_attempt_chain(cursor, oa['id'], oa['uniqueid'])

                    # Copiar question_usages
                    cursor.execute(f"""
                        SELECT contextid, component, preferredbehaviour
                        FROM {table('question_usages')} WHERE id = %s
                    """, (src_usage_id,))
                    src_usage = cursor.fetchone()
                    if not src_usage:
                        continue

                    cursor.execute(f"""
                        INSERT INTO {table('question_usages')}
                            (contextid, component, preferredbehaviour)
                        VALUES (%s, %s, %s)
                    """, (src_usage['contextid'], src_usage['component'],
                          src_usage['preferredbehaviour']))
                    new_usage_id = cursor.lastrowid

                    # Determinar número de intento para destino
                    cursor.execute(f"""
                        SELECT COALESCE(MAX(attempt), 0) + 1 AS next_att
                        FROM {table('quiz_attempts')}
                        WHERE quiz = %s AND userid = %s
                    """, (qid, dest_user_id))
                    next_att = cursor.fetchone()['next_att']

                    # Copiar quiz_attempts (fechas = momento actual, misma duración)
                    src_duration = (best['timefinish'] or 0) - (best['timestart'] or 0)
                    if src_duration < 0:
                        src_duration = 0
                    cursor.execute(f"""
                        INSERT INTO {table('quiz_attempts')}
                            (quiz, userid, attempt, uniqueid, layout,
                             currentpage, preview, state,
                             timestart, timefinish, timemodified,
                             timemodifiedoffline, timecheckstate, sumgrades,
                             gradednotificationsenttime)
                        VALUES (%s, %s, %s, %s, %s,
                                0, 0, 'finished',
                                UNIX_TIMESTAMP(), UNIX_TIMESTAMP() + %s, UNIX_TIMESTAMP(),
                                0, NULL, %s, NULL)
                    """, (qid, dest_user_id, next_att, new_usage_id,
                          best['layout'],
                          src_duration,
                          best['sumgrades']))

                    # Copiar question_attempts
                    cursor.execute(f"""
                        SELECT id, slot, behaviour, questionid, variant,
                               maxmark, minfraction, maxfraction, flagged,
                               questionsummary, rightanswer, responsesummary,
                               timemodified
                        FROM {table('question_attempts')}
                        WHERE questionusageid = %s ORDER BY slot
                    """, (src_usage_id,))
                    src_qas = cursor.fetchall()

                    for sqa in src_qas:
                        cursor.execute(f"""
                            INSERT INTO {table('question_attempts')}
                                (questionusageid, slot, behaviour, questionid,
                                 variant, maxmark, minfraction, maxfraction,
                                 flagged, questionsummary, rightanswer,
                                 responsesummary, timemodified)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                                    %s, %s, %s, %s, %s)
                        """, (new_usage_id, sqa['slot'], sqa['behaviour'],
                              sqa['questionid'], sqa['variant'], sqa['maxmark'],
                              sqa['minfraction'], sqa['maxfraction'],
                              sqa['flagged'], sqa['questionsummary'],
                              sqa['rightanswer'], sqa['responsesummary'],
                              sqa['timemodified']))
                        new_qa_id = cursor.lastrowid

                        # Copiar steps
                        cursor.execute(f"""
                            SELECT id, sequencenumber, state, fraction,
                                   timecreated
                            FROM {table('question_attempt_steps')}
                            WHERE questionattemptid = %s
                            ORDER BY sequencenumber
                        """, (sqa['id'],))
                        src_steps = cursor.fetchall()

                        for ss in src_steps:
                            cursor.execute(f"""
                                INSERT INTO {table('question_attempt_steps')}
                                    (questionattemptid, sequencenumber, state,
                                     fraction, timecreated, userid)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """, (new_qa_id, ss['sequencenumber'], ss['state'],
                                  ss['fraction'], ss['timecreated'],
                                  dest_user_id))
                            new_step_id = cursor.lastrowid

                            # Copiar step_data
                            cursor.execute(f"""
                                SELECT name, value
                                FROM {table('question_attempt_step_data')}
                                WHERE attemptstepid = %s
                            """, (ss['id'],))
                            src_sd = cursor.fetchall()
                            for sd in src_sd:
                                cursor.execute(f"""
                                    INSERT INTO {table('question_attempt_step_data')}
                                        (attemptstepid, name, value)
                                    VALUES (%s, %s, %s)
                                """, (new_step_id, sd['name'], sd['value']))

                    # Copiar/actualizar quiz_grades
                    cursor.execute(f"""
                        SELECT grade FROM {table('quiz_grades')}
                        WHERE quiz = %s AND userid = %s
                    """, (qid, source_user_id))
                    src_qg = cursor.fetchone()
                    if src_qg:
                        cursor.execute(f"""
                            INSERT INTO {table('quiz_grades')}
                                (quiz, userid, grade, timemodified)
                            VALUES (%s, %s, %s, UNIX_TIMESTAMP())
                            ON DUPLICATE KEY UPDATE
                                grade = VALUES(grade),
                                timemodified = UNIX_TIMESTAMP()
                        """, (qid, dest_user_id, src_qg['grade']))

                    rows += 1  # track quiz cloned

                results[cid] = rows
    finally:
        conn.close()

    return results


def _delete_attempt_chain(cursor, attempt_id, usage_id):
    """Elimina un intento de quiz completo: steps_data → steps → q_attempts → quiz_attempt → usage."""
    t = table
    # Obtener question_attempts del usage
    cursor.execute(f"""
        SELECT id FROM {t('question_attempts')} WHERE questionusageid = %s
    """, (usage_id,))
    qa_ids = [r['id'] for r in cursor.fetchall()]

    if qa_ids:
        ph = ','.join(['%s'] * len(qa_ids))
        # Obtener steps
        cursor.execute(f"""
            SELECT id FROM {t('question_attempt_steps')}
            WHERE questionattemptid IN ({ph})
        """, qa_ids)
        step_ids = [r['id'] for r in cursor.fetchall()]

        if step_ids:
            sph = ','.join(['%s'] * len(step_ids))
            # Borrar step_data
            cursor.execute(f"""
                DELETE FROM {t('question_attempt_step_data')}
                WHERE attemptstepid IN ({sph})
            """, step_ids)
            # Borrar steps
            cursor.execute(f"""
                DELETE FROM {t('question_attempt_steps')}
                WHERE id IN ({sph})
            """, step_ids)

        # Borrar question_attempts
        cursor.execute(f"""
            DELETE FROM {t('question_attempts')} WHERE id IN ({ph})
        """, qa_ids)

    # Borrar quiz_attempt
    cursor.execute(f"""
        DELETE FROM {t('quiz_attempts')} WHERE id = %s
    """, (attempt_id,))

    # Borrar question_usage
    cursor.execute(f"""
        DELETE FROM {t('question_usages')} WHERE id = %s
    """, (usage_id,))
