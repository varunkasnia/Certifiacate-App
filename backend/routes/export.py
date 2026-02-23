from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db, GameSession, Player, Question, Answer
from services.export_service import (
    generate_csv,
    generate_excel,
    generate_pdf,
    prepare_game_data_for_export
)

router = APIRouter(prefix="/api/export", tags=["Export"])


@router.get("/{pin}/csv")
async def export_csv(pin: str, db: Session = Depends(get_db)):
    """Export game results as CSV"""
    
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Get all related data
    players = db.query(Player).filter(Player.game_session_id == game_session.id).all()
    questions = db.query(Question).filter(Question.quiz_id == game_session.quiz_id).all()
    
    # Get all answers
    player_ids = [p.id for p in players]
    answers = db.query(Answer).filter(Answer.player_id.in_(player_ids)).all()
    
    # Prepare data
    game_data = prepare_game_data_for_export(game_session, players, questions, answers)
    
    # Generate CSV
    csv_buffer = generate_csv(game_data)
    
    return StreamingResponse(
        csv_buffer,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=quiz_results_{pin}.csv"
        }
    )


@router.get("/{pin}/excel")
async def export_excel(pin: str, db: Session = Depends(get_db)):
    """Export game results as Excel"""
    
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Get all related data
    players = db.query(Player).filter(Player.game_session_id == game_session.id).all()
    questions = db.query(Question).filter(Question.quiz_id == game_session.quiz_id).all()
    
    # Get all answers
    player_ids = [p.id for p in players]
    answers = db.query(Answer).filter(Answer.player_id.in_(player_ids)).all()
    
    # Prepare data
    game_data = prepare_game_data_for_export(game_session, players, questions, answers)
    
    # Generate Excel
    excel_buffer = generate_excel(game_data)
    
    return StreamingResponse(
        excel_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=quiz_results_{pin}.xlsx"
        }
    )


@router.get("/{pin}/pdf")
async def export_pdf(pin: str, db: Session = Depends(get_db)):
    """Export game results as PDF"""
    
    game_session = db.query(GameSession).filter(GameSession.pin == pin).first()
    
    if not game_session:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Get all related data
    players = db.query(Player).filter(Player.game_session_id == game_session.id).all()
    questions = db.query(Question).filter(Question.quiz_id == game_session.quiz_id).all()
    
    # Get all answers
    player_ids = [p.id for p in players]
    answers = db.query(Answer).filter(Answer.player_id.in_(player_ids)).all()
    
    # Prepare data
    game_data = prepare_game_data_for_export(game_session, players, questions, answers)
    
    # Generate PDF
    pdf_buffer = generate_pdf(game_data)
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=quiz_results_{pin}.pdf"
        }
    )
