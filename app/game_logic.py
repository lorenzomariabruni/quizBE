import json
from typing import List
from app.models import Question
from pathlib import Path

def calculate_score(is_correct: bool, time_taken: float, time_limit: float) -> float:
    """
    Calculate score based on correctness and speed.
    
    Correct answer: 100-1000 points (based on speed)
    Wrong answer: 0 to -500 points penalty (faster = more penalty)
    """
    # Calculate speed factor (1 = instant, 0 = timeout)
    speed_factor = max(0, 1 - (time_taken / time_limit))
    
    if is_correct:
        # Correct: 100 base + up to 900 bonus
        return 100 + (900 * speed_factor)
    else:
        # Wrong: up to -500 penalty (faster wrong = more penalty)
        return -(500 * speed_factor)

def load_questions(quiz_name: str = None) -> List[Question]:
    """
    Load questions from a quiz.
    If quiz_name is provided, load from quizzes/{quiz_name}/questions.json
    Otherwise, load from legacy questions.json
    """
    if quiz_name:
        # Load from specific quiz
        quiz_path = Path("quizzes") / quiz_name / "questions.json"
        if not quiz_path.exists():
            raise FileNotFoundError(f"Quiz '{quiz_name}' not found")
    else:
        # Load from legacy file
        quiz_path = Path("questions.json")
        if not quiz_path.exists():
            raise FileNotFoundError("questions.json not found")
    
    with open(quiz_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    questions = []
    for q in data.get('questions', []):
        questions.append(Question(
            question=q['question'],
            answers=q['answers'],
            correct_answer=q['correct_answer'],
            question_type=q.get('type', 'text'),
            image=q.get('image')
        ))
    
    return questions