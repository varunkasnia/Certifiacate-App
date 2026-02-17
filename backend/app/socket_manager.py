import time
from collections import defaultdict
from datetime import datetime
import logging

import socketio
from sqlalchemy import Select, func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Answer, GameSession, Player, Quiz

logger = logging.getLogger(__name__)


class QuizSocketManager:
    def __init__(self) -> None:
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=settings.cors_origin_list)
        self.runtime: dict[str, dict] = {}
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.sio.event
        async def connect(sid, environ, auth):
            await self.sio.emit("connected", {"sid": sid}, to=sid)

        @self.sio.event
        async def disconnect(sid):
            async with AsyncSessionLocal() as db:
                player = await db.scalar(select(Player).where(Player.sid == sid))
                if player:
                    player.sid = None
                    await db.commit()

        @self.sio.on("join_room")
        async def join_room(sid, payload):
            payload = payload or {}
            pin = str(payload.get("pin", payload.get("gamePin", ""))).strip()
            player_name = str(payload.get("player_name", payload.get("playerName", ""))).strip()
            role = str(payload.get("role", payload.get("mode", "player"))).strip().lower()
            logger.info("join_room sid=%s pin=%s role=%s player=%s", sid, pin, role, player_name)

            if len(pin) != 6:
                await self.sio.emit("error", {"detail": "Invalid PIN"}, to=sid)
                return

            async with AsyncSessionLocal() as db:
                session = await db.scalar(select(GameSession).where(GameSession.pin == pin))
                if not session:
                    await self.sio.emit("error", {"detail": "Game not found"}, to=sid)
                    return

                await self.sio.enter_room(sid, pin)

                if role == "host":
                    runtime = self.runtime.setdefault(pin, {})
                    runtime["host_sid"] = sid
                    await self.sio.emit("join_success", {"pin": pin, "role": "host"}, to=sid)
                    await self._emit_lobby(pin, db)
                    await self._emit_game_snapshot_to_sid(pin, session, sid, db)
                    return

                if len(player_name) < 2:
                    await self.sio.emit("error", {"detail": "Name too short"}, to=sid)
                    return

                player = await db.scalar(
                    select(Player).where(Player.session_id == session.id, func.lower(Player.name) == player_name.lower())
                )
                if player:
                    player.sid = sid
                else:
                    player = Player(session_id=session.id, sid=sid, name=player_name)
                    db.add(player)

                await db.commit()
                await self.sio.emit("join_success", {"pin": pin, "player_name": player_name, "role": "player"}, to=sid)
                await self._emit_lobby(pin, db)
                await self._emit_game_snapshot_to_sid(pin, session, sid, db)

        @self.sio.on("start_game")
        async def start_game(sid, payload):
            pin = str(payload.get("pin", "")).strip()
            async with AsyncSessionLocal() as db:
                session = await db.scalar(select(GameSession).where(GameSession.pin == pin))
                if not session:
                    await self.sio.emit("error", {"detail": "Game not found"}, to=sid)
                    return

                runtime = self.runtime.setdefault(pin, {})
                if runtime.get("host_sid") != sid:
                    await self.sio.emit("error", {"detail": "Only host can start"}, to=sid)
                    return

                quiz = await db.scalar(select(Quiz).where(Quiz.id == session.quiz_id))
                if not quiz:
                    await self.sio.emit("error", {"detail": "Quiz not found"}, to=sid)
                    return

                session.status = "in_progress"
                session.started_at = datetime.utcnow()
                session.current_question_index = 0
                runtime["question_started_at"] = time.time()
                runtime["answered_by_question"] = defaultdict(set)
                await db.commit()
                await self._emit_question(pin, session.current_question_index, quiz.questions_json)

        @self.sio.on("submit_answer")
        async def submit_answer(sid, payload):
            pin = str(payload.get("pin", "")).strip()
            selected_option_id = str(payload.get("selected_option_id", "")).strip()
            question_index = int(payload.get("question_index", -1))

            async with AsyncSessionLocal() as db:
                session = await db.scalar(select(GameSession).where(GameSession.pin == pin))
                if not session:
                    await self.sio.emit("error", {"detail": "Game not found"}, to=sid)
                    return

                if session.status != "in_progress":
                    await self.sio.emit("error", {"detail": "Game has not started"}, to=sid)
                    return

                player = await db.scalar(select(Player).where(Player.session_id == session.id, Player.sid == sid))
                if not player:
                    await self.sio.emit("error", {"detail": "Player not in session"}, to=sid)
                    return

                quiz = await db.scalar(select(Quiz).where(Quiz.id == session.quiz_id))
                if not quiz or question_index != session.current_question_index:
                    await self.sio.emit("error", {"detail": "Question mismatch"}, to=sid)
                    return

                runtime = self.runtime.setdefault(pin, {})
                answered = runtime.setdefault("answered_by_question", defaultdict(set))
                if player.id in answered[question_index]:
                    await self.sio.emit("answer_ack", {"accepted": False, "reason": "Already answered"}, to=sid)
                    return

                question = quiz.questions_json[question_index]
                is_correct = int(selected_option_id == question["correct_option_id"])
                elapsed = max(0.0, time.time() - runtime.get("question_started_at", time.time()))
                limit = float(question.get("time_limit_seconds", 20))
                response_time_ms = int(elapsed * 1000)

                points = 0
                if is_correct:
                    speed_ratio = max(0.0, min(1.0, (limit - elapsed) / limit))
                    points = int(600 + (speed_ratio * 400))

                player.score += points
                answered[question_index].add(player.id)
                db.add(
                    Answer(
                        session_id=session.id,
                        player_id=player.id,
                        question_index=question_index,
                        selected_option_id=selected_option_id,
                        is_correct=is_correct,
                        points_awarded=points,
                        response_time_ms=response_time_ms,
                    )
                )
                await db.commit()

                await self.sio.emit(
                    "answer_ack",
                    {
                        "accepted": True,
                        "is_correct": bool(is_correct),
                        "points": points,
                        "total_score": player.score,
                    },
                    to=sid,
                )

        @self.sio.on("next_question")
        async def next_question(sid, payload):
            pin = str(payload.get("pin", "")).strip()
            async with AsyncSessionLocal() as db:
                session = await db.scalar(select(GameSession).where(GameSession.pin == pin))
                if not session:
                    await self.sio.emit("error", {"detail": "Game not found"}, to=sid)
                    return

                runtime = self.runtime.setdefault(pin, {})
                if runtime.get("host_sid") != sid:
                    await self.sio.emit("error", {"detail": "Only host can advance"}, to=sid)
                    return

                quiz = await db.scalar(select(Quiz).where(Quiz.id == session.quiz_id))
                if not quiz:
                    await self.sio.emit("error", {"detail": "Quiz missing"}, to=sid)
                    return

                next_index = session.current_question_index + 1
                if next_index >= len(quiz.questions_json):
                    await self._finalize_game(pin, db, session)
                    return

                session.current_question_index = next_index
                runtime["question_started_at"] = time.time()
                await db.commit()
                await self._emit_question(pin, next_index, quiz.questions_json)

        @self.sio.on("end_game")
        async def end_game(sid, payload):
            pin = str(payload.get("pin", "")).strip()
            async with AsyncSessionLocal() as db:
                session = await db.scalar(select(GameSession).where(GameSession.pin == pin))
                if not session:
                    return
                runtime = self.runtime.setdefault(pin, {})
                if runtime.get("host_sid") != sid:
                    await self.sio.emit("error", {"detail": "Only host can end"}, to=sid)
                    return
                await self._finalize_game(pin, db, session)

    async def _emit_lobby(self, pin: str, db):
        session = await db.scalar(select(GameSession).where(GameSession.pin == pin))
        if not session:
            return
        players = (await db.scalars(select(Player).where(Player.session_id == session.id))).all()
        payload = {
            "pin": pin,
            "status": session.status,
            "players": [{"id": p.id, "name": p.name, "score": p.score} for p in players],
        }
        await self.sio.emit("lobby_update", payload, room=pin)
        logger.info("lobby_update pin=%s players=%s status=%s", pin, len(payload["players"]), session.status)

    async def _emit_question(self, pin: str, question_index: int, questions: list[dict]):
        q = questions[question_index]
        payload = {
            "question_index": question_index,
            "question": {
                "question": q["question"],
                "options": q["options"],
                "time_limit_seconds": q["time_limit_seconds"],
            },
        }
        await self.sio.emit("question_started", payload, room=pin)

    async def _emit_game_snapshot_to_sid(self, pin: str, session: GameSession, sid: str, db):
        if session.status == "in_progress" and session.current_question_index >= 0:
            quiz = await db.scalar(select(Quiz).where(Quiz.id == session.quiz_id))
            if quiz and session.current_question_index < len(quiz.questions_json):
                q = quiz.questions_json[session.current_question_index]
                await self.sio.emit(
                    "question_started",
                    {
                        "question_index": session.current_question_index,
                        "question": {
                            "question": q["question"],
                            "options": q["options"],
                            "time_limit_seconds": q["time_limit_seconds"],
                        },
                    },
                    to=sid,
                )
                logger.info("snapshot_question pin=%s sid=%s q_idx=%s", pin, sid, session.current_question_index)
            return

        if session.status == "finished":
            leaderboard = await self.compute_leaderboard(session.id, db)
            await self.sio.emit("game_ended", {"pin": pin, "leaderboard": leaderboard}, to=sid)
            logger.info("snapshot_finished pin=%s sid=%s", pin, sid)

    async def _finalize_game(self, pin: str, db, session: GameSession):
        session.status = "finished"
        session.ended_at = datetime.utcnow()
        await db.commit()
        leaderboard = await self.compute_leaderboard(session.id, db)
        await self.sio.emit("game_ended", {"pin": pin, "leaderboard": leaderboard}, room=pin)

    async def compute_leaderboard(self, session_id: str, db) -> list[dict]:
        players = (await db.scalars(select(Player).where(Player.session_id == session_id))).all()
        result = []
        for player in players:
            correct_count = await db.scalar(
                select(func.count(Answer.id)).where(
                    Answer.session_id == session_id,
                    Answer.player_id == player.id,
                    Answer.is_correct == 1,
                )
            )
            result.append(
                {
                    "player_id": player.id,
                    "player_name": player.name,
                    "score": player.score,
                    "correct_answers": int(correct_count or 0),
                }
            )
        result.sort(key=lambda item: item["score"], reverse=True)
        return result


quiz_socket_manager = QuizSocketManager()
