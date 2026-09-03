#!/usr/bin/env bash
#
# Устанавливает Docker (если нужно) и разворачивает 3x-ui на чистом
# Ubuntu/Debian сервере — «одна команда — готовая нода».
#
# Использование (от root, на НОВОМ сервере, который станет VPN-нодой):
#   scp install_node.sh root@<ip-новой-ноды>:~/
#   ssh root@<ip-новой-ноды>
#   bash install_node.sh
#
# После завершения впишите выведенные адрес/логин/пароль панели в разделе
# «⚙️ Админ-панель → 🌍 Серверы → ➕ Добавить ноду» бота — он сам залогинится
# на панель и создаст Reality-инбаунд.
#
# ⚠️ Команда `x-ui setting ...` ниже — официальный CLI самой панели x-ui/3x-ui
# для установки логина/пароля/порта, но флаги слегка отличались между
# версиями образа. Если шаг покажет ошибку — настройте вручную:
#   docker exec -it 3x-ui x-ui
# (интерактивное меню, пункты вида "Account settings" / "Panel settings").

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Запустите скрипт от root (или через sudo)." >&2
  exit 1
fi

# --------------------------------------------------------------------------- #
# Параметры
# --------------------------------------------------------------------------- #
PANEL_PORT="${PANEL_PORT:-2053}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 20)}"
XRAY_PORT="${XRAY_PORT:-}"

# Полностью неинтерактивный запуск (в обход read, если по какой-то причине
# интерактивный ввод/tty в вашей сессии ведёт себя не как ожидается):
#   NONINTERACTIVE=1 PANEL_PORT=2053 XRAY_PORT=443 bash install_node.sh
if [[ "${NONINTERACTIVE:-0}" != "1" ]]; then
  echo "== Параметры установки (Enter — принять значение по умолчанию в []) =="

  read -rp "Порт панели [$PANEL_PORT]: " input_port </dev/tty
  PANEL_PORT="${input_port:-$PANEL_PORT}"

  if [[ -z "$XRAY_PORT" ]]; then
    read -rp "Порт VLESS/Reality на этой ноде (укажете тот же в боте), например 443: " XRAY_PORT </dev/tty
  fi
fi

if [[ -z "${XRAY_PORT:-}" ]]; then
  echo "Порт VLESS обязателен. Передайте его через XRAY_PORT=443 (см. подсказку выше)." >&2
  exit 1
fi

echo "Параметры приняты: PANEL_PORT=${PANEL_PORT}, XRAY_PORT=${XRAY_PORT}"

echo
echo "Панель:  порт ${PANEL_PORT}, логин ${ADMIN_USER}, пароль ${ADMIN_PASS}"
echo "VLESS:   порт ${XRAY_PORT}"
echo

# --------------------------------------------------------------------------- #
# Docker
# --------------------------------------------------------------------------- #
if ! command -v docker &>/dev/null; then
  echo "== Устанавливаю Docker =="
  curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version &>/dev/null; then
  echo "Docker Compose plugin не найден — установите docker-compose-plugin и запустите скрипт снова." >&2
  exit 1
fi

# --------------------------------------------------------------------------- #
# Файлы ноды
# --------------------------------------------------------------------------- #
INSTALL_DIR="/opt/3x-ui"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

cat > docker-compose.yml << EOF
services:
  xui:
    image: ghcr.io/mhsanaei/3x-ui:latest
    container_name: 3x-ui
    restart: unless-stopped
    network_mode: host
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - 3x-ui-db:/etc/x-ui
      - 3x-ui-cert:/root/cert

volumes:
  3x-ui-db:
  3x-ui-cert:
EOF

echo "== Поднимаю контейнер 3x-ui =="
docker compose up -d

echo "Жду запуска панели..."
sleep 8

echo "== Настраиваю логин/пароль/порт панели =="
if ! docker exec 3x-ui x-ui setting -username "$ADMIN_USER" -password "$ADMIN_PASS" -port "$PANEL_PORT"; then
  echo
  echo "⚠️  Не получилось настроить автоматически — настройте вручную:"
  echo "    docker exec -it 3x-ui x-ui"
  echo
fi

docker restart 3x-ui >/dev/null
sleep 3

# --------------------------------------------------------------------------- #
# Firewall
# --------------------------------------------------------------------------- #
if command -v ufw &>/dev/null; then
  echo "== Настраиваю ufw =="
  ufw allow OpenSSH >/dev/null || true
  ufw allow "${PANEL_PORT}/tcp" >/dev/null || true
  ufw allow "${XRAY_PORT}/tcp" >/dev/null || true
  ufw allow "${XRAY_PORT}/udp" >/dev/null || true
  yes | ufw enable >/dev/null || true
else
  echo "ufw не найден — откройте порты ${PANEL_PORT} (панель) и ${XRAY_PORT} (VLESS) вручную в firewall/security group облака."
fi

# --------------------------------------------------------------------------- #
# TCP BBR — обычно немного улучшает пропускную способность для VPN-трафика
# --------------------------------------------------------------------------- #
if ! sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep -q bbr; then
  echo "== Включаю TCP BBR =="
  grep -qxF 'net.core.default_qdisc=fq' /etc/sysctl.conf 2>/dev/null \
    || echo 'net.core.default_qdisc=fq' >> /etc/sysctl.conf
  grep -qxF 'net.ipv4.tcp_congestion_control=bbr' /etc/sysctl.conf 2>/dev/null \
    || echo 'net.ipv4.tcp_congestion_control=bbr' >> /etc/sysctl.conf
  sysctl -p >/dev/null || true
fi

PUBLIC_IP="$(curl -fsSL -4 ifconfig.me || echo '<IP-этого-сервера>')"

cat << SUMMARY

========================================================================
Готово!

  Панель:             https://${PUBLIC_IP}:${PANEL_PORT}
  Логин:               ${ADMIN_USER}
  Пароль:              ${ADMIN_PASS}
  Порт VLESS/Reality:  ${XRAY_PORT}

Дальше — в Telegram-боте: ⚙️ Админ-панель → 🌍 Серверы → ➕ Добавить ноду.
Укажите адрес этого сервера (${PUBLIC_IP}), порт ${XRAY_PORT} и данные
панели выше — бот сам создаст Reality-инбаунд и раздаст ноду всем, у кого
уже есть активная подписка.

⚠️ Панель сейчас на самоподписанном сертификате — это нормально для
админского доступа, но сохраните логин/пароль в надёжном месте и по
возможности ограничьте доступ к порту ${PANEL_PORT} по IP в firewall облака.
========================================================================
SUMMARY
