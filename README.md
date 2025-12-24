# 🎯 Quiz Backend (Python + FastAPI + WebSocket)

> Backend real-time per quiz multiplayer con Socket.IO, supporto mobile e riconnessione automatica

## 📋 Indice

- [Caratteristiche](#-caratteristiche)
- [Stack Tecnologico](#-stack-tecnologico)
- [Architettura](#-architettura)
- [Installazione](#-installazione)
- [Avvio Rapido](#-avvio-rapido)
- [Configurazione](#-configurazione)
- [API & Eventi WebSocket](#-api--eventi-websocket)
- [Sistema di Punteggio](#-sistema-di-punteggio)
- [Riconnessione Mobile](#-riconnessione-mobile)
- [Troubleshooting](#-troubleshooting)

## ✨ Caratteristiche

- ⚡ **Real-time WebSocket** con Socket.IO
- 🎮 **Quiz multiplayer** con timer sincronizzato
- 📱 **Supporto mobile ottimizzato** con riconnessione automatica
- 🔄 **Recupero sessione** dopo disconnessione
- 🏆 **Sistema di punteggio dinamico** basato su velocità
- 📊 **Classifica in tempo reale**
- 🔌 **CORS configurabile** per deployment
- 📝 **Domande personalizzabili** via JSON
- 🎲 **Sessioni multiple** simultanee
- 💾 **Gestione stato in-memory** (scalabile a database)

## 🛠 Stack Tecnologico

- **FastAPI** - Framework web moderno e veloce
- **Socket.IO** - Comunicazione real-time bidirezionale
- **Pydantic** - Validazione dati e type hints
- **Uvicorn** - ASGI server ad alte prestazioni
- **Python 3.8+** - Linguaggio di sviluppo

## 🏗 Architettura

### Componenti Principali

#### 1. Socket Manager (`app/socket_manager.py`)
Gestisce tutte le connessioni WebSocket e gli eventi del gioco con supporto riconnessione mobile.

#### 2. Game Logic (`app/game_logic.py`)
Sistema di punteggio dinamico: 100-1000 punti per risposte corrette, penalità fino a -500 per errori veloci.

#### 3. Modelli Dati (`app/models.py`)
Player con flag `connected` per gestione riconnessioni, GameSession con stato del quiz.

## 📦 Installazione

### Prerequisiti

- Python 3.8+
- pip

### Setup

```bash
# Clone repository
git clone https://github.com/lorenzomariabruni/quizBE.git
cd quizBE

# Crea virtual environment
python -m venv venv

# Attiva virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Installa dipendenze
pip install -r requirements.txt
```

## 🚀 Avvio Rapido

### Sviluppo (con auto-reload)

```bash
uvicorn app.main:socket_app --reload --host 0.0.0.0 --port 8000
```

**IMPORTANTE**: Usa `--host 0.0.0.0` per permettere connessioni da dispositivi mobile sulla rete locale!

### Verifica

- Health Check: http://localhost:8000/health
- API Docs: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/socket.io/

## ⚙️ Configurazione

### CORS

Il server accetta connessioni da qualsiasi origine per sviluppo:

```python
allow_origins=["*"]  # Modificare per produzione
```

### Socket.IO Mobile-Optimized

```python
ping_timeout=60      # Attesa 60s prima di disconnect
ping_interval=25     # Heartbeat ogni 25s
```

## 📡 API & Eventi WebSocket

### Eventi Client → Server

- `create_session` - Crea sessione (host)
- `join_session` - Unisciti/Riconnettiti (player)
- `start_game` - Avvia quiz (host)
- `submit_answer` - Invia risposta (player)

### Eventi Server → Client

- `session_created` - Conferma creazione
- `joined_session` - Conferma join (con flag `reconnected`)
- `game_started` - Quiz iniziato
- `new_question` - Nuova domanda (con flag `already_answered`)
- `timer_update` - Countdown
- `answer_submitted` - Feedback risposta
- `question_results` - Risultati domanda
- `game_over` - Fine quiz con classifica

## 🏆 Sistema di Punteggio

```python
speed_factor = 1 - (time_taken / time_limit)

# Corretta: 100-1000 punti
points = 100 + (900 * speed_factor)

# Errata: 0 a -500 punti
points = -(500 * speed_factor)
```

### Esempi

| Tempo | Corretta | Errata |
|-------|----------|--------|
| 1s    | ~900     | -450   |
| 5s    | ~550     | -275   |
| 9s    | ~190     | -95    |
| 10s   | 100      | 0      |

## 📱 Riconnessione Mobile

### Funzionalità

- Auto-rejoin dopo disconnect (schermo bloccato, rete persa)
- Recupero punteggio e risposte
- Sincronizzazione domanda corrente
- Prevenzione risposte duplicate con flag `already_answered`

### Flusso

1. Player disconnette → marcato `connected: false`, dati mantenuti
2. Player riconnette → `join_session` con stesso nome
3. Backend riconosce player → aggiorna socket ID
4. Invia stato corrente → domanda + punteggio + flag già risposto

## 🐛 Troubleshooting

### Porta già in uso

```bash
# Cambia porta
uvicorn app.main:socket_app --port 8001

# Termina processo
# Linux/Mac:
lsof -ti:8000 | xargs kill -9
# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Mobile non si connette

**Checklist**:
- [ ] Server avviato con `--host 0.0.0.0`
- [ ] Firewall permette porta 8000
- [ ] Mobile sulla stessa rete WiFi
- [ ] Test: http://IP_PC:8000/health dal browser mobile

**Apri firewall**:
```bash
# Linux
sudo ufw allow 8000/tcp

# Mac: System Preferences → Security → Firewall
# Windows: Defender Firewall → Inbound Rules
```

### Formato Domande

```json
{
  "questions": [
    {
      "question": "Domanda?",
      "answers": ["A", "B", "C", "D"],
      "correct_answer": 1
    }
  ]
}
```

Salva come `questions.json` nella root.

## 📄 Licenza

MIT

## 👨‍💻 Autore

Lorenzo Maria Bruni - [@lorenzomariabruni](https://github.com/lorenzomariabruni)