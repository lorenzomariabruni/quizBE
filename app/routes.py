from fastapi import APIRouter, HTTPException, Form, File, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path
import json
import os
import uuid
from datetime import datetime
from typing import Optional
import asyncio
from app.image_optimizer import optimize_image, get_image_info

router = APIRouter()

# Base directory for quizzes
QUIZ_BASE_DIR = Path("quizzes")
QUIZ_BASE_DIR.mkdir(exist_ok=True)

# Locks for concurrent access
quiz_locks = {}

def get_quiz_lock(quiz_name: str):
    """Get or create a lock for a specific quiz"""
    if quiz_name not in quiz_locks:
        quiz_locks[quiz_name] = asyncio.Lock()
    return quiz_locks[quiz_name]


@router.post("/quizzes")
async def create_quiz(
    name: str = Form(...),
    title: str = Form(...),
    description: str = Form("")
):
    """Create a new quiz"""
    # Sanitize name
    quiz_name = name.lower().replace(" ", "-")
    quiz_dir = QUIZ_BASE_DIR / quiz_name
    
    if quiz_dir.exists():
        raise HTTPException(400, "Quiz with this name already exists")
    
    # Create directory structure
    quiz_dir.mkdir(parents=True)
    (quiz_dir / "images").mkdir()
    
    # Create metadata
    metadata = {
        "name": quiz_name,
        "title": title,
        "description": description,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "question_count": 0
    }
    
    with open(quiz_dir / "metadata.json", 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    # Create empty questions file
    with open(quiz_dir / "questions.json", 'w', encoding='utf-8') as f:
        json.dump({"questions": []}, f, indent=2)
    
    return {"message": "Quiz created successfully", "name": quiz_name}


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
                    quizzes.append(metadata)
    
    return {"quizzes": quizzes}


@router.get("/quizzes/{quiz_name}")
async def get_quiz(quiz_name: str):
    """Get quiz metadata and questions"""
    quiz_dir = QUIZ_BASE_DIR / quiz_name
    
    if not quiz_dir.exists():
        raise HTTPException(404, "Quiz not found")
    
    # Read metadata
    with open(quiz_dir / "metadata.json", 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    # Read questions
    with open(quiz_dir / "questions.json", 'r', encoding='utf-8') as f:
        questions_data = json.load(f)
    
    return {
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
    """
    Add a question to a quiz with image optimization.
    
    Images are automatically:
    - Resized to max 1200x900px (maintaining aspect ratio)
    - Compressed to ~85% quality JPEG
    - Optimized for progressive loading
    - Reduced to target max 500KB
    """
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
        
        # Process and optimize image if provided
        image_filename = None
        image_stats = None
        
        if question_type == "image" and image:
            # Read original image
            original_bytes = await image.read()
            
            # Get original image info
            original_info = get_image_info(original_bytes)
            
            print(f"📸 Original image: {original_info['width']}x{original_info['height']}, "
                  f"{original_info['size_kb']:.1f}KB, {original_info['format']}")
            
            # Optimize image
            optimized_bytes, ext = optimize_image(
                original_bytes,
                max_width=1200,
                max_height=900,
                quality=85,
                format='JPEG'  # Always convert to JPEG for consistency
            )
            
            optimized_info = get_image_info(optimized_bytes)
            
            print(f"✅ Optimized image: {optimized_info['width']}x{optimized_info['height']}, "
                  f"{optimized_info['size_kb']:.1f}KB")
            print(f"💾 Size reduction: {original_info['size_kb']:.1f}KB → {optimized_info['size_kb']:.1f}KB "
                  f"({100 * (1 - optimized_info['size_kb']/original_info['size_kb']):.1f}% smaller)")
            
            # Generate unique filename with correct extension
            image_filename = f"{uuid.uuid4()}{ext}"
            image_path = quiz_dir / "images" / image_filename
            
            # Save optimized image
            with open(image_path, 'wb') as f:
                f.write(optimized_bytes)
            
            # Store stats for response
            image_stats = {
                'original_size_kb': round(original_info['size_kb'], 2),
                'optimized_size_kb': round(optimized_info['size_kb'], 2),
                'reduction_percent': round(100 * (1 - optimized_info['size_kb']/original_info['size_kb']), 1),
                'dimensions': f"{optimized_info['width']}x{optimized_info['height']}"
            }
        
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
    
    response = {
        "message": "Question added successfully",
        "question_id": new_question["id"],
        "total_questions": len(data["questions"])
    }
    
    if image_stats:
        response["image_optimization"] = image_stats
    
    return response


@router.get("/quizzes/{quiz_name}/images/{image_name}")
async def get_image(quiz_name: str, image_name: str):
    """Serve an optimized image"""
    image_path = QUIZ_BASE_DIR / quiz_name / "images" / image_name
    
    if not image_path.exists():
        raise HTTPException(404, "Image not found")
    
    return FileResponse(image_path)


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
        question_to_delete = None
        for i, q in enumerate(data["questions"]):
            if q["id"] == question_id:
                question_to_delete = data["questions"].pop(i)
                break
        
        if not question_to_delete:
            raise HTTPException(404, "Question not found")
        
        # Delete associated image if exists
        if question_to_delete.get("image"):
            image_path = quiz_dir / "images" / question_to_delete["image"]
            if image_path.exists():
                os.remove(image_path)
        
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
        "message": "Question deleted successfully",
        "total_questions": len(data["questions"])
    }