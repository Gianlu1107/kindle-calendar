#!/usr/bin/env bash
# ==============================================================================
# Kindle Calendar Dashboard - Automated Server Setup Script (Debian / Ubuntu)
# ==============================================================================
set -e

echo "=== Installazione Kindle Calendar Server ==="

# Verifica root
if [ "$EUID" -ne 0 ]; then
  echo "[-] Esegui questo script come root (sudo ./setup.sh)"
  exit 1
fi

BASE_DIR="/opt/kindleCalendar"

# 1. Dipendenze di sistema
echo "[+] Installazione dipendenze di sistema apt..."
apt-get update -y
apt-get install -y python3 python3-venv imagemagick curl git postgresql postgresql-contrib libpq-dev

# 2. Setup directory
mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

# 3. Virtualenv Python & Playwright
if [ ! -d "$BASE_DIR/venv" ]; then
    echo "[+] Creazione Python virtual environment..."
    python3 -m venv "$BASE_DIR/venv"
fi

echo "[+] Installazione pacchetti Python..."
"$BASE_DIR/venv/bin/pip" install --upgrade pip
"$BASE_DIR/venv/bin/pip" install -r "$BASE_DIR/requirements.txt"

echo "[+] Installazione browser Chromium e librerie per Playwright..."
"$BASE_DIR/venv/bin/playwright" install chromium
"$BASE_DIR/venv/bin/playwright" install-deps chromium

# 4. Configurazione .env se assente
if [ ! -f "$BASE_DIR/.env" ] && [ -f "$BASE_DIR/.env.example" ]; then
    echo "[+] Copia configurazione .env.example -> .env..."
    cp "$BASE_DIR/.env.example" "$BASE_DIR/.env"
    echo "[!] Ricordati di configurare $BASE_DIR/.env con i tuoi parametri!"
fi

# 4b. Inizializzazione Database PostgreSQL
echo "[+] Inizializzazione PostgreSQL..."
systemctl enable --now postgresql || true
su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname = 'kindle_calendar'\" | grep -q 1 || psql -c \"CREATE DATABASE kindle_calendar;\"" || true
"$BASE_DIR/venv/bin/python" "$BASE_DIR/db.py" || true

# 5. Servizi systemd
if [ -d "$BASE_DIR/systemd" ]; then
    echo "[+] Configurazione servizi systemd..."
    cp "$BASE_DIR/systemd/kindle-server.service" /etc/systemd/system/
    cp "$BASE_DIR/systemd/kindle-renderer.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now kindle-server.service
    systemctl enable --now kindle-renderer.service
    echo "[+] Servizi kindle-server e kindle-renderer avviati con successo!"
fi

echo "=== Installazione completata! Dashboard attiva su porta 5055 ==="
