import base64
import io
import random
import string
from datetime import datetime

import qrcode
import socketio
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_service import gemini_service
from app.config import settings
from app.database import Base, engine, get_db
from app.exporters import to_csv_bytes, to_pdf_bytes, to_xlsx_bytes
from app.file_parser import IMAGE_EXTENSIONS, parse_upload_to_text
from app.models import Answer, GameSession, Player, Quiz
from app.schemas import (
    QuizCreateRequest,
    QuizGenerateRequest,
    QuizResponse,
    SessionResponse,
    StartSessionRequest,
)
from app.socket_manager import quiz_socket_manager

fastapi_app = FastAPI(title=settings.app_name)
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@fastapi_app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@fastapi_app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@fastapi_app.post(f"{settings.api_prefix}/quizzes/generate")
async def generate_quiz(payload: QuizGenerateRequest):
    try:
        data = gemini_service.generate_quiz(
            topic_prompt=payload.topic_prompt,
            source_text="",
            question_count=payload.question_count,
            difficulty=payload.difficulty,
        )
        return data.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@fastapi_app.post(f"{settings.api_prefix}/quizzes/generate-from-file")
async def generate_quiz_from_file(
    file: UploadFile = File(...),
    topic_prompt: str = Form(default=""),
    question_count: int = Form(default=5),
    difficulty: str = Form(default="medium"),
):
    if question_count < 3 or question_count > 20:
        raise HTTPException(status_code=400, detail="question_count must be between 3 and 20")

    parsed_text, ext, raw = await parse_upload_to_text(file)
    source_text = parsed_text
    if ext in IMAGE_EXTENSIONS:
        mime = file.content_type or "image/png"
        source_text = gemini_service.extract_text_from_image(raw, mime)

    prompt = topic_prompt or "Generate a quiz from the uploaded content"
    try:
        data = gemini_service.generate_quiz(
            topic_prompt=prompt,
            source_text=source_text,
            question_count=question_count,
            difficulty=difficulty,
        )
        return data.model_dump() | {"source_text_preview": source_text[:500]}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@fastapi_app.post(f"{settings.api_prefix}/quizzes", response_model=QuizResponse)
async def save_quiz(payload: QuizCreateRequest, db: AsyncSession = Depends(get_db)):
    quiz = Quiz(
        title=payload.title,
        topic_prompt=payload.topic_prompt,
        source_text=payload.source_text,
        questions_json=[q.model_dump() for q in payload.questions],
    )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)
    return QuizResponse(
        id=quiz.id,
        title=quiz.title,
        topic_prompt=quiz.topic_prompt,
        source_text=quiz.source_text,
        questions=quiz.questions_json,
        created_at=quiz.created_at,
    )


@fastapi_app.get(f"{settings.api_prefix}/quizzes")
async def list_quizzes(db: AsyncSession = Depends(get_db)):
    quizzes = (await db.scalars(select(Quiz).order_by(Quiz.created_at.desc()))).all()
    return [
        {
            "id": q.id,
            "title": q.title,
            "topic_prompt": q.topic_prompt,
            "question_count": len(q.questions_json or []),
            "created_at": q.created_at,
        }
        for q in quizzes
    ]


@fastapi_app.post(f"{settings.api_prefix}/sessions/start", response_model=SessionResponse)
async def start_session(payload: StartSessionRequest, db: AsyncSession = Depends(get_db)):
    quiz = await db.scalar(select(Quiz).where(Quiz.id == payload.quiz_id))
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    pin = await _generate_unique_pin(db)
    session = GameSession(pin=pin, host_name=payload.host_name, quiz_id=payload.quiz_id, status="lobby")
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return SessionResponse(
        id=session.id,
        pin=session.pin,
        host_name=session.host_name,
        quiz_id=session.quiz_id,
        status=session.status,
        current_question_index=session.current_question_index,
        created_at=session.created_at,
    )


@fastapi_app.get(f"{settings.api_prefix}/sessions/{{pin}}")
async def get_session(pin: str, db: AsyncSession = Depends(get_db)):
    session = await db.scalar(select(GameSession).where(GameSession.pin == pin))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    players = (await db.scalars(select(Player).where(Player.session_id == session.id))).all()
    return {
        "id": session.id,
        "pin": session.pin,
        "host_name": session.host_name,
        "quiz_id": session.quiz_id,
        "status": session.status,
        "current_question_index": session.current_question_index,
        "players": [{"id": p.id, "name": p.name, "score": p.score} for p in players],
    }


@fastapi_app.get(f"{settings.api_prefix}/sessions/{{pin}}/leaderboard")
async def get_leaderboard(pin: str, db: AsyncSession = Depends(get_db)):
    session = await db.scalar(select(GameSession).where(GameSession.pin == pin))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    leaderboard = await quiz_socket_manager.compute_leaderboard(session.id, db)
    return leaderboard


@fastapi_app.get(f"{settings.api_prefix}/sessions/{{pin}}/qr")
async def get_qr(pin: str):
    join_url = f"{settings.cors_origin_list[0]}/join?pin={pin}"
    image = qrcode.make(join_url)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    return {"pin": pin, "join_url": join_url, "qr_data_url": f"data:image/png;base64,{encoded}"}


@fastapi_app.get(f"{settings.api_prefix}/sessions/{{pin}}/export/{{fmt}}")
async def export_results(pin: str, fmt: str, db: AsyncSession = Depends(get_db)):
    session = await db.scalar(select(GameSession).where(GameSession.pin == pin))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = await _build_export_rows(session.id, db)
    fmt = fmt.lower()
    if fmt == "csv":
        data = to_csv_bytes(rows)
        return StreamingResponse(io.BytesIO(data), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=results-{pin}.csv"})
    if fmt == "xlsx":
        data = to_xlsx_bytes(rows)
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=results-{pin}.xlsx"},
        )
    if fmt == "pdf":
        data = to_pdf_bytes(rows, title=f"Quiz Results {pin}")
        return StreamingResponse(io.BytesIO(data), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=results-{pin}.pdf"})

    raise HTTPException(status_code=400, detail="Supported formats: csv, xlsx, pdf")


@fastapi_app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": f"Internal server error: {exc}"})


async def _generate_unique_pin(db: AsyncSession) -> str:
    for _ in range(30):
        pin = "".join(random.choices(string.digits, k=6))
        existing = await db.scalar(select(GameSession).where(GameSession.pin == pin))
        if not existing:
            return pin
    raise HTTPException(status_code=500, detail="Could not generate unique game PIN")


async def _build_export_rows(session_id: str, db: AsyncSession) -> list[dict]:
    players = (await db.scalars(select(Player).where(Player.session_id == session_id))).all()
    rows: list[dict] = []
    for player in players:
        answers = (
            await db.scalars(select(Answer).where(Answer.session_id == session_id, Answer.player_id == player.id))
        ).all()
        rows.append(
            {
                "player_name": player.name,
                "score": player.score,
                "correct_answers": sum(1 for a in answers if a.is_correct == 1),
                "answers_submitted": len(answers),
            }
        )
    rows.sort(key=lambda item: item["score"], reverse=True)
    return rows


app: socketio.ASGIApp = socketio.ASGIApp(quiz_socket_manager.sio, other_asgi_app=fastapi_app)
