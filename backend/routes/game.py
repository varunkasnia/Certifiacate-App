from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db, GameSession, Player, Quiz, Question, Answer
from schemas import GameSessionCreate, GameSessionResponse, PlayerJoinRequest, PlayerResponse, SubmitAnswerRequest, LeaderboardEntry
from utils.helpers import generate_game_pin, generate_qr_code
from services.socket_manager import calculate_score
from services.certificate_service import generate_certificate_pdf, calculate_certificate_eligibility
from typing import List
from datetime import datetime
from pathlib import Path
import shutil
import uuid
import re

router = APIRouter(prefix="/api/game", tags=["Game"])
CERTIFICATE_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "uploads" / "certificate_templates"
CERTIFICATE_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/create", response_model=dict)
async def create_game_session(game_data: GameSessionCreate, db: Session = Depends(get_db)):
    """Create a new game session with unique PIN"""
    
    # Verify quiz exists
    quiz = db.query(Quiz).filter(Quiz.id == game_data.quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    # Generate unique PIN
    pin = generate_game_pin()
    while db.query(GameSession).filter(GameSession.pin == pin).first():
        pin = generate_game_pin()
    
    # Create game session
    game_session = GameSession(
        quiz_id=game_data.quiz_id,
        pin=pin,
        host_name=game_data.host_name,
        status="waiting"
    )
    
    db.add(game_session)
    db.commit()
    db.refresh(game_session)
    
    # Generate QR code for joining
    join_url = f"https://yourdomain.vercel.app/join?pin={pin}"
    qr_code = generate_qr_code(join_url)
    
    return {
        "id": game_session.id,
        "quiz_id": game_session.quiz_id,
        "quiz_title": quiz.title,
        "pin": game_session.pin,
        "qr_code": qr_code,
        "host_name": game_session.host_name,
        "status": game_session.status,
        "certificate_threshold": game_session.certificate_threshold,
        "certificate_template_uploaded": bool(game_session.certificate_template_path),
        "created_at": game_session.created_at
    }


@router.get("/history")
async def get_host_history(
    host_name: str,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get hosted game history for a host"""
    normalized_host = host_name.strip()
    if not normalized_host:
        raise HTTPException(status_code=400, detail="Host name is required")

    sessions = (
        db.query(GameSession)
        .filter(GameSession.host_name == normalized_host)
        .order_by(GameSession.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": session.id,
            "quiz_id": session.quiz_id,
            "quiz_title": session.quiz.title if session.quiz else "Untitled Quiz",
            "pin": session.pin,
            "status": session.status,
            "player_count": len(session.players),
            "created_at": session.created_at,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
        }
        for session in sessions
    ]


@router.delete("/history/{session_id}")
async def delete_host_history(
    session_id: int,
    host_name: str,
    db: Session = Depends(get_db)
):
    """Delete a hosted game from host history"""
    game_session = db.query(GameSession).filter(GameSession.id == session_id).first()

    if not game_session:
        raise HTTPException(status_code=404, detail="Hosted game not found")

    if game_session.host_name != host_name.strip():
        raise HTTPException(status_code=403, detail="You can only delete your own hosted games")

    db.delete(game_session)
    db.commit()

    return {"message": "Hosted game history deleted successfully"}


@router.post("/join", response_model=PlayerResponse)
async def join_game(player_data: PlayerJoinRequest, db: Session = Depends(get_db)):
    """Player joins a game session"""
    
    # Find game session
    game_session = db.query(GameSession).filter(GameSession.pin == player_data.pin).first()
    
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found. Check your PIN.")
    
    if game_session.status == "finished":
        raise HTTPException(status_code=400, detail="This game has already ended.")
    
    if game_session.status == "active":
        raise HTTPException(status_code=400, detail="This game has already started.")
    
    # Check if name already exists in this game
    existing_player = db.query(Player).filter(
        Player.game_session_id == game_session.id,
        Player.name == player_data.name
    ).first()
    
    if existing_player:
        raise HTTPException(status_code=400, detail="This name is already taken in this game.")
    
    # Create player
    player = Player(
        game_session_id=game_session.id,
        name=player_data.name,
        roll_number=(player_data.roll_number.strip() if player_data.roll_number else None),
        score=0
    )
    
    db.add(player)
    db.commit()
    db.refresh(player)
    
    return PlayerResponse(
        id=player.id,
        name=player.name,
        roll_number=player.roll_number,
        score=player.score,
        joined_at=player.joined_at
    )


@router.get("/{pin}/status")
async def get_game_status(pin: str, db: Session = Depends(get_db)):
    """Get current game status"""
    
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")
    
    players = db.query(Player).filter(Player.game_session_id == game_session.id).all()
    
    return {
        "id": game_session.id,
        "quiz_id": game_session.quiz_id,
        "pin": game_session.pin,
        "status": game_session.status,
        "current_question_index": game_session.current_question_index,
        "player_count": len(players),
        "players": [{"id": p.id, "name": p.name, "roll_number": p.roll_number, "score": p.score} for p in players]
    }


@router.post("/{pin}/start")
async def start_game(pin: str, db: Session = Depends(get_db)):
    """Start the game (host only)"""
    
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")
    
    if game_session.status != "waiting":
        raise HTTPException(status_code=400, detail="Game already started or finished")
    
    # Check if there are players
    player_count = db.query(Player).filter(Player.game_session_id == game_session.id).count()
    if player_count == 0:
        raise HTTPException(status_code=400, detail="Cannot start game with no players")
    
    game_session.status = "active"
    game_session.started_at = datetime.utcnow()
    game_session.current_question_index = 0
    
    db.commit()
    
    return {"message": "Game started successfully"}


@router.post("/answer/submit")
async def submit_answer(answer_data: SubmitAnswerRequest, db: Session = Depends(get_db)):
    """Submit player's answer to a question"""
    
    # Verify player exists
    player = db.query(Player).filter(Player.id == answer_data.player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Verify question exists
    question = db.query(Question).filter(Question.id == answer_data.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Check if already answered
    existing_answer = db.query(Answer).filter(
        Answer.player_id == answer_data.player_id,
        Answer.question_id == answer_data.question_id
    ).first()
    
    if existing_answer:
        raise HTTPException(status_code=400, detail="Already answered this question")
    
    # Check if correct
    is_correct = answer_data.answer == question.correct_answer
    
    # Calculate score
    points = calculate_score(is_correct, answer_data.time_taken, question.time_limit)
    
    # Create answer record
    answer = Answer(
        player_id=answer_data.player_id,
        question_id=answer_data.question_id,
        answer=answer_data.answer,
        is_correct=is_correct,
        time_taken=answer_data.time_taken,
        points_earned=points
    )
    
    db.add(answer)
    
    # Update player score
    player.score += points
    
    db.commit()
    
    return {
        "message": "Answer submitted successfully"
    }


@router.get("/{pin}/question/{question_id}/results")
async def get_question_results(pin: str, question_id: int, db: Session = Depends(get_db)):
    """Get per-question answer results for host view"""
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()

    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")

    question = db.query(Question).filter(
        Question.id == question_id,
        Question.quiz_id == game_session.quiz_id
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found for this game")

    players = db.query(Player).filter(Player.game_session_id == game_session.id).all()
    if not players:
        return {
            "question_id": question.id,
            "question_text": question.question_text,
            "correct_answer": question.correct_answer,
            "players": [],
            "summary": {
                "total_players": 0,
                "answered_count": 0,
                "correct_count": 0
            }
        }

    player_ids = [p.id for p in players]
    answers = db.query(Answer).filter(
        Answer.player_id.in_(player_ids),
        Answer.question_id == question.id
    ).all()
    answers_by_player = {a.player_id: a for a in answers}

    player_rows = []
    answered_count = 0
    correct_count = 0

    for p in players:
        answer = answers_by_player.get(p.id)
        if answer:
            answered_count += 1
            if answer.is_correct:
                correct_count += 1
            player_rows.append({
                "player_id": p.id,
                "name": p.name,
                "roll_number": p.roll_number,
                "answered": True,
                "answer": answer.answer,
                "is_correct": answer.is_correct,
                "time_taken": answer.time_taken,
                "points_earned": answer.points_earned
            })
        else:
            player_rows.append({
                "player_id": p.id,
                "name": p.name,
                "roll_number": p.roll_number,
                "answered": False,
                "answer": None,
                "is_correct": False,
                "time_taken": None,
                "points_earned": 0
            })

    return {
        "question_id": question.id,
        "question_text": question.question_text,
        "correct_answer": question.correct_answer,
        "players": player_rows,
        "summary": {
            "total_players": len(players),
            "answered_count": answered_count,
            "correct_count": correct_count
        }
    }


@router.get("/{pin}/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard(pin: str, db: Session = Depends(get_db)):
    """Get current leaderboard"""
    
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Get all players with their answers
    players = db.query(Player).filter(Player.game_session_id == game_session.id).all()
    
    leaderboard = []
    total_questions = db.query(Question).filter(Question.quiz_id == game_session.quiz_id).count()
    
    for player in players:
        correct_count = db.query(Answer).filter(
            Answer.player_id == player.id,
            Answer.is_correct == True
        ).count()
        
        leaderboard.append(LeaderboardEntry(
            player_id=player.id,
            name=player.name,
            score=player.score,
            correct_answers=correct_count,
            total_questions=total_questions
        ))
    
    # Sort by score
    leaderboard.sort(key=lambda x: x.score, reverse=True)
    
    return leaderboard


@router.post("/{pin}/end")
async def end_game(pin: str, db: Session = Depends(get_db)):
    """End the game"""
    
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game_session.status = "finished"
    game_session.ended_at = datetime.utcnow()
    
    db.commit()
    
    return {"message": "Game ended successfully"}


@router.get("/{pin}/results")
async def get_game_results(pin: str, db: Session = Depends(get_db)):
    """Get detailed game results"""
    
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")
    
    players = db.query(Player).filter(Player.game_session_id == game_session.id).all()
    questions = db.query(Question).filter(Question.quiz_id == game_session.quiz_id).order_by(Question.order).all()
    
    results = {
        "game_id": game_session.id,
        "quiz_title": game_session.quiz.title,
        "pin": game_session.pin,
        "host_name": game_session.host_name,
        "status": game_session.status,
        "started_at": game_session.started_at,
        "ended_at": game_session.ended_at,
        "total_questions": len(questions),
        "players": []
    }
    
    for player in players:
        answers = db.query(Answer).filter(Answer.player_id == player.id).all()
        correct_count = sum(1 for a in answers if a.is_correct)
        
        results["players"].append({
            "id": player.id,
            "name": player.name,
            "roll_number": player.roll_number,
            "score": player.score,
            "correct_answers": correct_count,
            "total_answers": len(answers),
            "accuracy": round((correct_count / len(questions)) * 100, 2) if questions else 0
        })
    
    # Sort by score
    results["players"].sort(key=lambda x: x["score"], reverse=True)
    
    return results


@router.get("/{pin}/certificate/settings")
async def get_certificate_settings(pin: str, db: Session = Depends(get_db)):
    """Get certificate settings configured for a game session."""
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")

    return {
        "pin": game_session.pin,
        "certificate_threshold": game_session.certificate_threshold or 75,
        "certificate_template_uploaded": bool(game_session.certificate_template_path)
    }


@router.post("/{pin}/certificate/settings")
async def update_certificate_settings(
    pin: str,
    certificate_threshold: int = Form(75),
    template_pdf: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    """Set certificate pass threshold and optionally upload certificate template PDF."""
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")

    if game_session.status != "waiting":
        raise HTTPException(status_code=400, detail="Certificate settings can only be changed before game starts")

    if certificate_threshold < 1 or certificate_threshold > 100:
        raise HTTPException(status_code=422, detail="Certificate threshold must be between 1 and 100")

    game_session.certificate_threshold = certificate_threshold

    if template_pdf:
        if template_pdf.content_type != "application/pdf":
            raise HTTPException(status_code=422, detail="Certificate template must be a PDF file")

        unique_name = f"{pin}_{uuid.uuid4().hex}.pdf"
        output_path = CERTIFICATE_TEMPLATES_DIR / unique_name

        with output_path.open("wb") as output_file:
            shutil.copyfileobj(template_pdf.file, output_file)

        game_session.certificate_template_path = str(output_path)

    db.commit()
    db.refresh(game_session)

    return {
        "pin": game_session.pin,
        "certificate_threshold": game_session.certificate_threshold or 75,
        "certificate_template_uploaded": bool(game_session.certificate_template_path),
        "message": "Certificate settings saved"
    }


@router.get("/{pin}/certificate/status/{player_id}")
async def get_player_certificate_status(pin: str, player_id: int, db: Session = Depends(get_db)):
    """Check if player is eligible for certificate download."""
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")

    player = db.query(Player).filter(
        Player.id == player_id,
        Player.game_session_id == game_session.id
    ).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found in this game")

    total_questions = db.query(Question).filter(Question.quiz_id == game_session.quiz_id).count()
    correct_answers = db.query(Answer).filter(
        Answer.player_id == player.id,
        Answer.is_correct == True
    ).count()

    threshold = game_session.certificate_threshold or 75
    eligibility = calculate_certificate_eligibility(correct_answers, total_questions, threshold)

    game_finished = game_session.status == "finished"
    template_uploaded = bool(game_session.certificate_template_path)

    return {
        "player_id": player.id,
        "player_name": player.name,
        "correct_answers": correct_answers,
        "total_questions": total_questions,
        "game_finished": game_finished,
        "template_uploaded": template_uploaded,
        **eligibility,
    }


@router.get("/{pin}/certificate/download/{player_id}")
async def download_player_certificate(pin: str, player_id: int, db: Session = Depends(get_db)):
    """Generate and download personalized certificate PDF for eligible players."""
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")

    if game_session.status != "finished":
        raise HTTPException(status_code=400, detail="Certificate is available only after game ends")

    if not game_session.certificate_template_path:
        raise HTTPException(status_code=404, detail="Host has not uploaded a certificate template")

    template_path = Path(game_session.certificate_template_path)
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Certificate template file not found")

    player = db.query(Player).filter(
        Player.id == player_id,
        Player.game_session_id == game_session.id
    ).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found in this game")

    total_questions = db.query(Question).filter(Question.quiz_id == game_session.quiz_id).count()
    correct_answers = db.query(Answer).filter(
        Answer.player_id == player.id,
        Answer.is_correct == True
    ).count()
    threshold = game_session.certificate_threshold or 75
    eligibility = calculate_certificate_eligibility(correct_answers, total_questions, threshold)

    if not eligibility["eligible"]:
        raise HTTPException(status_code=400, detail="You are not eligible for certificate")

    try:
        certificate_pdf = generate_certificate_pdf(str(template_path), player.name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate certificate: {str(exc)}")

    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", player.name.strip()) or "player"
    filename = f"certificate_{pin}_{safe_name}.pdf"

    return StreamingResponse(
        certificate_pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
