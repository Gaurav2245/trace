from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.config import get_settings
import hashlib

settings = get_settings()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(pw: str) -> str:
    pw = hashlib.sha256(pw.encode()).hexdigest()
    return pwd_ctx.hash(pw)


def verify_password(plain: str, hashed: str) -> bool:
    plain = hashlib.sha256(plain.encode()).hexdigest()
    return pwd_ctx.verify(plain, hashed)

def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_user_id(token: str) -> str:
    """Decode a JWT and return the user id, raising JWTError/ValueError on failure."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    uid = payload.get("sub")
    if not uid:
        raise ValueError("Invalid token payload")
    return uid


async def get_current_user_id(token: str = Depends(oauth2)) -> str:
    try:
        return decode_user_id(token)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
