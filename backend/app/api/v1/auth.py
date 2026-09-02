from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.models.user import User
from app.repositories import users as users_repo
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.services.mail import MailError, send_password_reset, smtp_configured

router = APIRouter()
logger = logging.getLogger(__name__)
_FORGOT_MESSAGE = "Bu e-posta kayıtlıysa sıfırlama bağlantısı gönderildi."
_last_forgot: dict[str, float] = {}


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.user_id),
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = str(body.email).lower()
    if users_repo.get_by_email(db, email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu e-posta zaten kayıtlı")

    try:
        user = users_repo.create_user(
            db,
            name=email.split("@")[0][:255] or email,
            email=email,
            password_hash=hash_password(body.password),
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu e-posta zaten kayıtlı",
        ) from exc

    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = str(body.email).lower()
    user = users_repo.get_by_email(db, email)
    if user is None or not verify_password(body.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı",
        )
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/change-password", response_model=UserOut)
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    if not verify_password(body.current_password, current_user.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mevcut şifre hatalı")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Yeni şifre eskisiyle aynı")
    return users_repo.set_password(db, current_user, hash_password(body.new_password))


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _reset_url(raw: str) -> str:
    base = settings.frontend_url.rstrip("/")
    return f"{base}/reset-password?token={raw}"


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)) -> ForgotPasswordResponse:
    email = str(body.email).lower()
    now = time.time()
    last = _last_forgot.get(email, 0)
    if now - last < 30:
        return ForgotPasswordResponse(message=_FORGOT_MESSAGE)
    _last_forgot[email] = now

    user = users_repo.get_by_email(db, email)
    if user is None:
        return ForgotPasswordResponse(message=_FORGOT_MESSAGE)

    raw = secrets.token_urlsafe(32)
    users_repo.set_reset_token(
        db,
        user,
        token_hash=_token_hash(raw),
        expires=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    link = _reset_url(raw)
    try:
        send_password_reset(user.email, link)
    except MailError as exc:
        if not smtp_configured():
            logger.warning("SMTP yok; şifre sıfırlama bağlantısı: %s", link)
            return ForgotPasswordResponse(message=_FORGOT_MESSAGE, reset_url=link)
        logger.exception("Şifre sıfırlama e-postası gönderilemedi")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="E-posta gönderilemedi. SMTP kullanıcı/şifre veya Gmail uygulama şifresini kontrol et.",
        ) from exc
    return ForgotPasswordResponse(message=_FORGOT_MESSAGE)


@router.post("/reset-password", response_model=TokenResponse)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = users_repo.get_by_reset_hash(db, _token_hash(body.token.strip()))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bağlantı geçersiz veya süresi dolmuş",
        )
    user = users_repo.set_password(db, user, hash_password(body.password))
    return _token_response(user)
