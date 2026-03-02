"""Servicio de envío de correos electrónicos."""
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import Config


def send_email(to_email, subject, html_body, to_name=''):
    """Envía un correo electrónico individual.
    
    Args:
        to_email: Dirección de correo del destinatario
        subject: Asunto del correo
        html_body: Contenido HTML del correo
        to_name: Nombre del destinatario (opcional)
    
    Returns:
        True si se envió correctamente, False si hubo error
    """
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"Gestión Moodle <{Config.MAIL_USERNAME}>"
        msg['To'] = f"{to_name} <{to_email}>" if to_name else to_email
        
        html_part = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(html_part)
        
        with smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT) as server:
            server.ehlo()
            if Config.MAIL_USE_TLS:
                server.starttls()
                server.ehlo()
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.sendmail(Config.MAIL_USERNAME, to_email, msg.as_string())
        
        return True
    except Exception as e:
        print(f"[ERROR] Error enviando correo a {to_email}: {e}")
        return False


def send_bulk_email(recipients, subject, html_template, variables_list):
    """Envía correos masivos respetando el límite de lote.
    
    Args:
        recipients: Lista de dicts con keys: email, name
        subject: Asunto del correo
        html_template: Template HTML con placeholders {nombre}, {curso}, etc.
        variables_list: Lista de dicts con variables para cada destinatario
    
    Returns:
        Tupla (exitosos, fallidos)
    """
    max_bulk = Config.MAIL_MAX_BULK
    success = 0
    failed = 0
    
    for i, (recipient, variables) in enumerate(zip(recipients, variables_list)):
        # Reemplazar variables en el template (soporta {var} y [:var:])
        body = _replace_vars(html_template, variables)
        
        if send_email(recipient['email'], subject, body, recipient.get('name', '')):
            success += 1
        else:
            failed += 1
        
        # Pausa entre lotes configurable
        if (i + 1) % max_bulk == 0 and i + 1 < len(recipients):
            time.sleep(Config.MAIL_BULK_PAUSE_SECONDS)
    
    return success, failed



import json
import os

# file that persistently stores customizable templates
TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'email_templates.json')


def _ensure_template_file():
    """Ensure the template file exists and contains the default welcome
    template.  Only creates the welcome entry when the file is brand new
    or when the 'welcome' key is completely absent.  User edits are
    **never** overwritten.
    """
    # canonical default welcome template
    default_welcome = {
        'subject': 'Bienvenido al curso: {curso}',
        'body': """
<div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 0 auto;">
    <div style="background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 30px; text-align: center;">
        <h1 style="color: #f98012; margin: 0;">Gestión Moodle</h1>
        <p style="color: rgba(255,255,255,0.7); margin: 5px 0 0;">Clínica de la Presentación</p>
    </div>
    <div style="padding: 40px; background: #fff; border: 1px solid #e0e0e0;">
        <h2 style="color: #1a1a2e;">¡Bienvenido/a, {nombre}!</h2>
        <p>Desde el área de Seguridad y Salud en el Trabajo ({categoryname}) te damos la bienvenida al curso <strong>{curso}</strong>, al cual has sido matriculado a través de la plataforma Moodle.</p>
        <p>A continuación, te brindamos toda la información para el ingreso:</p>
        <ul>
            <li>Enlace a la plataforma: <a href="{url_moodle}">{url_moodle}</a></li>
            <li>Usuario: tu número de identificación</li>
            <li>Contraseña: tu número de identificación</li>
        </ul>
        <p>Por tu seguridad, te recomendamos que al ingresar a la plataforma realices el cambio de la contraseña.</p>
        <p>Adicional te invitamos a dar un recorrido por la plataforma de aprendizaje para que te familiarices con la interfaz y los contenidos.</p>
        <p>El acceso al curso podrás realizarlo desde la pestaña “Mis cursos”, donde encontrarás el contenido de la capacitación junto a material de apoyo que te ayudará a ampliar tus conocimientos. Al finalizar su estudio deberás presentar la evaluación, que una vez cumplida de manera exitosa, te permitirá descargar el certificado.</p>
        <p>En caso de tener algún problema técnico o dudas con el manejo de la plataforma podrás dirigirte al área de sistemas.</p>
        <div style="text-align: center; margin-top: 30px;">
            <a href="{url_moodle}" style="background: #f98012; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                Acceder a Moodle
            </a>
        </div>
    </div>
    <div style="padding: 15px; text-align: center; color: #999; font-size: 12px;">
        <p>Este correo fue enviado automáticamente. No responda a este mensaje.</p>
    </div>
</div>
"""
    }

    # if file doesn't exist create with welcome
    if not os.path.exists(TEMPLATE_FILE):
        os.makedirs(os.path.dirname(TEMPLATE_FILE), exist_ok=True)
        with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'welcome': default_welcome}, f, indent=2, ensure_ascii=False)
        return

    # only add welcome if it was deleted; never overwrite user edits
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if 'welcome' not in data:
        data['welcome'] = default_welcome
        with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # one-time migration: replace [:var:] → {var} in all templates
    _migrate_bracket_syntax(data)


import re as _re

_BRACKET_RE = _re.compile(r'\[:([a-zA-Z_]+):]')


def _migrate_bracket_syntax(data):
    """Replace ``[:var:]`` → ``{var}`` in all template subjects/bodies."""
    changed = False
    for name, tpl in data.items():
        for field in ('subject', 'body'):
            original = tpl.get(field, '')
            migrated = _BRACKET_RE.sub(r'{\1}', original)
            if migrated != original:
                tpl[field] = migrated
                changed = True
    if changed:
        with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def _load_templates():
    _ensure_template_file()
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_email_templates():
    """Devuelve un diccionario con nombre->{subject,body}."""
    return _load_templates()


def get_email_template(name):
    return _load_templates().get(name)


def add_or_update_email_template(name, subject, body):
    templates = _load_templates()
    templates[name] = {'subject': subject, 'body': body}
    with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(templates, f, indent=2, ensure_ascii=False)


def delete_email_template(name):
    templates = _load_templates()
    if name in templates:
        templates.pop(name)
        with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(templates, f, indent=2, ensure_ascii=False)


def _replace_vars(text, variables):
    """Replace ``{key}`` **and** ``[:key:]`` placeholders in *text*."""
    for key, value in variables.items():
        val = str(value)
        text = text.replace(f'{{{key}}}', val)
        text = text.replace(f'[:{key}:]', val)
    return text


def render_email_template(template_name, **variables):
    """Renderiza una plantilla de correo con variables.

    El cuerpo y el asunto se almacenan en el archivo JSON definido en
    ``TEMPLATE_FILE``.  Acepta marcadores ``{variable}`` y también la
    sintaxis heredada ``[:variable:]``.
    """
    tpl = get_email_template(template_name) or {}
    body = _replace_vars(tpl.get('body', ''), variables)
    return body
