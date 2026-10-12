from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import (
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
)
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import User
from schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ============================================================
# PASSWORD FUNCTIONS
# ============================================================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


# ============================================================
# JWT / AUTHENTICATION
# ============================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)


def create_access_token(user_id: UUID) -> str:
    expire = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=settings.access_token_expire_minutes
        )
    )

    payload = {
        "sub": str(user_id),
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        user_id = payload.get("sub")

        if user_id is None:
            raise credentials_exception

        user_uuid = UUID(user_id)

    except (JWTError, ValueError):
        raise credentials_exception

    result = await db.execute(
        select(User).where(User.id == user_uuid)
    )

    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user


# ============================================================
# SIGNUP
# ============================================================

@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def signup(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):

    # Check whether email already exists
    result = await db.execute(
        select(User).where(
            User.email == user_data.email
        )
    )

    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Hash password before storing
    user = User(
        email=user_data.email,
        password_hash=hash_password(
            user_data.password
        ),
        full_name=user_data.full_name,
    )

    db.add(user)

    await db.commit()
    await db.refresh(user)

    return user


# ============================================================
# LOGIN
# ============================================================

@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):

    # OAuth2 calls this field "username",
    # but we use the user's email here.
    result = await db.execute(
        select(User).where(
            User.email == form_data.username
        )
    )

    user = result.scalar_one_or_none()

    # User doesn't exist
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Password doesn't match
    if not verify_password(
        form_data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Create JWT
    access_token = create_access_token(
        user.id
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
    )


# ============================================================
# CURRENT USER
# ============================================================

@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    current_user: User = Depends(
        get_current_user
    ),
):

    return current_user