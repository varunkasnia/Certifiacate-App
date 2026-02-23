from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float, JSON, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=settings.DEBUG
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Quiz(Base):
    __tablename__ = "quizzes"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    questions = relationship("Question", back_populates="quiz", cascade="all, delete-orphan")
    game_sessions = relationship("GameSession", back_populates="quiz", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)  # List of options
    correct_answer = Column(String(255), nullable=False)
    time_limit = Column(Integer, default=30)  # seconds
    order = Column(Integer, default=0)
    
    quiz = relationship("Quiz", back_populates="questions")


class GameSession(Base):
    __tablename__ = "game_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    pin = Column(String(6), unique=True, index=True, nullable=False)
    host_name = Column(String(100), nullable=False)
    status = Column(String(20), default="waiting")  # waiting, active, finished
    current_question_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    certificate_threshold = Column(Integer, default=75)
    certificate_template_path = Column(String(500), nullable=True)
    
    quiz = relationship("Quiz", back_populates="game_sessions")
    players = relationship("Player", back_populates="game_session", cascade="all, delete-orphan")


class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, index=True)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    name = Column(String(100), nullable=False)
    roll_number = Column(String(50), nullable=True, index=True)
    score = Column(Integer, default=0)
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    game_session = relationship("GameSession", back_populates="players")
    answers = relationship("Answer", back_populates="player", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer = Column(String(255), nullable=False)
    is_correct = Column(Boolean, default=False)
    time_taken = Column(Float, nullable=False)  # seconds
    points_earned = Column(Integer, default=0)
    answered_at = Column(DateTime, default=datetime.utcnow)
    
    player = relationship("Player", back_populates="answers")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, index=True)  # host, joiner
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_game_session_certificate_columns()
    _ensure_player_roll_number_column()
    _ensure_user_table()


def _ensure_game_session_certificate_columns():
    """
    Lightweight schema patch for existing DBs without running alembic migrations.
    """
    inspector = inspect(engine)
    if "game_sessions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("game_sessions")}

    with engine.begin() as conn:
        if "certificate_threshold" not in columns:
            conn.execute(text("ALTER TABLE game_sessions ADD COLUMN certificate_threshold INTEGER DEFAULT 75"))

        if "certificate_template_path" not in columns:
            conn.execute(text("ALTER TABLE game_sessions ADD COLUMN certificate_template_path VARCHAR(500)"))


def _ensure_player_roll_number_column():
    """
    Add roll_number on players for direct join without affecting old rows/flows.
    """
    inspector = inspect(engine)
    if "players" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("players")}
    if "roll_number" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE players ADD COLUMN roll_number VARCHAR(50)"))


def _ensure_user_table():
    """
    Ensure auth user table exists on legacy DBs.
    """
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        return

    User.__table__.create(bind=engine, checkfirst=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
