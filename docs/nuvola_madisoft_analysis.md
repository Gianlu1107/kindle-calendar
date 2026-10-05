# Analisi di Fattibilità: Integrazione Registro Elettronico Nuvola (Madisoft)

Questo documento analizza la fattibilità tecnica di utilizzare il registro elettronico **Nuvola di Madisoft S.p.A.** come alternativa o opzione configurabile rispetto a **ClasseViva (Spaggiari)** all'interno del progetto **kindleCalendar**.

---

## 1. Sintesi e Risposta Diretta

> **Esito della verifica:** **SÌ, è pienamente fattibile.**

Nuvola Madisoft non offre un'API pubblica documentata per sviluppatori di terze parti, ma la sua applicazione web e mobile si appoggia su una **suite completa di API REST JSON** (`/api-studente/v1/...`). 

Queste API sono state analizzate, reverse-ingegnerizzate e implementate con successo da diversi progetti open-source (tra cui librerie Python su PyPI e componenti per Home Assistant aggiornati al 2026). I dati necessari per la dashboard e-ink (compiti per casa, verifiche, materie, date e descrizioni) sono interamente disponibili.

---

## 2. Dati Richiesti da kindleCalendar e Corrispondenza Nuvola

Attualmente, il server estrae da ClasseViva le seguenti informazioni per popolare la colonna destra del Kindle:
- **Materia** (es. Matematica, Italiano)
- **Data di scadenza / svolgimento** (categorizzata in "Oggi", "Domani", o data futura `DD/MM`)
- **Descrizione del compito / evento**
- **Tipologia di evento** (Verifica formale vs Compito ordinario, classificata tramite Groq LLM o regole euristiche)

### Tabella di comparazione dei campi dati:

| Concetto in kindleCalendar | ClasseViva (Spaggiari) | Nuvola (Madisoft) | Disponibilità / Note |
|---|---|---|---|
| **Identificativo Alunno** | `student_id` (da `AuthApi4.php`) | `id` (da `/api-studente/v1/alunni`) | Disponibile, supporta anche famiglie con più studenti |
| **Materia** | `subjectDesc` / `authorName` | `materia` | Disponibile in chiaro |
| **Data Scadenza / Consegna** | `evtDatetimeBegin` | `dataConsegna` o `dataInizio` | Formato standard (`YYYY-MM-DD` o `DD-MM-YYYY`) |
| **Descrizione** | `notes` | `descrizione` / `annotazioni` | Nota: in Nuvola `descrizione` può essere una stringa o una lista di stringhe |
| **Verifiche & Eventi** | `agenda` (con testo note) | `/eventi-classe` e `/compito/elenco/{data}` | Distinzione nativa tra compiti ed eventi/verifiche di classe |
| **Filtro Intelligente LLM** | Groq (`qwen/qwen3.8-27b`) | Invariato | Lo stesso prompt funziona identicamente con il testo restituito da Nuvola |

---

## 3. Architettura delle API di Nuvola Madisoft

### Parametri di Connessione di Base

- **Base URL:** `https://nuvola.madisoft.it`
- **Host Autenticazione (OIDC):** `auth.nuvola.madisoft.it`
- **Prefisso API:** `/api-studente/v1`
- **Formato Risposte:** JSON (solitamente incapsulato nell'oggetto `{"valori": [...]}`)
- **Autenticazione chiamate:** `Authorization: Bearer <jwt_token>` + query string `?contextAlunno=<student_id>`
- **Scadenza Token:** circa 28–30 minuti (perfettamente compatibile con la cache oraria del progetto)

### Flusso di Autenticazione

Nuvola supporta due flussi a seconda della configurazione dell'istituto scolastico:

#### A. Flusso Standard (Sessione Web + Scambio JWT)
1. **Richiesta GET iniziale:**
   ```http
   GET https://nuvola.madisoft.it/login
   ```
   Estrae il token CSRF dall'input HTML: `<input name="_csrf_token" value="..." />`.

2. **Login credenziali:**
   ```http
   POST https://nuvola.madisoft.it/login_check
   Content-Type: application/x-www-form-urlencoded

   _username=<USERNAME>&_password=<PASSWORD>&_csrf_token=<CSRF_TOKEN>
   ```
   Imposta il cookie di sessione `nuvola`.

3. **Scambio con Bearer JWT:**
   ```http
   GET https://nuvola.madisoft.it/api-studente/v1/login-from-web
   Cookie: nuvola=<SESSION_COOKIE>
   ```
   Restituisce un JSON con `{ "token": "eyJhbGci..." }`.

#### B. Flusso Moderno OIDC / Keycloak (in uso in molti istituti dal 2024–2026)
1. Nuvola effettua redirect da `/connect/authentication-service` a `auth.nuvola.madisoft.it` (Keycloak).
2. Viene compilato il form Keycloak con `_username`, `_password` e i parametri effimeri del form (`session_code`, `execution`, `tab_id`).
3. Il callback reindirizza all'area Nuvola e valida la sessione web.
4. Chiamata finale a `/api-studente/v1/login-from-web` per ottenere il JWT.

---

## 4. Endpoint Principali per kindleCalendar

Una volta ottenuto il token Bearer (`jwt_token`):

### 1. Recupero dell'ID Studente
```http
GET https://nuvola.madisoft.it/api-studente/v1/alunni
Authorization: Bearer <jwt_token>
```
**Risposta:**
```json
{
  "valori": [
    {
      "id": 12345,
      "nome": "Mario",
      "cognome": "Rossi",
      "classe": "3A",
      "scuola": "Istituto Esempio"
    }
  ]
}
```

### 2. Recupero dei Compiti per una Data
```http
GET https://nuvola.madisoft.it/api-studente/v1/alunno/12345/compito/elenco/10-03-2026?contextAlunno=12345
Authorization: Bearer <jwt_token>
```
**Risposta:**
```json
{
  "valori": [
    {
      "id": 7001,
      "materia": "MATEMATICA",
      "descrizione": ["Esercizi pag. 140 n. 1, 2, 3", "Rivedere formule triangoli"],
      "dataConsegna": "2026-03-10",
      "docente": "Prof. Bianchi"
    }
  ]
}
```

> **Nota di parsing:** il campo `descrizione` può essere una stringa oppure un array di stringhe. In Python si gestisce con:
> `descrizione = " ".join(item["descrizione"]) if isinstance(item["descrizione"], list) else str(item["descrizione"])`

### 3. Recupero degli Eventi e Verifiche di Classe
```http
GET https://nuvola.madisoft.it/api-studente/v1/alunno/12345/eventi-classe?contextAlunno=12345
Authorization: Bearer <jwt_token>
```
**Risposta:**
```json
{
  "valori": [
    {
      "id": 8001,
      "tipo": "verifica",
      "nome": "Verifica scritta di Storia",
      "descrizione": "Capitoli 4 e 5",
      "docente": "Prof.ssa Verdi",
      "dataInizio": "2026-03-12 09:00:00",
      "dataFine": "2026-03-12 10:00:00"
    }
  ]
}
```

---

## 5. Progetti e Riferimenti Open Source Esistenti

Esistono già implementazioni mature a cui fare riferimento per dettagli o codice riutilizzabile:

1. **`dddevid/Volta` (GitHub):**
   - Client mobile non ufficiale in Flutter per Nuvola Madisoft.
   - Contiene il file `NUVOLA_API.md` (aggiornato a **marzo 2026**) con tutte le specifiche complete degli endpoint reverse-engineered.
2. **`damjj/ha-nuvola` (GitHub):**
   - Integrazione custom per **Home Assistant** in Python (`custom_components/nuvola/api.py`).
   - Implementa il supporto al flusso di autenticazione OIDC Keycloak (`auth.nuvola.madisoft.it`), gestione sessione aiohttp, rinnovo automatico del token scaduto, scaricamento bacheca e compiti.
3. **`topongo/nuvola` (PyPI / GitHub):**
   - Libreria Python standalone (`pip install nuvola`) che implementa un client orientato agli oggetti per l'API studente di Nuvola Madisoft.
4. **`giorgiobeggiora/nuvola-notifiche` e `hex0x0000/NuvolaBot`:**
   - Bot e script per notifiche e monitoraggio dei compiti su Nuvola.

---

## 6. Valutazione di Impatto e Architettura per kindleCalendar

Qualora si decida di implementare Nuvola, la modifica all'architettura di `kindleCalendar` sarebbe molto pulita e modulare:

### Pattern ad Adattatore / Provider nel `server.py`
Invece di avere solo `get_classeviva_agenda(env)`, si può creare un'astrazione generica:
```
           +-----------------------------+
           |     kindleCalendar Server   |
           +--------------+--------------+
                          |
              +-----------+-----------+
              |                       |
    [Provider ClasseViva]     [Provider Nuvola]
              |                       |
              v                       v
     ClasseViva Spaggiari      Nuvola Madisoft
              |                       |
              +-----------+-----------+
                          |
                          v
         [Filtro Groq LLM / Regole Euristiche]
                          |
                          v
              [Render Template HTML]
```

### Configurazione d'Ambiente (`.env`)
Si possono supportare entrambi i sistemi permettendo la selezione automatica o esplicita:
```env
# Registro Elettronico (opzioni: classeviva, nuvola, none)
REGISTRO_PROVIDER=nuvola

# Credenziali Nuvola Madisoft
NUVOLA_USERNAME=tuo_username
NUVOLA_PASSWORD=tua_password
NUVOLA_STUDENT_ID=        # Opzionale: obbligatorio solo se l'account ha più figli
```

### Strategia di Caching
- Come per ClasseViva, una cache su file locale (es. `/tmp/nuvola_cache.json`) valida 1 ora (3600s) azzera il carico sui server Madisoft ed elimina qualsiasi rischio di ban dell'account o rate-limiting.

---

## 7. Limitazioni, Rischi e Best Practices

1. **Assenza di API Ufficiali Supportate:**
   - Trattandosi di API non pubblicamente garantite da Madisoft per uso esterno, eventuali modifiche al frontend potrebbero richiedere aggiornamenti del parser (sebbene l'API `/api-studente/v1` sia rimasta stabile negli ultimi anni).
2. **Accesso tramite SPID / CIE:**
   - Se un istituto scolastico disabilita completamente le credenziali tradizionali riservate a studenti o tutori imponendo esclusivamente SPID/CIE, l'accesso automatizzato non è possibile senza token o sessione manuale. Tuttavia, per gli account studente le credenziali username/password rimangono generalmente attive.
3. **Range Temporale delle Chiamate:**
   - Mentre ClasseViva restituisce l'agenda per un range (`/agendav2/all/{da}/{a}`), l'endpoint compiti di Nuvola lavora per singola data (`/compito/elenco/{date}`). È sufficiente effettuare chiamate concorrenti o cicliche per i giorni della settimana corrente e successiva (es. prossimi 7–14 giorni) oppure interrogare `/eventi-classe`.

---

## 8. Conclusione

La sostituzione o l'estensione di ClasseViva con **Nuvola Madisoft** è **fattibile, collaudata dalla community e pienamente compatibile** con le strutture dati e la grafica attualmente mostrata sulla dashboard Kindle.
