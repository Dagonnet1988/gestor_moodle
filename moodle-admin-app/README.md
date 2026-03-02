# Gestor Moodle

Pequeña aplicación web en Flask para gestionar usuarios, inscripciones, calificaciones y correos
sobre una instalación de Moodle existente.

## Instalación

1. Crear un entorno virtual Python (recomendado `venv`).
2. Activar el entorno y ejecutar:
   ```bash
   pip install -r requirements.txt
   ```
3. Crear un archivo `.env` en la raíz de `moodle-admin-app` con las credenciales de la BD
   y SMTP. Ejemplo:
   ```ini
   DB_HOST=192.168.1.212
   DB_PORT=3306
   DB_NAME=moodle
   DB_USER=moodle
   DB_PASS=secret
   DB_PREFIX=mdl_

   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=clinicaestudia@clinicadelapresentacion.com.co
   SMTP_PASS=app_password_here
   SMTP_MAX_BULK=10
   SMTP_BULK_PAUSE=5

   MOODLE_URL=http://190.71.122.76/moodle

   FLASK_DEBUG=true
   SECRET_KEY=change-this
   ```

4. Ejecutar la aplicación de desarrollo:
   ```bash
   python run.py
   ```
   Acceder en `http://localhost:5000`.

## Pruebas unitarias

Se utiliza `pytest` para validación. Algunas pruebas requieren acceso a la base de
Moodle real; se omiten automáticamente si la conexión no está disponible.

Variables de entorno opcionales para pruebas con autenticación real:
```bash
export TEST_USER=admin
export TEST_PASS=admin123
```

Para ejecutar todas las pruebas:
```bash
cd moodle-admin-app
pytest
```


## Estructura básica

- `app/` – código fuente de la app
- `app/routes` – blueprints de Flask
- `app/services` – lógica de negocio y accesos a BD/SMTP
- `app/templates` – vistas Jinja2
- `tests/` – casos de prueba

## Funcionalidades implementadas

- Autenticación contra Moodle (roles no estudiantiles)
- CRUD de usuarios (identificación igual al nombre de usuario, campo sincronizado)
- Listado de cursos e inscripciones
- Formularios de usuario simplificados: solo país, ciudad y teléfono principal
- Inscripción individual y masiva (CSV)
- Envío de correos con plantillas y cola masiva paramétrica
- Dashboard con estadísticas y logs de actividad
- Registro/auditoría en tabla `app_action_log`

## Siguientes pasos

- Extender módulos según plan original (envío masivo desde UI, reenvíos, etc.)
- Despliegue con Gunicorn/Waitress
- Expansión de pruebas y documentación adicional

---

_Proyecto generado por GitHub Copilot en colaboración con el desarrollador._
