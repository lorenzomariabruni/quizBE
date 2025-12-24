import json
from typing import List
from app.models import Question


def calculate_score(is_correct: bool, time_taken: float, time_limit: int = 10) -> float:
    """
    Calculate score based on correctness and speed.
    
    Formula:
    - Correct answer: 1000 * (1 - time_taken/time_limit)
      Fast correct = high score (max 1000 points)
    - Wrong answer: -500 * (1 - time_taken/time_limit)
      Fast wrong = heavy penalty (max -500 points)
    """
    if time_taken > time_limit:
        return 0.0
    
    speed_factor = 1 - (time_taken / time_limit)
    
    if is_correct:
        # Correct: 100 to 1000 points based on speed
        return 100 + (900 * speed_factor)
    else:
        # Wrong: 0 to -500 penalty based on speed
        return -(500 * speed_factor)


def load_questions(file_path: str = "questions.json") -> List[Question]:
    """
    Load questions from JSON file.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [Question(**q) for q in data['questions']]
    except FileNotFoundError:
        # Return default questions if file not found
        return get_default_questions()


def get_default_questions() -> List[Question]:
    """Return default questions for testing"""
    return [
        Question(
            question="Qual è la capitale dell'Italia?",
            answers=["Milano", "Roma", "Napoli", "Firenze"],
            correct_answer=1
        ),
        Question(
            question="Quanti sono i continenti?",
            answers=["5", "6", "7", "8"],
            correct_answer=2
        ),
        Question(
            question="Chi ha dipinto la Gioconda?",
            answers=["Michelangelo", "Raffaello", "Leonardo da Vinci", "Caravaggio"],
            correct_answer=2
        ),
        Question(
            question="Qual è il pianeta più grande del sistema solare?",
            answers=["Terra", "Marte", "Saturno", "Giove"],
            correct_answer=3
        ),
        Question(
            question="In che anno è caduto il muro di Berlino?",
            answers=["1985", "1989", "1991", "1995"],
            correct_answer=1
        )
    ]