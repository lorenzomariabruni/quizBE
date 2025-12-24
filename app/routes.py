from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List, Optional
import os
import json
import uuid
from datetime import datetime
import shutil
from pathlib import Path
import asyncio
from fastapi.responses import FileResponse

router = APIRouter()

# Base directory for quizzes
QUIZ_BASE_DIR = Path("quizzes")
QUIZ_BASE_DIR.mkdir(exist_ok=True)

# Lock per gestire la concorrenza
quiz_locks = {}

def get_quiz_lock(quiz_name: str):
    """Get or create a lock for a specific quiz"""
    if quiz_name not in quiz_locks:
        quiz_locks[quiz_name] = asyncio.Lock()
    return quiz_locks[quiz_name]

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    from app.socket_manager import sessions
    return {
        "status": "healthy",
        "version": "1.0.0",
        "active_sessions": len(sessions),
        "total_players": sum(len(s.players) for s in sessions.values())
    }

@router.get("/quizzes")
async def list_quizzes():
    """List all available quizzes"""
    quizzes = []
    
    for quiz_dir in QUIZ_BASE_DIR.iterdir():
        if quiz_dir.is_dir():
            metadata_file = quiz_dir / "metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    quizzes.append({
                        "name": quiz_dir.name,
                        "title": metadata.get("title", quiz_dir.name),
                        "description": metadata.get("description", ""),
                        "question_count": metadata.get("question_count", 0),
                        "created_at": metadata.get("created_at", ""),
                        "updated_at": metadata.get("updated_at", "")
                    })
    
    return {"quizzes": quizzes}

@router.post("/quizzes")
async def create_quiz(
    name: str = Form(...),
    title: str = Form(...),
    description: str = Form("")
):
    """Create a new quiz"""
    # Sanitize name
    safe_name = "".join(c for c in name if c.isalnum() or c in ('-', '_')).lower()
    
    if not safe_name:
        raise HTTPException(400, "Invalid quiz name")
    
    quiz_dir = QUIZ_BASE_DIR / safe_name
    
    if quiz_dir.exists():
        raise HTTPException(400, "Quiz already exists")
    
    # Create directory structure
    quiz_dir.mkdir(parents=True)
    (quiz_dir / "images").mkdir()
    
    # Create metadata
    metadata = {
        "title": title,
        "description": description,
        "question_count": 0,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    with open(quiz_dir / "metadata.json", 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    # Create empty questions file
    with open(quiz_dir / "questions.json", 'w', encoding='utf-8') as f:
        json.dump({"questions": []}, f, indent=2, ensure_ascii=False)
    
    return {
        "name": safe_name,
        "message": "Quiz created successfully"
    }

@router.get("/quizzes/{quiz_name}")
async def get_quiz(quiz_name: str):
    """Get quiz details and questions"""
    quiz_dir = QUIZ_BASE_DIR / quiz_name
    
    if not quiz_dir.exists():
        raise HTTPException(404, "Quiz not found")
    
    # Read metadata
    metadata_file = quiz_dir / "metadata.json"
    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    # Read questions
    questions_file = quiz_dir / "questions.json"
    with open(questions_file, 'r', encoding='utf-8') as f:
        questions_data = json.load(f)
    
    return {
        "name": quiz_name,
        **metadata,
        "questions": questions_data["questions"]
    }

@router.post("/quizzes/{quiz_name}/questions")
async def add_question(
    quiz_name: str,
    question_text: str = Form(...),
    answer_0: str = Form(...),
    answer_1: str = Form(...),
    answer_2: str = Form(...),
    answer_3: str = Form(...),
    correct_answer: int = Form(...),
    question_type: str = Form("text"),  # "text" or "image"
    image: Optional[UploadFile] = File(None)
):
    """Add a question to a quiz (with concurrency support)"""
    quiz_dir = QUIZ_BASE_DIR / quiz_name
    
    if not quiz_dir.exists():
        raise HTTPException(404, "Quiz not found")
    
    if correct_answer not in [0, 1, 2, 3]:
        raise HTTPException(400, "correct_answer must be between 0 and 3")
    
    # Use lock to prevent concurrent writes
    async with get_quiz_lock(quiz_name):
        # Read current questions
        questions_file = quiz_dir / "questions.json"
        with open(questions_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Process image if provided
        image_filename = None
        if question_type == "image" and image:
            # Generate unique filename
            ext = os.path.splitext(image.filename)[1]
            image_filename = f"{uuid.uuid4()}{ext}"
            image_path = quiz_dir / "images" / image_filename
            
            # Save image
            with open(image_path, 'wb') as f:
                content = await image.read()
                f.write(content)
        
        # Create question
        new_question = {
            "id": str(uuid.uuid4()),
            "question": question_text,
            "answers": [answer_0, answer_1, answer_2, answer_3],
            "correct_answer": correct_answer,
            "type": question_type,
            "image": image_filename if image_filename else None
        }
        
        data["questions"].append(new_question)
        
        # Write back
        with open(questions_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Update metadata
        metadata_file = quiz_dir / "metadata.json"
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        metadata["question_count"] = len(data["questions"])
        metadata["updated_at"] = datetime.utcnow().isoformat()
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    return {
        "message": "Question added successfully",
        "question_id": new_question["id"],
        "total_questions": len(data["questions"])
    }

@router.delete("/quizzes/{quiz_name}/questions/{question_id}")
async def delete_question(quiz_name: str, question_id: str):
    """Delete a question from a quiz"""
    quiz_dir = QUIZ_BASE_DIR / quiz_name
    
    if not quiz_dir.exists():
        raise HTTPException(404, "Quiz not found")
    
    async with get_quiz_lock(quiz_name):
        questions_file = quiz_dir / "questions.json"
        with open(questions_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Find and remove question
        question_to_remove = None
        for q in data["questions"]:
            if q.get("id") == question_id:
                question_to_remove = q
                break
        
        if not question_to_remove:
            raise HTTPException(404, "Question not found")
        
        # Delete image if exists
        if question_to_remove.get("image"):
            image_path = quiz_dir / "images" / question_to_remove["image"]
            if image_path.exists():
                image_path.unlink()
        
        data["questions"].remove(question_to_remove)
        
        # Write back
        with open(questions_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Update metadata
        metadata_file = quiz_dir / "metadata.json"
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        metadata["question_count"] = len(data["questions"])
        metadata["updated_at"] = datetime.utcnow().isoformat()
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    return {"message": "Question deleted successfully"}

@router.get("/quizzes/{quiz_name}/images/{image_name}")
async def get_image(quiz_name: str, image_name: str):
    """Get an image from a quiz"""
    image_path = QUIZ_BASE_DIR / quiz_name / "images" / image_name
    
    if not image_path.exists():
        raise HTTPException(404, "Image not found")
    
    return FileResponse(image_path)

@router.delete("/quizzes/{quiz_name}")
async def delete_quiz(quiz_name: str):
    """Delete a quiz and all its data"""
    quiz_dir = QUIZ_BASE_DIR / quiz_name
    
    if not quiz_dir.exists():
        raise HTTPException(404, "Quiz not found")
    
    async with get_quiz_lock(quiz_name):
        shutil.rmtree(quiz_dir)
    
    # Remove lock
    if quiz_name in quiz_locks:
        del quiz_locks[quiz_name]
    
    return {"message": "Quiz deleted successfully"}