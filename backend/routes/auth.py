from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import User, get_db
from schemas import AuthTokenResponse, AuthUserResponse, LoginRequest, SignupRequest
from services.auth_service import create_access_token, decode_access_token, hash_password

router = APIRouter(prefix="/api/auth", tags=["Auth"])
security = HTTPBearer(auto_error=False)

ALLOWED_HOST_CREDENTIALS = {
    "tester01": "Quiz@123",
    "tester02": "Quiz@124",
    "tester03": "Quiz@125",
    "tester04": "Quiz@126",
    "tester05": "Quiz@127",
    "tester06": "Quiz@128",
    "tester07": "Quiz@129",
    "tester08": "Quiz@130",
    "tester09": "Quiz@131",
    "tester10": "Quiz@132",
    "admin": "admin@varunbhai",
}


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    subject = decode_access_token(credentials.credentials)
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    try:
        user_id = int(subject)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from exc

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


@router.post("/signup", response_model=AuthTokenResponse)
async def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    raise HTTPException(status_code=403, detail="Signup is disabled. Use your assigned credentials.")


@router.post("/login", response_model=AuthTokenResponse)
async def login(payload: LoginRequest, db: Session = Depends(get_db)):
    identifier = _normalize_email(payload.email)

    expected_password = ALLOWED_HOST_CREDENTIALS.get(identifier)
    if not expected_password:
        raise HTTPException(status_code=403, detail="This Host ID is not allowed")
    if payload.password != expected_password:
        raise HTTPException(status_code=401, detail="Invalid Host ID or password")

    synthetic_email = f"{identifier}@host.local"
    user = db.query(User).filter(User.email == synthetic_email).first()
    if not user:
        user = User(
            full_name=identifier.upper(),
            email=synthetic_email,
            password_hash=hash_password(expected_password),
            role="host",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(subject=str(user.id))

    return AuthTokenResponse(
        access_token=token,
        user=AuthUserResponse(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=user.role,
            created_at=user.created_at,
        ),
    )


@router.get("/me", response_model=AuthUserResponse)
async def me(current_user: User = Depends(_get_current_user)):
    return AuthUserResponse(
        id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        role=current_user.role,
        created_at=current_user.created_at,
    )
