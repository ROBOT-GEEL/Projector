#!/bin/bash

# 1. Configuratie
ENV_FILE="/home/projector/Documents/.env"
HTML_FILE="file:///home/projector/Documents/browser/kiosk_master.html"
TMP_PROFILE="/tmp/chrome_kiosk"

# 2. Haal het IP uit de .env file
SERVER_IP=$(grep "^SERVER_IP=" "$ENV_FILE" | cut -d '=' -f 2 | tr -d ' \r')
echo "Gevonden IP uit .env: $SERVER_IP"

# 3. De Loop
while true; do
    echo "Chromium opstarten..."

    # Ruim het oude profiel op om 'Profile in use' lock-fouten te voorkomen
    rm -rf "$TMP_PROFILE"

    # Start Chromium
    /snap/bin/chromium \
        --kiosk \
        --no-sandbox \
        --incognito \
        --noerrdialogs \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-translate \
        --no-first-run \
        --disable-features=Translate,TranslateUI,LanguageDetectionAPI \
        --password-store=basic \
        --disable-save-password-bubble \
        --disable-notifications \
        --allow-file-access-from-files \
        --disable-web-security \
        --user-data-dir="$TMP_PROFILE" \
        "$HTML_FILE#$SERVER_IP"

    echo "Chromium is gestopt. Herstarten over 2 seconden..."
    sleep 2
done
