from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.services.auth import decode_token, get_user_by_id, hash_password

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def _get_or_create_bypass_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.email == settings.auth_bypass_email))
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(
        email=settings.auth_bypass_email,
        username=settings.auth_bypass_username,
        hashed_password=hash_password("auth-bypass-not-used"),
        is_active=True,
        is_superuser=settings.auth_bypass_superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if settings.auth_bypass_enabled:
        return await _get_or_create_bypass_user(db)

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_error
        user_id: str = payload["sub"]
    except (ValueError, KeyError):
        raise credentials_error

    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise credentials_error
    return user


async def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
    return current_user
