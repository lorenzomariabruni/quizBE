import socketio
import asyncio
from typing import Dict, List
from app.models import GameSession, Player, Question, Answer
from app.game_logic import calculate_score, load_questions

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True
)

# In-memory storage
sessions: Dict[str, GameSession] = {}
players: Dict[str, Player] = {}  # sid -> Player


@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    await sio.emit('connection_established', {'sid': sid}, room=sid)


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")
    if sid in players:
        player = players[sid]
        if player.session_id in sessions:
            session = sessions[player.session_id]
            session.players = [p for p in session.players if p.sid != sid]
            await sio.emit('player_left', {'player_name': player.name}, room=player.session_id)
        del players[sid]


@sio.event
async def create_session(sid, data):
    """Host creates a new game session"""
    session_id = data.get('session_id', 'QUIZ001')
    questions = load_questions()
    
    session = GameSession(
        session_id=session_id,
        host_sid=sid,
        questions=questions,
        current_question_index=-1,
        state='waiting'
    )
    sessions[session_id] = session
    
    await sio.enter_room(sid, session_id)
    await sio.emit('session_created', {
        'session_id': session_id,
        'total_questions': len(questions)
    }, room=sid)
    print(f"Session created: {session_id}")


@sio.event
async def join_session(sid, data):
    """Player joins a session"""
    session_id = data.get('session_id')
    player_name = data.get('player_name')
    
    if session_id not in sessions:
        await sio.emit('error', {'message': 'Session not found'}, room=sid)
        return
    
    session = sessions[session_id]
    
    if session.state != 'waiting':
        await sio.emit('error', {'message': 'Game already started'}, room=sid)
        return
    
    player = Player(sid=sid, name=player_name, session_id=session_id)
    players[sid] = player
    session.players.append(player)
    
    await sio.enter_room(sid, session_id)
    await sio.emit('joined_session', {
        'player_name': player_name,
        'session_id': session_id
    }, room=sid)
    
    # Notify all players
    await sio.emit('player_joined', {
        'player_name': player_name,
        'total_players': len(session.players)
    }, room=session_id)
    print(f"Player {player_name} joined session {session_id}")


@sio.event
async def start_game(sid, data):
    """Host starts the game"""
    session_id = data.get('session_id')
    
    if session_id not in sessions:
        await sio.emit('error', {'message': 'Session not found'}, room=sid)
        return
    
    session = sessions[session_id]
    
    if session.host_sid != sid:
        await sio.emit('error', {'message': 'Only host can start the game'}, room=sid)
        return
    
    session.state = 'playing'
    await sio.emit('game_started', {}, room=session_id)
    
    # Start first question
    await next_question(session_id)


async def next_question(session_id: str):
    """Move to next question and start timer"""
    session = sessions[session_id]
    session.current_question_index += 1
    
    if session.current_question_index >= len(session.questions):
        # Game over
        await end_game(session_id)
        return
    
    question = session.questions[session.current_question_index]
    session.question_start_time = asyncio.get_event_loop().time()
    
    # Send question to all
    await sio.emit('new_question', {
        'question_number': session.current_question_index + 1,
        'total_questions': len(session.questions),
        'question': question.question,
        'answers': question.answers,
        'time_limit': 10
    }, room=session_id)
    
    # Start timer
    await countdown_timer(session_id, 10)


async def countdown_timer(session_id: str, duration: int):
    """Countdown timer for questions"""
    for remaining in range(duration, 0, -1):
        await sio.emit('timer_update', {'remaining': remaining}, room=session_id)
        await asyncio.sleep(1)
    
    # Time's up
    await sio.emit('time_up', {}, room=session_id)
    await asyncio.sleep(2)  # Show correct answer
    
    # Show results and move to next
    await show_question_results(session_id)


async def show_question_results(session_id: str):
    """Show results after question timeout"""
    session = sessions[session_id]
    question = session.questions[session.current_question_index]
    
    # Calculate scores and gather results
    results = []
    for player in session.players:
        player_answer = next((a for a in player.answers if a.question_index == session.current_question_index), None)
        if player_answer:
            results.append({
                'player_name': player.name,
                'answer_index': player_answer.answer_index,
                'is_correct': player_answer.answer_index == question.correct_answer,
                'time_taken': player_answer.time_taken,
                'points_earned': player_answer.points_earned
            })
    
    await sio.emit('question_results', {
        'correct_answer': question.correct_answer,
        'results': results,
        'leaderboard': get_leaderboard(session)
    }, room=session_id)
    
    await asyncio.sleep(3)
    await next_question(session_id)


@sio.event
async def submit_answer(sid, data):
    """Player submits an answer"""
    if sid not in players:
        return
    
    player = players[sid]
    session = sessions[player.session_id]
    
    answer_index = data.get('answer_index')
    
    # Check if already answered
    if any(a.question_index == session.current_question_index for a in player.answers):
        await sio.emit('error', {'message': 'Already answered'}, room=sid)
        return
    
    # Calculate time taken
    current_time = asyncio.get_event_loop().time()
    time_taken = current_time - session.question_start_time
    
    # Calculate score
    question = session.questions[session.current_question_index]
    is_correct = answer_index == question.correct_answer
    points = calculate_score(is_correct, time_taken, 10)
    
    # Save answer
    answer = Answer(
        question_index=session.current_question_index,
        answer_index=answer_index,
        time_taken=time_taken,
        points_earned=points
    )
    player.answers.append(answer)
    player.total_score += points
    
    await sio.emit('answer_submitted', {
        'points_earned': points,
        'is_correct': is_correct
    }, room=sid)
    
    # Notify host
    await sio.emit('player_answered', {
        'player_name': player.name
    }, room=session.host_sid)


async def end_game(session_id: str):
    """End the game and show final results"""
    session = sessions[session_id]
    session.state = 'finished'
    
    leaderboard = get_leaderboard(session)
    
    await sio.emit('game_over', {
        'leaderboard': leaderboard
    }, room=session_id)


def get_leaderboard(session: GameSession) -> List[dict]:
    """Get current leaderboard"""
    leaderboard = []
    for player in session.players:
        leaderboard.append({
            'name': player.name,
            'score': player.total_score,
            'correct_answers': sum(1 for a in player.answers 
                                  if a.answer_index == session.questions[a.question_index].correct_answer)
        })
    
    leaderboard.sort(key=lambda x: x['score'], reverse=True)
    return leaderboard