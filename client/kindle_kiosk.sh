#!/bin/sh
# ==============================================================================
# Kindle Client Daemon - High-Precision Atomic Kiosk Client
# Supports:
#   - Atomic minute synchronization (:00)
#   - Real hardware battery percentage and charging detection
#   - Dynamic day/night frontlight (0% at 22:00, 50% at 06:30 with full PWM shutdown)
#   - Automatic background NTP synchronization
#   - Screensaver prevention (preventScreenSaver)
# ==============================================================================

# Timezone string for Italy / Central Europe
export TZ='CET-1CEST,M3.5.0,M10.5.0/3'

SERVER_BASE="http://192.168.1.250:5055/api/image"
FBINK="/mnt/us/usbnet/bin/fbink"
TMP_IMG="/tmp/dashboard.png"

# Setup Kiosk & Power
/sbin/stop pillow 2>/dev/null
/sbin/stop framework 2>/dev/null
lipc-set-prop -i com.lab126.powerd preventScreenSaver 1 2>/dev/null

# Hardware frontlight intensity controller:
# Day   (06:30 - 22:00): 50% (12 of 24)
# Night (22:00 - 06:30): 0% (Physical PWM chip shutdown on /sys/devices/.../fl_intensity)
apply_frontlight() {
    _H=$(date +%H)
    _M=$(date +%M)
    _H=${_H#0}; [ -z "$_H" ] && _H=0
    _M=${_M#0}; [ -z "$_M" ] && _M=0
    _MIN=$(( _H * 60 + _M ))

    if [ "$_MIN" -ge 390 ] && [ "$_MIN" -lt 1320 ]; then
        # DAY: 50%
        lipc-set-prop -i com.lab126.powerd flIntensity 12 2>/dev/null
    else
        # NIGHT: 0% total hardware shutdown
        lipc-set-prop -i com.lab126.powerd flIntensity 0 2>/dev/null
        echo 0 > /sys/devices/system/fl_tps6116x/fl_tps6116x0/fl_intensity 2>/dev/null
    fi
}

apply_frontlight

echo "=== KINDLE ATOMIC KIOSK CLIENT ATTIVO ==="

# Initial NTP time synchronization
ntpdate -u pool.ntp.org >/dev/null 2>&1 || ntpdate -u 192.168.1.250 >/dev/null 2>&1

# Initial render
BATT=$(gasgauge-info -s 2>/dev/null)
[ -z "$BATT" ] && BATT=$(cat /sys/class/power_supply/max77696-battery/capacity 2>/dev/null)
[ -z "$BATT" ] && BATT=$(lipc-get-prop -i com.lab126.powerd battLevel 2>/dev/null)
[ -z "$BATT" ] && BATT=100

CHG=$(lipc-get-prop -i com.lab126.powerd isCharging 2>/dev/null)
[ -z "$CHG" ] && CHG=0

curl -s -f -m 5 "${SERVER_BASE}?batt=${BATT}&charging=${CHG}" -o "$TMP_IMG" && \
    $FBINK -c -f -g file="$TMP_IMG" 2>/dev/null

# Main atomic kiosk loop
CYCLE=0
while true; do
    # Calculate exact sleep until the next atomic :00 mark
    NOW=$(date +%s)
    SEC=$((NOW % 60))
    SLEEP_SEC=$((60 - SEC))
    [ "$SLEEP_SEC" -le 0 ] && SLEEP_SEC=60

    sleep "$SLEEP_SEC"

    # Periodic NTP background sync (every hour)
    CYCLE=$((CYCLE + 1))
    if [ "$CYCLE" -ge 60 ]; then
        CYCLE=0
        (ntpdate -u pool.ntp.org >/dev/null 2>&1 || ntpdate -u 192.168.1.250 >/dev/null 2>&1) &
    fi

    # Read hardware battery percentage & charging status
    BATT=$(gasgauge-info -s 2>/dev/null)
    [ -z "$BATT" ] && BATT=$(cat /sys/class/power_supply/max77696-battery/capacity 2>/dev/null)
    [ -z "$BATT" ] && BATT=$(lipc-get-prop -i com.lab126.powerd battLevel 2>/dev/null)
    [ -z "$BATT" ] && BATT=100

    CHG=$(lipc-get-prop -i com.lab126.powerd isCharging 2>/dev/null)
    [ -z "$CHG" ] && CHG=0

    URL="${SERVER_BASE}?batt=${BATT}&charging=${CHG}"

    # Keep screensaver disabled and enforce daylight frontlight schedule
    lipc-set-prop -i com.lab126.powerd preventScreenSaver 1 2>/dev/null
    apply_frontlight

    # Download fresh rendered snapshot and flash display
    if curl -s -f -m 5 "$URL" -o "$TMP_IMG"; then
        # Anti Burn-in & Ghosting mitigation:
        # Ogni 30 minuti (:00 e :30), esegui un flash completo con clearing (-c -f)
        # Negli altri minuti esegui un refresh rapido senza flash invasivo per non disturbare l'utente.
        CUR_MIN=$(date +%M)
        CUR_MIN=${CUR_MIN#0}; [ -z "$CUR_MIN" ] && CUR_MIN=0
        if [ $((CUR_MIN % 30)) -eq 0 ]; then
            $FBINK -q -k 2>/dev/null
            $FBINK -q -c -f -g file="$TMP_IMG" 2>/dev/null
        else
            $FBINK -q -g file="$TMP_IMG" 2>/dev/null
        fi
    else
        # Retry shortly in case of transient Wi-Fi latency
        sleep 2
    fi
done
