import socketio
import asyncio
import random
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
    print(f"✅ Client connected: {sid}")
    await sio.emit('connection_established', {'sid': sid}, room=sid)


@sio.event
async def disconnect(sid):
    print(f"❌ Client disconnected: {sid}")
    if sid in players:
        player = players[sid]
        print(f"Player {player.name} disconnected but keeping in session for recovery")
        player.connected = False


@sio.event
async def create_session(sid, data):
    """Host creates a new game session"""
    session_id = data.get('session_id', 'QUIZ001')
    quiz_name = data.get('quiz_name')  # Optional: specific quiz to load
    
    print(f"🎮 Creating session {session_id} with quiz: {quiz_name}")
    
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
    
    # Initialize shuffle mapping
    session.question_shuffles = {}
    
    sessions[session_id] = session
    
    await sio.enter_room(sid, session_id)
    await sio.emit('session_created', {
        'session_id': session_id,
        'quiz_name': quiz_name,
        'total_questions': len(questions)
    }, room=sid)
    print(f"✅ Session created: {session_id} with {len(questions)} questions")


@sio.event
async def join_session(sid, data):
    """Player joins a session"""
    session_id = data.get('session_id')
    player_name = data.get('player_name')
    
    print(f"👤 Player {player_name} attempting to join session {session_id}")
    
    if session_id not in sessions:
        print(f"❌ Session {session_id} not found")
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
        print(f"🔄 Existing player {player_name} rejoining session {session_id}")
        
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
            
            # Get shuffled answers for this question
            shuffled_data = session.question_shuffles.get(session.current_question_index)
            if shuffled_data:
                shuffled_answers = shuffled_data['answers']
            else:
                shuffled_answers = question.answers
            
            # Build image URL if question has image
            image_url = None
            if question.question_type == 'image' and question.image and session.quiz_name:
                image_url = f"/api/quizzes/{session.quiz_name}/images/{question.image}"
            
            await sio.emit('new_question', {
                'question_number': session.current_question_index + 1,
                'total_questions': len(session.questions),
                'question': question.question,
                'answers': shuffled_answers,
                'time_limit': 10,
                'already_answered': already_answered,
                'type': question.question_type,
                'image_url': image_url
            }, room=sid)
        
        print(f"✅ Player {player_name} successfully reconnected")
    else:
        if session.state != 'waiting':
            print(f"❌ Game already started, cannot join")
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
        
        print(f"✅ Player {player_name} joined session {session_id}")


@sio.event
async def start_game(sid, data):
    """Host starts the game"""
    session_id = data.get('session_id')
    
    print(f"🚀 Received start_game request for session {session_id} from {sid}")
    
    if session_id not in sessions:
        print(f"❌ Session {session_id} not found")
        await sio.emit('error', {'message': 'Session not found'}, room=sid)
        return
    
    session = sessions[session_id]
    
    if session.host_sid != sid:
        print(f"❌ Only host can start the game. Host: {session.host_sid}, Requester: {sid}")
        await sio.emit('error', {'message': 'Only host can start the game'}, room=sid)
        return
    
    print(f"✅ Starting game for session {session_id}")
    session.state = 'playing'
    
    # Emit game_started to all players
    await sio.emit('game_started', {}, room=session_id)
    print(f"📤 Emitted game_started to room {session_id}")
    
    # Start first question
    print(f"🎯 Starting first question...")
    await next_question(session_id)


async def next_question(session_id: str):
    """Move to next question and start timer"""
    print(f"📝 next_question called for session {session_id}")
    
    if session_id not in sessions:
        print(f"❌ Session {session_id} not found in next_question")
        return
    
    session = sessions[session_id]
    session.current_question_index += 1
    
    print(f"Question index: {session.current_question_index}/{len(session.questions)}")
    
    if session.current_question_index >= len(session.questions):
        print(f"🏁 All questions completed, ending game")
        await end_game(session_id)
        return
    
    question = session.questions[session.current_question_index]
    session.question_start_time = asyncio.get_event_loop().time()
    
    print(f"❓ Question: {question.question}")
    print(f"Original answers: {question.answers}")
    
    # Shuffle answers and track the mapping
    original_answers = question.answers.copy()
    shuffled_indices = list(range(len(original_answers)))
    random.shuffle(shuffled_indices)
    
    shuffled_answers = [original_answers[i] for i in shuffled_indices]
    
    # Find new position of correct answer
    new_correct_index = shuffled_indices.index(question.correct_answer)
    
    print(f"Shuffled answers: {shuffled_answers}")
    print(f"Original correct index: {question.correct_answer}, New correct index: {new_correct_index}")
    
    # Store shuffle mapping for this question
    session.question_shuffles[session.current_question_index] = {
        'answers': shuffled_answers,
        'original_to_shuffled': shuffled_indices,
        'correct_index': new_correct_index
    }
    
    # Build image URL if question has image
    image_url = None
    if question.question_type == 'image' and question.image and session.quiz_name:
        image_url = f"/api/quizzes/{session.quiz_name}/images/{question.image}"
    
    question_data = {
        'question_number': session.current_question_index + 1,
        'total_questions': len(session.questions),
        'question': question.question,
        'answers': shuffled_answers,
        'time_limit': 10,
        'already_answered': False,
        'type': question.question_type,
        'image_url': image_url
    }
    
    print(f"📤 Emitting new_question to room {session_id}")
    await sio.emit('new_question', question_data, room=session_id)
    
    print(f"⏱️ Starting countdown timer")
    await countdown_timer(session_id, 10)


async def countdown_timer(session_id: str, duration: int):
    """Countdown timer for questions"""
    print(f"⏱️ Timer started for {duration} seconds")
    
    for remaining in range(duration, 0, -1):
        if session_id not in sessions:
            print(f"❌ Session ended during timer")
            return
        
        await sio.emit('timer_update', {'remaining': remaining}, room=session_id)
        await asyncio.sleep(1)
    
    print(f"⏰ Time's up!")
    await sio.emit('time_up', {}, room=session_id)
    await asyncio.sleep(2)
    
    print(f"📊 Showing question results")
    await show_question_results(session_id)


async def show_question_results(session_id: str):
    """Show results after question timeout"""
    if session_id not in sessions:
        return
    
    session = sessions[session_id]
    question = session.questions[session.current_question_index]
    
    # Get shuffle data for this question
    shuffle_data = session.question_shuffles.get(session.current_question_index, {})
    correct_index_shuffled = shuffle_data.get('correct_index', question.correct_answer)
    
    print(f"📈 Calculating results. Correct answer index: {correct_index_shuffled}")
    
    results = []
    for player in session.players:
        player_answer = next((a for a in player.answers if a.question_index == session.current_question_index), None)
        if player_answer:
            is_correct = player_answer.answer_index == correct_index_shuffled
            results.append({
                'player_name': player.name,
                'answer_index': player_answer.answer_index,
                'is_correct': is_correct,
                'time_taken': player_answer.time_taken,
                'points_earned': player_answer.points_earned
            })
            print(f"Player {player.name}: answer={player_answer.answer_index}, correct={is_correct}, points={player_answer.points_earned}")
    
    leaderboard = get_leaderboard(session)
    
    await sio.emit('question_results', {
        'correct_answer': correct_index_shuffled,
        'results': results,
        'leaderboard': leaderboard
    }, room=session_id)
    
    print(f"✅ Results sent, waiting 3 seconds before next question")
    await asyncio.sleep(3)
    
    print(f"➡️ Moving to next question")
    await next_question(session_id)


@sio.event
async def submit_answer(sid, data):
    """Player submits an answer"""
    if sid not in players:
        print(f"❌ Player {sid} not found")
        return
    
    player = players[sid]
    session = sessions[player.session_id]
    
    answer_index = data.get('answer_index')
    
    print(f"📥 Player {player.name} submitted answer: {answer_index}")
    
    if any(a.question_index == session.current_question_index for a in player.answers):
        print(f"❌ Player already answered this question")
        await sio.emit('error', {'message': 'Already answered'}, room=sid)
        return
    
    current_time = asyncio.get_event_loop().time()
    time_taken = current_time - session.question_start_time
    
    # Get shuffle data for this question
    shuffle_data = session.question_shuffles.get(session.current_question_index, {})
    correct_index_shuffled = shuffle_data.get('correct_index', session.questions[session.current_question_index].correct_answer)
    
    is_correct = answer_index == correct_index_shuffled
    points = calculate_score(is_correct, time_taken, 10)
    
    print(f"✓ Answer evaluation: correct={is_correct}, time={time_taken:.2f}s, points={points}")
    
    answer = Answer(
        question_index=session.current_question_index,
        answer_index=answer_index,
        time_taken=time_taken,
        points_earned=points
    )
    player.answers.append(answer)
    player.total_score += points
    
    # DON'T send is_correct to player - only send points and confirmation
    await sio.emit('answer_submitted', {
        'points_earned': points
    }, room=sid)
    
    await sio.emit('player_answered', {
        'player_name': player.name
    }, room=session.host_sid)
    
    print(f"✅ Answer recorded for {player.name}")


async def end_game(session_id: str):
    """End the game and show final results"""
    if session_id not in sessions:
        return
    
    print(f"🏁 Ending game for session {session_id}")
    
    session = sessions[session_id]
    session.state = 'finished'
    
    leaderboard = get_leaderboard(session)
    
    await sio.emit('game_over', {
        'leaderboard': leaderboard
    }, room=session_id)
    
    print(f"✅ Game over sent to all players")


def get_leaderboard(session: GameSession) -> List[dict]:
    """Get current leaderboard"""
    leaderboard = []
    for player in session.players:
        # Get shuffle data to correctly count correct answers
        correct_count = 0
        for answer in player.answers:
            shuffle_data = session.question_shuffles.get(answer.question_index, {})
            correct_index = shuffle_data.get('correct_index', session.questions[answer.question_index].correct_answer)
            if answer.answer_index == correct_index:
                correct_count += 1
        
        leaderboard.append({
            'name': player.name,
            'score': player.total_score,
            'correct_answers': correct_count
        })
    
    leaderboard.sort(key=lambda x: x['score'], reverse=True)
    return leaderboard