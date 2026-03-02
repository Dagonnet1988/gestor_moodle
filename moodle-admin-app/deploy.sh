#!/usr/bin/env bash
# ============================================================
# deploy.sh — Script de despliegue para Gestor Moodle
# Ejecutar en el servidor Ubuntu 24.04 (192.162.2.34)
# Uso:  chmod +x deploy.sh && sudo ./deploy.sh
# ============================================================
set -e

APP_NAME="gestor-moodle"
REPO_DIR="/opt/${APP_NAME}"
APP_DIR="${REPO_DIR}/moodle-admin-app"
APP_USER="gestormoodle"
REPO_URL="https://github.com/Dagonnet1988/gestor_moodle.git"
BRANCH="main"

echo "=========================================="
echo "  Desplegando ${APP_NAME}"
echo "=========================================="

# 1. Instalar dependencias del sistema
echo "[1/7] Instalando dependencias del sistema..."
apt update -qq
apt install -y python3 python3-venv python3-pip nginx git

# 2. Crear usuario de servicio (sin login)
if ! id "${APP_USER}" &>/dev/null; then
    echo "[2/7] Creando usuario ${APP_USER}..."
    useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_USER}"
else
    echo "[2/7] Usuario ${APP_USER} ya existe."
fi

# 3. Clonar o actualizar repositorio
if [ -d "${REPO_DIR}" ]; then
    echo "[3/7] Actualizando repositorio..."
    cd "${REPO_DIR}"
    git fetch origin
    git reset --hard "origin/${BRANCH}"
else
    echo "[3/7] Clonando repositorio..."
    git clone -b "${BRANCH}" "${REPO_URL}" "${REPO_DIR}"
    cd "${REPO_DIR}"
fi

# 4. Crear entorno virtual e instalar dependencias
echo "[4/7] Configurando entorno virtual..."
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
"${APP_DIR}/venv/bin/pip" install gunicorn

# 5. Configurar .env (si no existe, copiar plantilla)
if [ ! -f "${APP_DIR}/.env" ]; then
    echo "[5/7] Copiando .env.production → .env  (¡EDITAR CONTRASEÑAS!)"
    cp "${APP_DIR}/.env.production" "${APP_DIR}/.env"
    echo "  >>> IMPORTANTE: edita ${APP_DIR}/.env con las contraseñas reales"
else
    echo "[5/7] .env ya existe, no se sobreescribe."
fi

# 6. Ajustar permisos
echo "[6/7] Ajustando permisos..."
mkdir -p /var/log/gestor-moodle
chown -R "${APP_USER}:${APP_USER}" "${REPO_DIR}"
chown -R "${APP_USER}:${APP_USER}" /var/log/gestor-moodle
chmod 600 "${APP_DIR}/.env"

# 7. Instalar y activar servicios
echo "[7/7] Configurando systemd y nginx..."

# Copiar archivos de configuración
cp "${APP_DIR}/deploy/gestor-moodle.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/gestor-moodle-nginx.conf" /etc/nginx/sites-available/${APP_NAME}

# Habilitar sitio nginx
ln -sf /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/${APP_NAME}
# Desactivar default si existe
rm -f /etc/nginx/sites-enabled/default

# Recargar servicios
systemctl daemon-reload
systemctl enable ${APP_NAME}
systemctl restart ${APP_NAME}
nginx -t && systemctl restart nginx

echo ""
echo "=========================================="
echo "  ✓ Despliegue completado"
echo "=========================================="
echo "  App:    http://192.162.2.34/moodle"
echo "  Estado: systemctl status ${APP_NAME}"
echo "  Logs:   journalctl -u ${APP_NAME} -f"
echo ""
echo "  ⚠ Recuerda editar ${APP_DIR}/.env con las"
echo "    contraseñas reales antes del primer uso."
echo "=========================================="
