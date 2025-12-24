from pydantic import BaseModel
from typing import List, Optional


class Question(BaseModel):
    question: str
    answers: List[str]
    correct_answer: int  # Index of correct answer (0-3)


class Answer(BaseModel):
    question_index: int
    answer_index: int
    time_taken: float
    points_earned: float


class Player(BaseModel):
    sid: str
    name: str
    session_id: str
    total_score: float = 0.0
    answers: List[Answer] = []


class GameSession(BaseModel):
    session_id: str
    host_sid: str
    players: List[Player] = []
    questions: List[Question]
    current_question_index: int = -1
    state: str = 'waiting'  # waiting, playing, finished
    question_start_time: Optional[float] = None