# 📖 Kindle Calendar Dashboard (E-Ink Smart Kiosk)

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Kindle%20Paperwhite-lightgrey.svg)](#)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#)
[![Display](https://img.shields.io/badge/Display-E--Ink%20Monochrome-black.svg)](#)

Un cruscotto intelligente ad alto contrasto per **Kindle Paperwhite (PW1 / PW2 / PW3 / PW4)** jailbroken, trasformato in uno smart display da scrivania a bassissimo consumo.

Sincronizza e visualizza in tempo reale:
- **Linea del tempo giornaliera (07:00–23:00):** con orologio atomico e badge di posizione sincronizzati al millisecondo.
- **Calendario macOS & iCloud:** deduplicazione automatica degli eventi, supporto eventi full-day e impegni a orario.
- **Agenda Scolastica (ClasseViva Spaggiari):** compiti e verifiche con classificazione semantica tramite **Groq LLM** (distinzione accurata tra verifiche reali e compiti normali).
- **Meteo locale ad alta efficienza:** previsioni a 3 giorni tramite Open-Meteo (senza API key).
- **Percentuale batteria reale & ricarica (⚡):** rilevamento dal circuito hardware del Kindle.
- **Auto-Luminosità Notturna (PWM Hardware Shutdown):** spegnimento hardware dei LED frontlight (0%) alle **22:00** e riaccensione al 50% alle **06:30**.

---

![Dashboard Preview](docs/preview.png)

---

## 🏛️ Architettura di Sistema

```mermaid
flowchart TD
    subgraph Client ["🖥️ macOS Client"]
        A[Apple Calendar.app] -->|AppleScript| B[sync_calendar.py]
        B -->|SCP / rsync| C[calendar_feed.ics]
    end

    subgraph Server ["🐧 Linux Server / LXC 141"]
        C --> D[server.py HTTP Server :5055]
        CV[ClasseViva API] -->|Cache 1h| D
        GQ[Groq LLM API] -->|Classificazione| D
        OM[Open-Meteo API] --> D
        D --> E[HTML Dashboard Template]
        E -->|Pre-render a :55| F[render_loop.py - Playwright Headless Chromium]
        F -->|ImageMagick 90°| G[/api/image - PNG 758x1024]
    end

    subgraph Kindle ["📱 Kindle Paperwhite"]
        H[kindle_kiosk.sh Daemon] -->|curl a :00.0| G
        H -->|gasgauge-info / lipc| D
        H -->|FBInk Framebuffer| I[Display E-Ink]
        H -->|sysfs PWM| J[LED Frontlight 0% / 50%]
    end
```

---

## ✨ Funzionalità Principali

### ⏱️ Sincronizzazione Atomica al Secondo (:00)
- Il server Chromium in RAM renderizza a **`:55`** lo snapshot già etichettato per il minuto successivo $M+1$.
- Alle **`:56.5`** l'immagine ruotata a 90° è salvata su disco con rename atomico POSIX.
- Il Kindle si risveglia esattamente a **`:00.0`**, scarica il file in ~50ms e disegna con FBInk in ~250ms: alle **`:00.3`** lo schermo è già aggiornato senza alcun ritardo.

### 🧠 Filtro Intelligente Verifiche (Groq LLM)
- I compiti scaricati dal registro elettronico vengono analizzati da un modello LLM ultraveloce (`qwen/qwen3.8-27b` su Groq).
- Riconosce le frasi ambigue (es. *"rispondere sul quaderno, tipo verifica di storia alle domande..."* non viene scambiata per una vera verifica).
- Le verifiche reali vengono evidenziate con card nera ad alto contrasto.

### 🌙 Gestione Luminosità Hardware (0% Notte / 50% Giorno)
- I Kindle Paperwhite non spengono i LED con i comandi software standard (rimangono al livello hardware 1).
- Il demone kiosk forza lo spegnimento fisico sul controller PWM `/sys/devices/system/fl_tps6116x/fl_tps6116x0/fl_intensity` a `0` tra le **22:00** e le **06:30**, azzerando qualunque emissione luminosa nella stanza.
- Alle **06:30** ripristina la luminosità al **50%** (livello 12 di 24).

---

## 🚀 Guida all'Installazione

### 1. Requisiti Server (Linux / LXC / Docker)
- Python 3.10+
- ImageMagick (`convert`)
- Chromium e dipendenze Playwright

```bash
# Dipendenze di sistema (Debian/Ubuntu)
sudo apt update && sudo apt install -y python3 python3-venv imagemagick curl

# Clone del repository
git clone https://github.com/Gianlu1107/kindle-calendar.git /opt/kindleCalendar
cd /opt/kindleCalendar

# Creazione virtual environment
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
./venv/bin/playwright install chromium
./venv/bin/playwright install-deps chromium

# Configurazione variabili d'ambiente
cp .env.example .env
nano .env
```

### 2. Configurazione Servizi Systemd

```bash
sudo cp systemd/kindle-server.service /etc/systemd/system/
sudo cp systemd/kindle-renderer.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now kindle-server.service
sudo systemctl enable --now kindle-renderer.service
```

Verifica lo stato dei servizi:
```bash
systemctl status kindle-server.service
systemctl status kindle-renderer.service
```

---

### 3. Setup del Kindle Paperwhite (Client Kiosk)

#### Prerequisiti sul Kindle:
1. Jailbreak attivo sul Kindle Paperwhite.
2. **KUAL** (Kindle Unified Application Launcher) installato.
3. **USBNetwork** installato e configurato (con SSH abilitato su Wi-Fi).
4. **FBInk** installato in `/mnt/us/usbnet/bin/fbink`.

#### Installazione Script Kiosk:
Copia lo script kiosk sul Kindle:
```bash
scp -i ~/.ssh/kindle_rsa client/kindle_kiosk.sh root@<IP_KINDLE>:/mnt/us/kindle_kiosk.sh
ssh -i ~/.ssh/kindle_rsa root@<IP_KINDLE> "chmod +x /mnt/us/kindle_kiosk.sh"
```

Copia la configurazione Upstart per l'avvio automatico al boot:
```bash
scp -i ~/.ssh/kindle_rsa client/kindle_kiosk.conf root@<IP_KINDLE>:/etc/upstart/kindle_kiosk.conf
```

Avvia il servizio kiosk:
```bash
ssh -i ~/.ssh/kindle_rsa root@<IP_KINDLE> "/sbin/restart kindle_kiosk"
```

---

### 4. Sincronizzazione macOS Calendar (Opzionale)

Se utilizzi l'app Calendario su macOS, puoi sincronizzare automaticamente gli eventi verso il server:

1. Modifica `macos_sync/sync_calendar.py` con l'IP e la destinazione del tuo server.
2. Installa l'agente Launchd su macOS:
```bash
cp macos_sync/com.kindle.calendarsync.plist.example ~/Library/LaunchAgents/com.kindle.calendarsync.plist
nano ~/Library/LaunchAgents/com.kindle.calendarsync.plist # adatta il path al tuo utente
launchctl load ~/Library/LaunchAgents/com.kindle.calendarsync.plist
```

---

## ⚙️ Variabili d'Ambiente (`.env`)

| Variabile | Descrizione | Default / Esempio |
|---|---|---|
| `PORT` | Porta del web server locale | `5055` |
| `CITY` | Città per le previsioni meteo Open-Meteo | `Padova` |
| `CLASSEVIVA_USERNAME` | Username o codice utente ClasseViva | Opzionale |
| `CLASSEVIVA_PASSWORD` | Password ClasseViva | Opzionale |
| `GROQ_API_KEY` | Chiave API Groq per il filtro LLM verifiche | `gsk_...` (Opzionale) |
| `ICLOUD_ICAL_URL` | URL pubblico feed iCalendar iCloud | Opzionale |
| `KINDLE_IP` | Indirizzo IP del Kindle nella rete locale | `192.168.1.28` |

---

## 🛠️ Manutenzione e Troubleshooting

- **Verifica snapshot live:**
  Apri nel browser `http://<IP_SERVER>:5055/` per visualizzare la dashboard in tempo reale o scarica `http://<IP_SERVER>:5055/api/image` per l'immagine ruotata a 90°.
- **NTP Drift sul Kindle:**
  Lo script client esegue periodicamente `ntpdate -u pool.ntp.org` per mantenere l'allineamento orario a < 5 millisecondi.
- **Risoluzione schermo:**
  Ottimizzato nativamente per il display 1024×758 (Kindle Paperwhite 1/2/3/4).

---

## 📄 Licenza

Rilasciato sotto licenza [MIT](LICENSE). Libero per uso personale e commerciale.
