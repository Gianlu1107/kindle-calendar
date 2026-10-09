#!/bin/sh
# ==============================================================================
# Kindle 4 (D01100) Client Daemon - Atomic Kiosk & Screen Controller
# Supports:
#   - Atomic minute synchronization (:00)
#   - Screen stay-alive (preventScreenSaver)
#   - Complete lock of physical buttons (chmod 000 /dev/input/event*)
#   - Permanent suppression of Amazon reader framework & "pagina 1 di 1" UI
#   - Automatic background NTP time synchronization
#   - FBInk native rendering for 600x800 e-paper
#   - Anti-ghosting cleaning cycle every 30 minutes
# ==============================================================================

export TZ='CET-1CEST,M3.5.0,M10.5.0/3'

SERVER_BASE="http://192.168.1.250:5055/api/image"
FBINK="/mnt/us/usbnet/bin/fbink"
TMP_IMG="/tmp/dashboard_k4.png"

# Ferma la UI nativa di Amazon (evita reader, booklet e la scritta "pagina 1 di 1")
/sbin/stop framework 2>/dev/null
/sbin/stop pillow 2>/dev/null
/etc/init.d/framework stop 2>/dev/null

# Disabilita completamente i tasti fisici (power, page-turn, 5-way d-pad, volume)
chmod 000 /dev/input/event0 /dev/input/event1 /dev/input/event2 2>/dev/null

# Disabilita screensaver e timeout di sospensione
lipc-set-prop -i com.lab126.powerd preventScreenSaver 1 2>/dev/null

echo "=== KINDLE 4 KIOSK CLIENT ATTIVO ==="

# Sincronizzazione oraria NTP iniziale
ntpdate -u pool.ntp.org >/dev/null 2>&1 || ntpdate -u 192.168.1.250 >/dev/null 2>&1

# Lettura batteria
BATT=$(gasgauge-info -s 2>/dev/null | tr -d '%')
[ -z "$BATT" ] && BATT=$(cat /sys/class/power_supply/max77696-battery/capacity 2>/dev/null)
[ -z "$BATT" ] && BATT=$(lipc-get-prop -i com.lab126.powerd battLevel 2>/dev/null)
[ -z "$BATT" ] && BATT=100

CHG=$(lipc-get-prop -i com.lab126.powerd isCharging 2>/dev/null)
[ -z "$CHG" ] && CHG=0

curl -s -f -m 6 "${SERVER_BASE}?device=k4&batt=${BATT}&charging=${CHG}" -o "$TMP_IMG" && \
    $FBINK -q -c -f -g file="$TMP_IMG" 2>/dev/null

CYCLE=0
while true; do
    # Attendi fino allo scattare esatto del secondo :00
    NOW=$(date +%s)
    SEC=$((NOW % 60))
    SLEEP_SEC=$((60 - SEC))
    [ "$SLEEP_SEC" -le 0 ] && SLEEP_SEC=60

    sleep "$SLEEP_SEC"

    CYCLE=$((CYCLE + 1))
    if [ "$CYCLE" -ge 60 ]; then
        CYCLE=0
        (ntpdate -u pool.ntp.org >/dev/null 2>&1 || ntpdate -u 192.168.1.250 >/dev/null 2>&1) &
    fi

    # Rinforza sempre la disattivazione screensaver e blocco tasti fisici
    lipc-set-prop -i com.lab126.powerd preventScreenSaver 1 2>/dev/null
    chmod 000 /dev/input/event0 /dev/input/event1 /dev/input/event2 2>/dev/null

    # Lettura percentuale batteria
    BATT=$(gasgauge-info -s 2>/dev/null | tr -d '%')
    [ -z "$BATT" ] && BATT=$(cat /sys/class/power_supply/max77696-battery/capacity 2>/dev/null)
    [ -z "$BATT" ] && BATT=$(lipc-get-prop -i com.lab126.powerd battLevel 2>/dev/null)
    [ -z "$BATT" ] && BATT=100

    CHG=$(lipc-get-prop -i com.lab126.powerd isCharging 2>/dev/null)
    [ -z "$CHG" ] && CHG=0

    URL="${SERVER_BASE}?device=k4&batt=${BATT}&charging=${CHG}"

    if curl -s -f -m 6 "$URL" -o "$TMP_IMG"; then
        CUR_MIN=$(date +%M)
        CUR_MIN=${CUR_MIN#0}; [ -z "$CUR_MIN" ] && CUR_MIN=0
        # Pulizia anti-ghosting ogni 30 minuti (:00 e :30)
        if [ $((CUR_MIN % 30)) -eq 0 ]; then
            $FBINK -q -c -f -g file="$TMP_IMG" 2>/dev/null
        else
            $FBINK -q -g file="$TMP_IMG" 2>/dev/null
        fi
    else
        sleep 2
    fi
done
