from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db, Quiz, Question
from schemas import QuizCreateRequest, QuizResponse, AIGenerateRequest, AIGeneratedQuestions, QuestionResponse
from services.ai_service import generate_quiz_from_text, generate_quiz_from_topic
from services.file_parser import parse_file
from config import settings
import json

router = APIRouter(prefix="/api/quiz", tags=["Quiz"])


@router.post("/create", response_model=QuizResponse)
async def create_quiz(quiz_data: QuizCreateRequest, db: Session = Depends(get_db)):
    """Create a new quiz with questions"""
    try:
        # Create quiz
        quiz = Quiz(
            title=quiz_data.title,
            description=quiz_data.description,
            created_by=quiz_data.created_by
        )
        db.add(quiz)
        db.flush()
        
        # Add questions
        for idx, q_data in enumerate(quiz_data.questions):
            question = Question(
                quiz_id=quiz.id,
                question_text=q_data.question_text,
                options=q_data.options,
                correct_answer=q_data.correct_answer,
                time_limit=q_data.time_limit,
                order=idx
            )
            db.add(question)
        
        db.commit()
        db.refresh(quiz)
        
        return QuizResponse(
            id=quiz.id,
            title=quiz.title,
            description=quiz.description,
            created_by=quiz.created_by,
            created_at=quiz.created_at,
            question_count=len(quiz_data.questions)
        )
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create quiz: {str(e)}")


@router.post("/generate/topic", response_model=AIGeneratedQuestions)
async def generate_from_topic(request: AIGenerateRequest):
    """Generate quiz questions from a topic using AI"""
    print(f"Received request: {request}")
    
    if not request.topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    
    try:
        result = generate_quiz_from_topic(
            topic=request.topic,
            num_questions=request.num_questions,
            difficulty=request.difficulty
        )
        return result
    
    except Exception as e:
        print(f"Error generating quiz: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate quiz: {str(e)}")


@router.post("/generate/file", response_model=AIGeneratedQuestions)
async def generate_from_file(
    file: UploadFile = File(...),
    num_questions: int = Form(10),
    difficulty: str = Form("medium")
):
    """Generate quiz questions from uploaded file using AI"""
    
    # Validate file size
    file_bytes = await file.read()
    if len(file_bytes) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE / (1024*1024)}MB"
        )
    
    # Parse file content
    try:
        content = parse_file(file.filename, file_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Limit content length for API
    if len(content) > 15000:
        content = content[:15000] + "..."
    
    # Generate questions
    try:
        result = generate_quiz_from_text(
            content=content,
            num_questions=num_questions,
            difficulty=difficulty
        )
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=List[QuizResponse])
async def list_quizzes(
    created_by: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List all quizzes, optionally filtered by creator"""
    query = db.query(Quiz)
    
    if created_by:
        query = query.filter(Quiz.created_by == created_by)
    
    quizzes = query.order_by(Quiz.created_at.desc()).limit(limit).all()
    
    return [
        QuizResponse(
            id=q.id,
            title=q.title,
            description=q.description,
            created_by=q.created_by,
            created_at=q.created_at,
            question_count=len(q.questions)
        )
        for q in quizzes
    ]


@router.get("/{quiz_id}", response_model=dict)
async def get_quiz(quiz_id: int, db: Session = Depends(get_db)):
    """Get quiz details with all questions"""
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    questions = db.query(Question).filter(Question.quiz_id == quiz_id).order_by(Question.order).all()
    
    return {
        "id": quiz.id,
        "title": quiz.title,
        "description": quiz.description,
        "created_by": quiz.created_by,
        "created_at": quiz.created_at,
        "questions": [
            {
                "id": q.id,
                "question_text": q.question_text,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "time_limit": q.time_limit,
                "order": q.order
            }
            for q in questions
        ]
    }


@router.put("/{quiz_id}/questions/{question_id}")
async def update_question(
    quiz_id: int,
    question_id: int,
    question_data: dict,
    db: Session = Depends(get_db)
):
    """Update a specific question"""
    question = db.query(Question).filter(
        Question.id == question_id,
        Question.quiz_id == quiz_id
    ).first()
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Update fields
    if "question_text" in question_data:
        question.question_text = question_data["question_text"]
    if "options" in question_data:
        question.options = question_data["options"]
    if "correct_answer" in question_data:
        question.correct_answer = question_data["correct_answer"]
    if "time_limit" in question_data:
        question.time_limit = question_data["time_limit"]
    
    db.commit()
    
    return {"message": "Question updated successfully"}


@router.delete("/{quiz_id}/questions/{question_id}")
async def delete_question(quiz_id: int, question_id: int, db: Session = Depends(get_db)):
    """Delete a specific question"""
    question = db.query(Question).filter(
        Question.id == question_id,
        Question.quiz_id == quiz_id
    ).first()
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    db.delete(question)
    db.commit()
    
    return {"message": "Question deleted successfully"}


@router.delete("/{quiz_id}")
async def delete_quiz(quiz_id: int, db: Session = Depends(get_db)):
    """Delete entire quiz"""
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    db.delete(quiz)
    db.commit()
    
    return {"message": "Quiz deleted successfully"}