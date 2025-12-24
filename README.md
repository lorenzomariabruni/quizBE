# Quiz Backend (Python + FastAPI + WebSocket)

## Architettura

### Stack Tecnologico
- **FastAPI**: Framework web moderno e veloce
- **Socket.IO**: Comunicazione real-time bidirezionale
- **Pydantic**: Validazione dati e type hints
- **Uvicorn**: ASGI server ad alte prestazioni

### Componenti Principali

#### 1. Socket Manager (`socket_manager.py`)
Gestisce tutte le connessioni WebSocket e gli eventi:
- `create_session`: Host crea una sessione
- `join_session`: Giocatori si uniscono
- `start_game`: Avvio del quiz
- `submit_answer`: Invio risposte
- Timer automatico per ogni domanda
- Calcolo punteggi in tempo reale

#### 2. Game Logic (`game_logic.py`)
**Sistema di punteggio**:
```python
# Risposta corretta: 100-1000 punti
points = 100 + (900 * speed_factor)

# Risposta errata: 0 a -500 punti (penalità)
points = -(500 * speed_factor)
```

Dove `speed_factor = 1 - (time_taken / time_limit)`

**Esempi**:
- Risposta corretta in 1s: ~900 punti
- Risposta corretta in 5s: ~550 punti
- Risposta corretta in 9s: ~190 punti
- Risposta errata in 1s: -450 punti (forte penalità)
- Risposta errata in 9s: -50 punti (penalità minore)

#### 3. Modello Dati (`models.py`)
- `Question`: Domanda con risposte multiple
- `Player`: Giocatore con punteggio e risposte
- `GameSession`: Sessione di gioco completa
- `Answer`: Risposta singola con timing e punti

### Formato JSON Domande

```json
{
  "questions": [
    {
      "question": "Testo della domanda?",
      "answers": ["Risposta 1", "Risposta 2", "Risposta 3", "Risposta 4"],
      "correct_answer": 1
    }
  ]
}
```

**Note**:
- `correct_answer`: indice (0-3) della risposta corretta
- Supporta 2-4 risposte per domanda
- File: `questions.json` nella root del progetto

## Installazione e Avvio

### Prerequisiti
- Python 3.8+
- pip

### Setup

```bash
# Clona il repository
git clone https://github.com/lorenzomariabruni/quizBE.git
cd quizBE

# Crea virtual environment
python -m venv venv

# Attiva virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Installa dipendenze
pip install -r requirements.txt

# Copia e configura .env
cp .env.example .env
# Modifica .env se necessario
```

### Avvio Server

```bash
# Modalità development (con auto-reload)
uvicorn app.main:socket_app --reload --host 0.0.0.0 --port 8000

# Oppure usando Python
python -m app.main
```

Il server sarà disponibile su:
- API: http://localhost:8000
- WebSocket: ws://localhost:8000/socket.io/
- Docs: http://localhost:8000/docs

## API Endpoints

### REST
- `GET /`: Health check
- `GET /health`: Status e versione
- `GET /sessions`: Lista sessioni attive (debug)

### WebSocket Events

#### Client → Server
- `create_session`: Crea sessione (host)
- `join_session`: Unisciti a sessione (player)
- `start_game`: Avvia quiz (host)
- `submit_answer`: Invia risposta (player)

#### Server → Client
- `session_created`: Sessione creata
- `joined_session`: Unione confermata
- `player_joined`: Nuovo giocatore
- `game_started`: Quiz iniziato
- `new_question`: Nuova domanda
- `timer_update`: Aggiornamento timer
- `time_up`: Tempo scaduto
- `question_results`: Risultati domanda
- `game_over`: Fine quiz
- `error`: Messaggi di errore

## Testing

### Test Manuale

1. Avvia il server
2. Apri http://localhost:8000/docs
3. Usa un client Socket.IO per testare eventi

### Estensioni Future

- Supporto per domande vero/falso
- Domande a risposta aperta
- Modalità multiplayer team
- Persistenza sessioni (database)
- Autenticazione utenti
- API per gestione domande
- Analytics e statistiche

## Troubleshooting

### Porta già in uso
```bash
# Cambia porta
uvicorn app.main:socket_app --port 8001
```

### CORS errors
Verifica `CORS_ORIGINS` in `.env` corrisponda all'URL del frontend

### WebSocket non si connette
- Verifica che il server sia avviato
- Controlla URL WebSocket nel frontend
- Verifica firewall/antivirus

## Licenza
MIT