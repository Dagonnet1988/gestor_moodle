import bcrypt
from app.services.db import execute_query, table


def verify_moodle_password(plain_password, hashed_password):
    """Verifica una contraseña contra el hash bcrypt de Moodle.
    
    Moodle almacena contraseñas con bcrypt (prefijo $2y$).
    Python bcrypt usa $2b$, así que se reemplaza el prefijo.
    """
    # Moodle usa $2y$ pero Python bcrypt espera $2b$
    if hashed_password.startswith('$2y$'):
        hashed_password = '$2b$' + hashed_password[4:]
    
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def get_user_by_username(username):
    """Obtiene un usuario de Moodle por su username."""
    query = f"""
        SELECT id, username, password, firstname, lastname, email, 
               suspended, confirmed, auth
        FROM {table('user')}
        WHERE username = %s AND deleted = 0
    """
    return execute_query(query, (username,), fetchone=True)


def get_role_label(shortname):
    """Convierte el shortname de Moodle a una etiqueta en español."""
    labels = {
        'manager': 'Administrador',
        'coursecreator': 'Creador de cursos',
        'editingteacher': 'Docente con edición',
        'teacher': 'Docente',
        'student': 'Estudiante',
        'guest': 'Invitado'
    }
    return labels.get(shortname, shortname)


def get_user_roles(user_id):
    """Obtiene los roles de un usuario en Moodle.
    
    Retorna una lista de diccionarios con los roles asignados; además
    agrega la etiqueta en español bajo la clave 'label'.
    """
    query = f"""
        SELECT DISTINCT r.id as role_id, r.shortname, r.name
        FROM {table('role_assignments')} ra
        JOIN {table('role')} r ON r.id = ra.roleid
        WHERE ra.userid = %s
    """
    roles = execute_query(query, (user_id,))
    for r in roles:
        r['label'] = get_role_label(r['shortname'])
    return roles


def get_user_top_roles(user_id, n=2):
    """Devuelve los n roles de mayor jerarquía (menor role_id) para el usuario."""
    roles = get_user_roles(user_id)
    # excluir invitados y estudiantes si hay otros disponibles
    non_std = [r for r in roles if r['shortname'] not in ('student','guest')]
    sel = non_std or roles
    sel.sort(key=lambda r: r['role_id'])
    return sel[:n]


def is_non_student(user_id):
    """Verifica si el usuario tiene al menos un rol diferente a estudiante.
    
    Retorna True si tiene un rol que NO sea student (roleid != 5) ni guest (roleid != 6).
    """
    roles = get_user_roles(user_id)
    for role in roles:
        if role['shortname'] not in ('student', 'guest'):
            return True
    return False


def get_user_highest_role(user_id):
    """Obtiene el rol más alto del usuario (menor ID = mayor privilegio)."""
    roles = get_user_roles(user_id)
    non_student_roles = [r for r in roles if r['shortname'] not in ('student', 'guest')]
    if not non_student_roles:
        return None
    # Ordenar por role_id (menor = más privilegio)
    non_student_roles.sort(key=lambda r: r['role_id'])
    return non_student_roles[0]


def authenticate_user(username, password):
    """Autentica un usuario con credenciales de Moodle.
    
    Retorna:
        - dict con datos del usuario si la autenticación es exitosa
        - None si falla
        - Lanza ValueError con mensaje descriptivo si hay error
    """
    # 1. Buscar usuario
    user = get_user_by_username(username)
    if not user:
        raise ValueError('Usuario no encontrado')
    
    # 2. Verificar que no esté suspendido
    if user['suspended']:
        raise ValueError('Usuario suspendido. Contacte al administrador')
    
    # 3. Verificar contraseña
    if not verify_moodle_password(password, user['password']):
        raise ValueError('Contraseña incorrecta')
    
    # 4. Verificar que tenga rol diferente a estudiante
    if not is_non_student(user['id']):
        raise ValueError('Acceso denegado. Solo usuarios con rol administrativo o docente pueden acceder')
    
    # 5. Obtener los dos roles más altos
    top_roles = get_user_top_roles(user['id'], n=2)
    primary = top_roles[0] if top_roles else None
    role_list = [r['shortname'] for r in top_roles]
    role_names = [r['label'] for r in top_roles]
    
    return {
        'id': user['id'],
        'username': user['username'],
        'firstname': user['firstname'],
        'lastname': user['lastname'],
        'email': user['email'],
        'roles': role_list,            # lista de shortnames
        'role': primary['shortname'] if primary else 'unknown',
        'role_name': ", ".join(role_names) if role_names else 'Desconocido'
    }
