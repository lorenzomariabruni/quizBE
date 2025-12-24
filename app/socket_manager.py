import socketio
import asyncio
from typing import Dict, List
from app.models import GameSession, Player, Question, Answer
from app.game_logic import calculate_score, load_questions

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
)

# In-memory storage
sessions: Dict[str, GameSession] = {}
players: Dict[str, Player] = {}  # sid -> Player
player_sessions: Dict[str, str] = {}  # player_name -> session_id


@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    await sio.emit('connection_established', {'sid': sid}, room=sid)


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")
    if sid in players:
        player = players[sid]
        print(f"Player {player.name} disconnected but keeping in session for recovery")
        player.connected = False


@sio.event
async def create_session(sid, data):
    """Host creates a new game session"""
    session_id = data.get('session_id', 'QUIZ001')
    quiz_name = data.get('quiz_name')  # Optional: specific quiz to load
    
    try:
        questions = load_questions(quiz_name)
    except FileNotFoundError as e:
        await sio.emit('error', {'message': str(e)}, room=sid)
        return
    
    if not questions:
        await sio.emit('error', {'message': 'No questions found in quiz'}, room=sid)
        return
    
    session = GameSession(
        session_id=session_id,
        host_sid=sid,
        quiz_name=quiz_name,
        questions=questions,
        current_question_index=-1,
        state='waiting'
    )
    sessions[session_id] = session
    
    await sio.enter_room(sid, session_id)
    await sio.emit('session_created', {
        'session_id': session_id,
        'quiz_name': quiz_name,
        'total_questions': len(questions)
    }, room=sid)
    print(f"Session created: {session_id} with quiz: {quiz_name}")


@sio.event
async def join_session(sid, data):
    """Player joins a session"""
    session_id = data.get('session_id')
    player_name = data.get('player_name')
    
    if session_id not in sessions:
        await sio.emit('error', {'message': 'Session not found'}, room=sid)
        return
    
    session = sessions[session_id]
    
    # Check if player already exists (reconnection)
    existing_player = None
    for p in session.players:
        if p.name == player_name:
            existing_player = p
            break
    
    if existing_player:
        print(f"Existing player {player_name} rejoining session {session_id}")
        
        old_sid = existing_player.sid
        if old_sid in players:
            del players[old_sid]
        
        existing_player.sid = sid
        existing_player.connected = True
        players[sid] = existing_player
        
        await sio.enter_room(sid, session_id)
        
        await sio.emit('joined_session', {
            'player_name': player_name,
            'session_id': session_id,
            'reconnected': True,
            'game_state': session.state,
            'total_score': existing_player.total_score
        }, room=sid)
        
        if session.state == 'playing' and session.current_question_index >= 0:
            question = session.questions[session.current_question_index]
            already_answered = any(
                a.question_index == session.current_question_index 
                for a in existing_player.answers
            )
            
            # Build image URL if question has image
            image_url = None
            if question.question_type == 'image' and question.image and session.quiz_name:
                image_url = f"/api/quizzes/{session.quiz_name}/images/{question.image}"
            
            await sio.emit('new_question', {
                'question_number': session.current_question_index + 1,
                'total_questions': len(session.questions),
                'question': question.question,
                'answers': question.answers,
                'time_limit': 10,
                'already_answered': already_answered,
                'type': question.question_type,
                'image_url': image_url
            }, room=sid)
        
        print(f"Player {player_name} successfully reconnected")
    else:
        if session.state != 'waiting':
            await sio.emit('error', {'message': 'Game already started'}, room=sid)
            return
        
        player = Player(sid=sid, name=player_name, session_id=session_id, connected=True)
        players[sid] = player
        session.players.append(player)
        player_sessions[player_name] = session_id
        
        await sio.enter_room(sid, session_id)
        await sio.emit('joined_session', {
            'player_name': player_name,
            'session_id': session_id,
            'reconnected': False,
            'game_state': session.state
        }, room=sid)
        
        await sio.emit('player_joined', {
            'player_name': player_name,
            'total_players': len([p for p in session.players if p.connected])
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
    
    await next_question(session_id)


async def next_question(session_id: str):
    """Move to next question and start timer"""
    session = sessions[session_id]
    session.current_question_index += 1
    
    if session.current_question_index >= len(session.questions):
        await end_game(session_id)
        return
    
    question = session.questions[session.current_question_index]
    session.question_start_time = asyncio.get_event_loop().time()
    
    # Build image URL if question has image
    image_url = None
    if question.question_type == 'image' and question.image and session.quiz_name:
        image_url = f"/api/quizzes/{session.quiz_name}/images/{question.image}"
    
    await sio.emit('new_question', {
        'question_number': session.current_question_index + 1,
        'total_questions': len(session.questions),
        'question': question.question,
        'answers': question.answers,
        'time_limit': 10,
        'already_answered': False,
        'type': question.question_type,
        'image_url': image_url
    }, room=session_id)
    
    await countdown_timer(session_id, 10)


async def countdown_timer(session_id: str, duration: int):
    """Countdown timer for questions"""
    for remaining in range(duration, 0, -1):
        await sio.emit('timer_update', {'remaining': remaining}, room=session_id)
        await asyncio.sleep(1)
    
    await sio.emit('time_up', {}, room=session_id)
    await asyncio.sleep(2)
    
    await show_question_results(session_id)


async def show_question_results(session_id: str):
    """Show results after question timeout"""
    session = sessions[session_id]
    question = session.questions[session.current_question_index]
    
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
    
    if any(a.question_index == session.current_question_index for a in player.answers):
        await sio.emit('error', {'message': 'Already answered'}, room=sid)
        return
    
    current_time = asyncio.get_event_loop().time()
    time_taken = current_time - session.question_start_time
    
    question = session.questions[session.current_question_index]
    is_correct = answer_index == question.correct_answer
    points = calculate_score(is_correct, time_taken, 10)
    
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