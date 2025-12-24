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
    print(f"📊 Current active sessions: {list(sessions.keys())}")
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
    
    print(f"\n{'='*60}")
    print(f"🎮 CREATE SESSION REQUEST")
    print(f"Session ID: {session_id}")
    print(f"Quiz Name: {quiz_name}")
    print(f"Host SID: {sid}")
    print(f"{'='*60}\n")
    
    try:
        questions = load_questions(quiz_name)
    except FileNotFoundError as e:
        print(f"❌ Error loading questions: {e}")
        await sio.emit('error', {'message': str(e)}, room=sid)
        return
    
    if not questions:
        print(f"❌ No questions found in quiz {quiz_name}")
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
    
    print(f"✅ Session created successfully!")
    print(f"📊 Active sessions: {list(sessions.keys())}")
    print(f"📝 Questions loaded: {len(questions)}\n")


@sio.event
async def join_session(sid, data):
    """Player joins a session"""
    session_id = data.get('session_id')
    player_name = data.get('player_name')
    
    print(f"\n{'='*60}")
    print(f"👤 JOIN SESSION REQUEST")
    print(f"Player Name: {player_name}")
    print(f"Session ID: {session_id}")
    print(f"Player SID: {sid}")
    print(f"📊 Active sessions: {list(sessions.keys())}")
    print(f"{'='*60}\n")
    
    if session_id not in sessions:
        print(f"❌ SESSION NOT FOUND: {session_id}")
        print(f"🔍 Available sessions: {list(sessions.keys())}")
        print(f"💡 Tip: Make sure the host has created the session first\n")
        await sio.emit('error', {'message': 'Session not found'}, room=sid)
        return
    
    session = sessions[session_id]
    print(f"✅ Session found: {session_id}")
    print(f"🎮 Quiz: {session.quiz_name}")
    print(f"📊 Current players: {[p.name for p in session.players]}")
    print(f"🔄 Session state: {session.state}")
    
    # Check if player already exists (reconnection)
    existing_player = None
    for p in session.players:
        if p.name == player_name:
            existing_player = p
            break
    
    if existing_player:
        print(f"🔄 RECONNECTION detected for {player_name}")
        
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
                'time_limit': 25,
                'already_answered': already_answered,
                'type': question.question_type,
                'image_url': image_url
            }, room=sid)
        
        print(f"✅ {player_name} successfully reconnected\n")
    else:
        if session.state != 'waiting':
            print(f"❌ Game already started, {player_name} cannot join\n")
            await sio.emit('error', {'message': 'Game already started'}, room=sid)
            return
        
        print(f"✨ NEW PLAYER joining: {player_name}")
        
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
        
        print(f"✅ {player_name} joined successfully")
        print(f"📊 Total players now: {len(session.players)}\n")


@sio.event
async def start_game(sid, data):
    """Host starts the game"""
    session_id = data.get('session_id')
    
    print(f"\n{'='*60}")
    print(f"🚀 START GAME REQUEST")
    print(f"Session ID: {session_id}")
    print(f"Requester SID: {sid}")
    print(f"{'='*60}\n")
    
    if session_id not in sessions:
        print(f"❌ Session {session_id} not found")
        await sio.emit('error', {'message': 'Session not found'}, room=sid)
        return
    
    session = sessions[session_id]
    
    if session.host_sid != sid:
        print(f"❌ Permission denied. Host SID: {session.host_sid}, Requester: {sid}")
        await sio.emit('error', {'message': 'Only host can start the game'}, room=sid)
        return
    
    print(f"✅ Starting game for session {session_id}")
    print(f"📊 Players: {[p.name for p in session.players]}")
    session.state = 'playing'
    
    # Emit game_started to all players
    await sio.emit('game_started', {}, room=session_id)
    print(f"📤 Emitted game_started to all players")
    
    # Start first question
    print(f"🎯 Starting first question...\n")
    await next_question(session_id)


async def next_question(session_id: str):
    """Move to next question and start timer"""
    if session_id not in sessions:
        print(f"❌ Session {session_id} not found in next_question")
        return
    
    session = sessions[session_id]
    session.current_question_index += 1
    
    print(f"\n📝 Question {session.current_question_index + 1}/{len(session.questions)}")
    
    if session.current_question_index >= len(session.questions):
        print(f"🏁 All questions completed, ending game\n")
        await end_game(session_id)
        return
    
    question = session.questions[session.current_question_index]
    session.question_start_time = asyncio.get_event_loop().time()
    
    print(f"❓ {question.question}")
    print(f"📝 Original answers: {question.answers}")
    
    # Shuffle answers and track the mapping
    original_answers = question.answers.copy()
    shuffled_indices = list(range(len(original_answers)))
    random.shuffle(shuffled_indices)
    
    shuffled_answers = [original_answers[i] for i in shuffled_indices]
    
    # Find new position of correct answer
    new_correct_index = shuffled_indices.index(question.correct_answer)
    
    print(f"🔀 Shuffled answers: {shuffled_answers}")
    print(f"✅ Correct answer: index {new_correct_index} ({shuffled_answers[new_correct_index]})")
    
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
        'time_limit': 25,
        'already_answered': False,
        'type': question.question_type,
        'image_url': image_url
    }
    
    print(f"📤 Emitting new_question to all players")
    await sio.emit('new_question', question_data, room=session_id)
    
    print(f"⏱️ Starting 10 second countdown\n")
    await countdown_timer(session_id, 25)


async def countdown_timer(session_id: str, duration: int):
    """Countdown timer for questions"""
    for remaining in range(duration, 0, -1):
        if session_id not in sessions:
            print(f"❌ Session ended during timer")
            return
        
        await sio.emit('timer_update', {'remaining': remaining}, room=session_id)
        await asyncio.sleep(1)
    
    print(f"⏰ Time's up!")
    await sio.emit('time_up', {}, room=session_id)
    await asyncio.sleep(2)
    
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
    
    print(f"\n📈 QUESTION RESULTS")
    print(f"Correct answer: {correct_index_shuffled}")
    
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
            status = "✅" if is_correct else "❌"
            print(f"{status} {player.name}: answer {player_answer.answer_index}, {player_answer.points_earned} points")
    
    leaderboard = get_leaderboard(session)
    
    await sio.emit('question_results', {
        'correct_answer': correct_index_shuffled,
        'results': results,
        'leaderboard': leaderboard
    }, room=session_id)
    
    print(f"⏳ Waiting 3 seconds before next question\n")
    await asyncio.sleep(3)
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
    
    print(f"📥 {player.name} submitted answer: {answer_index}")
    
    if any(a.question_index == session.current_question_index for a in player.answers):
        print(f"❌ {player.name} already answered this question")
        await sio.emit('error', {'message': 'Already answered'}, room=sid)
        return
    
    current_time = asyncio.get_event_loop().time()
    time_taken = current_time - session.question_start_time
    
    # Get shuffle data for this question
    shuffle_data = session.question_shuffles.get(session.current_question_index, {})
    correct_index_shuffled = shuffle_data.get('correct_index', session.questions[session.current_question_index].correct_answer)
    
    is_correct = answer_index == correct_index_shuffled
    points = calculate_score(is_correct, time_taken, 10)
    
    status = "✅" if is_correct else "❌"
    print(f"{status} {player.name}: correct={is_correct}, time={time_taken:.2f}s, points={points}")
    
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


async def end_game(session_id: str):
    """End the game and show final results"""
    if session_id not in sessions:
        return
    
    print(f"\n{'='*60}")
    print(f"🏁 GAME OVER - {session_id}")
    
    session = sessions[session_id]
    session.state = 'finished'
    
    leaderboard = get_leaderboard(session)
    
    print(f"\n🏆 FINAL LEADERBOARD:")
    for i, player_data in enumerate(leaderboard, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
        print(f"{medal} {i}. {player_data['name']}: {player_data['score']} points ({player_data['correct_answers']} correct)")
    
    print(f"{'='*60}\n")
    
    await sio.emit('game_over', {
        'leaderboard': leaderboard
    }, room=session_id)


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