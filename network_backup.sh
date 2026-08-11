#!/bin/bash

echo "-----" >> /home/projector/Documents/network_backup_log.txt
echo "Uitgevoerd op $(date)" >> /home/projector/Documents/network_backup_log.txt

# Controleer of het script als root (sudo) wordt uitgevoerd
if [ "$EUID" -ne 0 ]; then
  echo "Fout: Dit script moet met root-rechten worden uitgevoerd. Gebruik 'sudo ./setup_network.sh'"
  exit 1
fi

# Variabelen
WIFI_SSID="Robotoo"
WIFI_PASS="d2aQy34sjF67!"
WIFI_IFACE="wlP1p1s0"
IPPingDevice1="172.18.108.12" #Robot
IPPingDevice2="172.18.108.11" #Pi

#Om de 2 seconden wordt een pakketje verstuurd dat beantwoord moet worden binnen de 3 seconden. 
#Als er mistens 1 pakketje beantwoord terugkomt is de functie true
#Na 5 onbeantwoorde pakketjes wordt false geretourneerd
if ping -c 40 -i 5 -W 3 "$IPPingDevice1" &> /dev/null; then
	echo "Robot geconnecteerd" >> /home/projector/Documents/network_backup_log.txt
	exit 0
fi

if ping -c 40 -i 3 -W 3 "$IPPingDevice2" &> /dev/null; then
	echo "PI geconnecteerd" >> /home/projector/Documents/network_backup_log.txt
	exit 0
fi

echo "Geen device geconnecteerd, backupprocedure" >> /home/projector/Documents/network_backup_log.txt

# --- 0. Bestandsrechten herstellen ---
echo "Bestandsrechten van netwerkprofielen herstellen..."
chmod 600 /etc/NetworkManager/system-connections/*.nmconnection || true # Voorkom crash als map leeg is

# --- 1. Robotoo (Wi-Fi) instellingen ---
echo "Controleer Wi-Fi profiel: $WIFI_SSID..."
while nmcli connection show "$WIFI_SSID" > /dev/null 2>&1; do
    echo "bestaand '$WIFI_SSID' profiel gevonden, verwijderen..."
    nmcli connection delete "$WIFI_SSID"
done

echo "Nieuw profiel aanmaken"
nmcli connection add type wifi con-name "$WIFI_SSID" ifname "$WIFI_IFACE" ssid "$WIFI_SSID"

echo "Wi-Fi instellingen toepassen..."
nmcli connection modify "$WIFI_SSID" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    connection.autoconnect-retries 0 \
    ipv4.may-fail no \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$WIFI_PASS" \
    ipv4.route-metric 50

# --- 2. Power save (Globale instelling) uitschakelen ---
echo "Wi-Fi energiebesparing uitschakelen..."
WIFI_POWERSAVE_CONF="/etc/NetworkManager/conf.d/default-wifi-powersave-on.conf"
if [ -f "$WIFI_POWERSAVE_CONF" ]; then
    # Vervang 'wifi.powersave = 3' door 'wifi.powersave = 2'
    sed -i 's/wifi.powersave = [0-9]\+/wifi.powersave = 2/g' "$WIFI_POWERSAVE_CONF"
else
    echo "Waarschuwing: $WIFI_POWERSAVE_CONF niet gevonden. Handmatige configuratie mogelijk nodig."
fi

# --- 3. Connectivity check (20000 penalty) uitschakelen ---
echo "Connectivity check uitschakelen in NetworkManager.conf..."
NM_CONF="/etc/NetworkManager/NetworkManager.conf"
if ! grep -q "^\[connectivity\]" "$NM_CONF"; then
    echo -e "\n[connectivity]\nenabled=false" >> "$NM_CONF"
elif ! grep -q "^enabled=false" "$NM_CONF"; then
    # Als [connectivity] bestaat verwijder de regels en voeg enable = true toe
    sed -i '/^\[connectivity\]/,/^\[/{/^enabled=/d}' "$NM_CONF"
    sed -i '/^\[connectivity\]/a enabled=false' "$NM_CONF"
fi

# --- 4. Bestandsrechten herstellen ---
echo "Bestandsrechten van netwerkprofielen herstellen..."
chmod 600 /etc/NetworkManager/system-connections/*.nmconnection || true # Voorkom crash als map leeg is


# --- 5. Service herstarten en verbindingen activeren ---
echo "NetworkManager herstarten..."
systemctl restart NetworkManager

# Geef NetworkManager tijd om op te starten en interfaces te detecteren
sleep 10

echo "Verbindingen activeren..."
nmcli connection up "$WIFI_SSID" || echo "Let op: Kon Wi-Fi niet activeren. Controleer interface of bereik."

echo "=== Netwerkconfiguratie succesvol afgerond! ==="

