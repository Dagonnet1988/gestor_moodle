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
        # Reemplazar variables en el template
        body = html_template
        for key, value in variables.items():
            body = body.replace(f'{{{key}}}', str(value))
        
        if send_email(recipient['email'], subject, body, recipient.get('name', '')):
            success += 1
        else:
            failed += 1
        
        # Pausa entre lotes
        if (i + 1) % max_bulk == 0 and i + 1 < len(recipients):
            time.sleep(5)  # 5 segundos de pausa entre lotes
    
    return success, failed


def render_email_template(template_name, **variables):
    """Renderiza una plantilla de correo con variables.
    
    Plantillas disponibles:
        - welcome: Correo de bienvenida al inscribir en curso
        - reminder: Recordatorio para acceder al curso
    """
    templates = {
        'welcome': """
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 30px; text-align: center;">
                <h1 style="color: #f98012; margin: 0;">Gestión Moodle</h1>
                <p style="color: rgba(255,255,255,0.7); margin: 5px 0 0;">Clínica de la Presentación</p>
            </div>
            <div style="padding: 30px; background: #fff; border: 1px solid #e0e0e0;">
                <h2 style="color: #1a1a2e;">¡Bienvenido/a, {nombre}!</h2>
                <p>Ha sido inscrito/a en el curso: <strong>{curso}</strong></p>
                <p>Puede acceder a la plataforma Moodle con los siguientes datos:</p>
                <div style="background: #f4f6f9; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>URL:</strong> <a href="{url_moodle}">{url_moodle}</a></p>
                    <p style="margin: 5px 0;"><strong>Usuario:</strong> {username}</p>
                    <p style="margin: 5px 0;"><strong>Contraseña:</strong> La que le fue asignada al crear su cuenta</p>
                </div>
                <p>Si tiene alguna dificultad para acceder, contacte al administrador.</p>
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
        """,
        'reminder': """
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 30px; text-align: center;">
                <h1 style="color: #f98012; margin: 0;">Gestión Moodle</h1>
                <p style="color: rgba(255,255,255,0.7); margin: 5px 0 0;">Clínica de la Presentación</p>
            </div>
            <div style="padding: 30px; background: #fff; border: 1px solid #e0e0e0;">
                <h2 style="color: #1a1a2e;">Recordatorio - {curso}</h2>
                <p>Estimado/a <strong>{nombre}</strong>,</p>
                <p>Le recordamos que tiene pendiente acceder al curso: <strong>{curso}</strong></p>
                <p>Es importante que ingrese a la plataforma y complete las actividades asignadas.</p>
                <div style="background: #f4f6f9; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Plataforma:</strong> <a href="{url_moodle}">{url_moodle}</a></p>
                    <p style="margin: 5px 0;"><strong>Su usuario:</strong> {username}</p>
                </div>
                <div style="text-align: center; margin-top: 30px;">
                    <a href="{url_moodle}" style="background: #f98012; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                        Ir al Curso
                    </a>
                </div>
            </div>
            <div style="padding: 15px; text-align: center; color: #999; font-size: 12px;">
                <p>Este correo fue enviado automáticamente. No responda a este mensaje.</p>
            </div>
        </div>
        """
    }
    
    template = templates.get(template_name, '')
    for key, value in variables.items():
        template = template.replace(f'{{{key}}}', str(value))
    
    return template
