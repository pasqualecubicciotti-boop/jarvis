# Jarvis – il tuo assistente personale su Telegram

Jarvis è un bot Telegram che risponde **solo a te** e usa l'intelligenza artificiale di Anthropic (Claude).
Per ora sa: dirti data e ora, salvare promemoria in un file, elencarli e **scriverti da solo su Telegram all'ora giusta**.

> Costi: paghi solo l'uso della chiave Anthropic (con il modello predefinito, molto economico) e l'affitto del server.
> Jarvis ha un limite giornaliero di richieste, così non ti arrivano brutte sorprese.

---

## Parte 1 – Cosa ti serve (si fa dal telefono o dal computer)

1. **Il token del bot.** Su Telegram cerca **@BotFather**, scrivi `/newbot`, scegli un nome. Ti darà una riga lunga tipo `123456:ABC...`. È il *token*: è la password del bot, non darla a nessuno.
2. **Il tuo ID Telegram.** Scrivi a **@userinfobot**: ti risponde con un numero. È il tuo ID.
3. **La chiave Anthropic.** Vai su <https://console.anthropic.com>, crea un account, metti un po' di credito e crea una *API key*. Consiglio: imposta lì anche un tetto di spesa mensile.
4. **Un server Linux in affitto** (un VPS Ubuntu va benissimo, bastano 1 CPU e 1 GB di memoria; costa pochi euro al mese). Il fornitore ti dà un indirizzo IP e una password o una chiave per entrare.

---

## Parte 2 – Installazione sul server

Ti colleghi al server dal terminale (su Windows: "PowerShell"; su Mac: "Terminale"):

```
ssh root@INDIRIZZO-IP-DEL-SERVER
```

Poi copia e incolla questi comandi, uno blocco alla volta.

**a) Prepara il sistema e un utente dedicato**
```
apt update && apt install -y python3 python3-venv git
adduser --disabled-password --gecos "" jarvis
```

**b) Scarica Jarvis e installalo**
```
su - jarvis
git clone https://github.com/pasqualecubicciotti-boop/jarvis.git
cd jarvis
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**c) Inserisci le tue chiavi**
```
cp .env.example .env
nano .env
```
Sostituisci i tre valori (token del bot, il tuo ID, chiave Anthropic). Salva con `Ctrl+O`, `Invio`, esci con `Ctrl+X`.
Il file `.env` resta solo sul server: non viene mai caricato su GitHub.

**d) Prova veloce**
```
.venv/bin/python -m jarvis
```
Apri Telegram, scrivi `/start` al tuo bot: deve rispondere. Premi `Ctrl+C` per fermarlo.

---

## Parte 3 – Farlo ripartire da solo

Con questo passo Jarvis parte quando il server si accende e **riparte da solo se si ferma** (dopo 10 secondi).

Torna amministratore (scrivi `exit` per uscire dall'utente jarvis), poi:

```
cp /home/jarvis/jarvis/jarvis.service /etc/systemd/system/jarvis.service
systemctl daemon-reload
systemctl enable --now jarvis
```

Comandi utili:

| Cosa vuoi fare | Comando |
|---|---|
| Vedere se funziona | `systemctl status jarvis` |
| Vedere cosa sta succedendo | `journalctl -u jarvis -f` (esci con `Ctrl+C`) |
| Riavviarlo | `systemctl restart jarvis` |
| Fermarlo | `systemctl stop jarvis` |

Dopo aver cambiato il file `.env`, esegui `systemctl restart jarvis`.

**Perché resta acceso 24 ore su 24:** il server Hetzner è sempre acceso e il servizio `jarvis` parte con il server e riparte da solo dopo uno stop o un errore. Non devi tenere aperto il tuo computer né la finestra nera. Puoi controllare in qualsiasi momento con `systemctl status jarvis`.

**Aggiornare Jarvis in futuro** (da root sul server):
```
su - jarvis -c 'cd jarvis && git pull && .venv/bin/pip install -r requirements.txt'
systemctl restart jarvis
```

---

## Come si usa

Scrivigli normalmente: *"Che giorno è oggi?"*, *"Ricordami di chiamare Anna domani alle 9"*, *"Quali promemoria ho?"*.

**Promemoria con avviso.** Se indichi un orario ("domani alle 9", "tra due ore"), Jarvis ti scrive da solo su Telegram a quell'ora. Controlla ogni 30 secondi. Se il server era spento in quel momento, ti avvisa appena riparte, aggiungendo "(in ritardo)". Se non indichi un orario, il promemoria viene solo salvato.

**Jarvis può contattarti di sua iniziativa.** Questa è la base per i compiti futuri (ricerca lavoro, progetto KDP, ecc.): qualsiasi compito automatico potrà scriverti su Telegram. Le **telefonate** non ci sono ancora: richiedono un servizio a parte (per esempio Twilio) e, come ogni azione che esce da Jarvis, passeranno dalla tua conferma sì/no.

Comandi: `/start` saluto · `/nuova` dimentica la conversazione · `/stato` richieste e errori di oggi · `/memoria` cosa ricorda di te · `/dimentica ID` cancella un appunto.

**Memoria.** Jarvis ha due memorie, entrambe salvate sul server e quindi **non si perdono ai riavvii**:
- **Appunti su di te** (preferenze, obiettivi, progetti): dì per esempio *"ricorda che cerco lavoro come grafico"*. Jarvis li legge a ogni risposta. Con `/memoria` li vedi, con `/dimentica ID` li cancelli senza usare l'intelligenza artificiale (quindi gratis). Se glielo chiedi a voce, prima ti domanda sì/no. Massimo 100 appunti da 300 caratteri.
- **Conversazione recente:** gli ultimi 20 messaggi di testo. `/nuova` li cancella.

Non chiedergli di ricordare password, chiavi o numeri di carta. I file della memoria stanno solo sul server, nella cartella `data/`, e non vanno mai su GitHub.

**Conferma sì/no.** Se in futuro Jarvis avrà strumenti che inviano messaggi, prenotano o pagano, prima di agire ti scriverà cosa vuole fare con due bottoni **Sì / No** (puoi anche rispondere scrivendo "sì" o "no"). Senza il tuo sì non succede nulla. Oggi nessuno strumento lo richiede, ma la struttura è già pronta: basta creare lo strumento con `requires_confirmation=True` (vedi `jarvis/tools.py`).

## Impostazioni (file `.env`)

| Nome | Cosa fa | Predefinito |
|---|---|---|
| `JARVIS_MODEL` | Modello: `claude-haiku-5-5` (economico), `claude-sonnet-5-5` (più capace), `claude-opus-5-5` (il migliore, costa di più) | `claude-haiku-5-5` |
| `JARVIS_MAX_TOKENS` | Lunghezza massima di ogni risposta | 1024 |
| `JARVIS_EFFORT` | Quanto ragiona: `low`, `medium`, `high` | `low` |
| `JARVIS_DAILY_LIMIT` | Massimo di richieste al modello al giorno | 100 |
| `JARVIS_TIMEZONE` | Fuso orario | Europe/Rome |
| `JARVIS_DATA_DIR` | Dove salva i dati | `data` |

Per passare a Sonnet: cambia `JARVIS_MODEL=claude-sonnet-5-5` e riavvia.
Nota: una singola tua domanda può usare più "richieste" al limite (ad esempio una per capire cosa fare e una per rispondere dopo aver usato uno strumento).

## Dove sono i dati (cartella `data/`)

- `reminders.json` – i promemoria
- `memory.json` – gli appunti su di te
- `history.json` – la conversazione recente
- `usage.json` – richieste ed errori per giorno
- `jarvis.log` – registro degli errori

## Sicurezza

- Il bot ignora in silenzio chiunque non abbia il tuo ID.
- Chiavi e ID stanno solo in `.env` (escluso da Git). Se pensi che un token sia trapelato, rigeneralo (BotFather: `/revoke`; console Anthropic: nuova chiave).
- Tieni il server aggiornato: `apt update && apt upgrade` ogni tanto.

## Per chi sviluppa

```
pip install -r requirements-dev.txt
pytest
```
I test usano chiavi finte e un client simulato: niente rete, niente costi.
