# Resoconto tecnico della revisione completa

Data della validazione: 2 settembre 2026  
Team: Paolo Monteduro (360415), Ludovico Pollastro (361775)

## 1. Esito sintetico

Il progetto è stato ristrutturato come piattaforma IoT a microservizi completa per
due escape room concorrenti. La versione corretta mantiene l'idea del proposal,
ma rimuove consapevolmente ThingSpeak, Telegram e Node-RED come richiesto dal
team: telemetria live, notifiche, controllo operativo e analytics sono integrati
nella Web Dashboard.

Sono stati corretti i contratti MQTT incoerenti, le funzionalità placeholder,
le correlazioni incomplete del Catalog, la gestione della persistenza, i calcoli
Analytics, la FSM, la safety strategy e il collegamento reale frontend/backend.
Il sistema è stato provato con tutti i processi applicativi attivi, due stanze,
broker MQTT, REST, SSE e SQLite.

## 2. Tracciabilità rispetto ai vincoli della consegna

| Vincolo | Implementazione ed evidenza |
| --- | --- |
| Python predominante, circa 80% | Python rappresenta circa l'85,4% dei byte tra sorgenti Python/JS/CSS/HTML, esclusi vendor e build. |
| Architettura a microservizi | 15 container applicativi più Mosquitto; ogni responsabilità ha un modulo e un Dockerfile dedicato. |
| Programmazione orientata agli oggetti | Store, client, connector, FSM, scheduler, analytics engine, bridge e provider sono classi con responsabilità separate. |
| Docker obbligatorio | `docker-compose.yml`, immagini non-root, health check, dipendenze, volumi nominati e porte host limitate a `127.0.0.1`. |
| Catalog centrale | CRUD completo GET/POST/PUT/DELETE per servizi, device e room; self-registration; discovery; correlazioni e strategie. |
| SenML | Tutta la telemetria di environment, badge e prop usa JSON SenML RFC 8428; encoder/decoder condiviso e testato. |
| MQTT client ID univoci | Gli ID includono ruolo e, per gli attori room-scoped, `room_id`; il wrapper ne valida il formato. |
| Configurazione esterna | Room, strategie, broker e soglie sono in JSON, `.conf`, `.env` e variabili Compose. |
| Nessuno scambio dati tramite file locali | I file JSON sono proprietà interna del Catalog; SQLite è proprietà esclusiva di TimeSeries; Analytics usa solo REST. |
| CherryPy | Tutte le API HTTP Python e il backend della dashboard usano CherryPy. |
| Più contesti/device | Due room complete e concorrenti; topic, client, strategie e record storici sono correlati a `room_id`. |
| GUI robusta al posto di Telegram | Alert critici live, feed persistente in memoria, presence, stato safety e comando di test caduta. |
| GUI/controllo al posto di Node-RED | Stato FSM, telemetria, prop, badge, environment, attuatori e comandi manuali con SSE reale. |
| Storico al posto di ThingSpeak | TimeSeries con SQLite/WAL e API REST; dashboard con grafici storici, heatmap e Analytics. |
| Analytics non banali | Durate reali, tasso completamento, throughput, ambiente, heatmap, bottleneck, safety e manutenzione. |

## 3. Architettura consegnata

| Componente | Istanze | Responsabilità principale |
| --- | ---: | --- |
| Mosquitto | 1 | Broker MQTT 3.1.1 persistente |
| Game Catalog | 1 | Registry, discovery, CRUD, correlazioni e strategie |
| Environment Connector | 2 | BME680 simulato/calibrato e telemetria SenML |
| Room Actuator Connector | 2 | Serratura, luci e audio; override safety indipendente |
| Badge Connector | 2 | Posizione, batteria, heartbeat e caduta |
| Prop Connector | 2 | RFID, button, capacitive e rotary; health e interaction |
| Room Control | 2 | FSM indipendente, timer, azioni e recovery |
| Safety Monitor | 1 | Regole caduta/qualità aria e sblocco di emergenza |
| TimeSeries Adapter | 1 | Ingest MQTT, coda, batch, retention, SQLite e REST |
| Analytics | 1 | Calcoli storici via REST, senza accesso diretto al DB |
| Web Dashboard | 1 | GUI, cache live MQTT, SSE, proxy e comandi validati |

Totale: 16 container nel file Compose.

## 4. Correzioni principali

### 4.1 Contratto MQTT condiviso

- sostituiti i topic costruiti localmente con helper canonici;
- separati telemetry, event, command, status, transition, session e alert;
- fissati QoS coerenti: 0 per telemetria periodica, 1 per eventi e comandi;
- introdotti LWT, presence retained, heartbeat e risottoscrizione automatica;
- aggiunta attesa della riconnessione per evitare crash se il broker cade tra
  connessione iniziale e primo publish;
- aggiunto recupero dello stato FSM retained senza ripetere gli attuatori.

### 4.2 Game Catalog

- implementato CRUD HTTP completo con status 201/200/400/404/409/415;
- eliminato un errore del dispatcher CherryPy che faceva restituire `rooms` o
  `services` come testo invece del JSON della collezione;
- evitati redirect su POST che avrebbero trasformato la richiesta in GET;
- aggiunte scritture JSON atomiche, lock e copie profonde;
- validate struttura room, dimensioni, durata, badge, prop, attuatori, versioni
  e riferimenti FSM;
- impediti device orfani, connector inesistenti, spostamenti cross-room e
  cancellazioni che romperebbero le correlazioni;
- mantenuto stabile l'ordine delle room durante gli update;
- aggiunto hot-reload strategia Catalog REST -> MQTT -> Room Control.

### 4.3 Device Connector

- Environment e Room Actuator sono microservizi distinti;
- il provider BME680 simulato produce un random walk limitato e ripetibile;
- badge multipli per room producono posizione, batteria e heartbeat naturali;
- il comando `force_fall` genera un vero evento SenML sul topic safety;
- i prop sono letti dal Catalog e validano sensor e valore atteso;
- i loop di pubblicazione terminano in modo ordinato e tollerano disconnessioni.

### 4.4 Room Control e FSM

- una FSM indipendente per container e room;
- validazione strutturale e semantica delle strategie;
- transizioni event-based e time-based realmente eseguite;
- `session_id`, tempi di ingresso, durata reale e transizioni persistibili;
- terminal state con un solo `session_ended`, senza duplicati;
- reset completo con nuova sessione;
- recovery retained verificata dopo arresto forzato del processo;
- hot-reload senza perdere sessione o stato corrente.

### 4.5 Safety

- fall detection e soglie temperature/humidity/CO2/VOC configurabili;
- cooldown per evitare alert storm;
- alert critico globale più comando room-specific di emergency unlock;
- la strategia opera indipendentemente da Room Control;
- la dashboard mostra l'alert live, sostituendo la funzione Telegram.

### 4.6 TimeSeries

- TimeSeries è l'unico proprietario del file SQLite;
- WAL, busy timeout, indici, connessioni per operazione e query parametrizzate;
- coda limitata, writer in batch e drain allo shutdown;
- filtri temporali, room/type, ordinamento, limit e offset;
- retention configurabile;
- reset POST con conferma e barriera ordinata: nessun evento accettato prima del
  reset può essere scritto nuovamente dopo la cancellazione.

### 4.7 Analytics

- rimosso qualsiasi volume o accesso diretto a SQLite;
- client TimeSeries REST con timeout e paginazione;
- calcoli basati su eventi storici reali anziché valori placeholder;
- validazione dei periodi e mapping stabile degli errori HTTP;
- summary post-session pubblicato via MQTT.

### 4.8 Web Dashboard

- frontend Vite realmente collegato a `EventSource('/api/stream')`;
- nessuna CDN o dipendenza runtime esterna;
- vista multi-room di FSM, environment, badge, batteria, prop e attuatori;
- comandi Game Master validati lato backend;
- grafico storico e heatmap su canvas nativo;
- alert banner, presence LWT/heartbeat e log live;
- CSP, anti-frame, no-sniff e referrer policy;
- tutte le API browser sono relative, quindi funzionano senza hardcoding host.

### 4.9 Docker e repository

- immagini Python 3.12 non-root (`65532:65532`);
- build frontend multi-stage Node 22 -> Python runtime;
- health check e `depends_on` sulle dipendenze critiche;
- Catalog, Mosquitto e TimeSeries su volumi distinti;
- nessun volume TimeSeries condiviso con Analytics;
- soglie `.env.example` realmente collegate a Compose;
- database demo precompilato, cache, `node_modules`, build e segreti esclusi.

## 5. Verifiche eseguite

| Verifica | Esito |
| --- | --- |
| Test unitari e di contratto | 20 superati |
| Ruff | nessun errore |
| `compileall` | superato |
| `pip check` | nessuna dipendenza rotta |
| Bandit su `shared` e `services` | nessun finding non giustificato; nessun high severity |
| Build Vite 8.1.4 | superata |
| `npm audit` | 0 vulnerabilità info/low/moderate/high/critical |
| Parsing e invarianti Compose | 16 servizi, 3 volumi, Dockerfile esistenti, app non-root |
| Flusso end-to-end completo | superato senza ERROR, traceback o eccezioni applicative |
| Isolamento room1/room2 | superato |
| REST -> MQTT -> FSM | superato |
| Transizione temporizzata | superata |
| MQTT -> SQLite -> REST Analytics | superato |
| SSE browser backend | evento MQTT reale ricevuto |
| Fall -> alert -> emergency unlock | superato |
| Recovery dopo crash Room Control | stesso session ID e stesso stato, nessun replay azioni |
| Hot-reload strategia | update valido applicato; update invalido rifiutato atomicamente |
| Restart broker | client riconnessi, risottoscritti e flusso comandi ripreso |

Il test black-box consegnato è `tests/integration/verify_stack.py`. Non considera
un semplice HTTP 200 come prova: attende gli effetti downstream nella FSM, nella
persistenza, negli Analytics, nello stream SSE e negli attuatori.

## 6. Limiti dichiarati

- Nell'ambiente usato per questa revisione non era installato Docker Engine.
  Non è stato quindi possibile eseguire materialmente `docker compose build`.
  Il Compose è stato parsato e verificato semanticamente; gli stessi processi,
  porte e dipendenze sono stati eseguiti localmente end-to-end.
- I sensori e gli attuatori sono provider simulati. L'integrazione elettrica
  Raspberry Pi/ESP32 richiede hardware, pin e librerie del laboratorio; il
  contratto Device Connector è già separato per sostituire il provider.
- Il profilo demo usa Mosquitto anonimo ma esposto sull'host solo in loopback.
  Un deployment remoto deve aggiungere credenziali/TLS e autenticazione del
  reverse proxy.
- Il runtime supportato è Python 3.12. CherryPy 18.9 usa ancora internamente il
  modulo `cgi`, deprecato in Python 3.13; la versione Docker evita il problema.

Questi punti non bloccano la demo e non sono funzionalità nascoste: sono confini
espliciti tra progetto software, ambiente Docker e hardware fisico.

## 7. Esecuzione e accettazione

```bash
docker compose up --build -d
docker compose ps
python tests/integration/verify_stack.py
```

Dashboard: <http://localhost:8087>

Per un reset intenzionale di tutti i dati persistenti:

```bash
docker compose down -v
```

Non usare `-v` durante un normale stop, perché elimina Catalog, retained data e
storico TimeSeries.

## 8. Conclusione

La release è coerente con il proposal aggiornato e con i vincoli tecnici della
consegna. Paolo e Ludovico risultano gli unici membri del team. Le sostituzioni
di Node-RED, Telegram e ThingSpeak non sono semplici rimozioni: le rispettive
funzioni sono presenti nella dashboard e nei microservizi interni, con test
osservabili sugli effetti reali.
