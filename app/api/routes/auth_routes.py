from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.auth import get_password_hash, verify_password, create_access_token
from app.api.deps import get_current_user
from app.db.session import get_async_db
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict


@router.post("/register", response_model=TokenResponse)
async def register(req: AuthRequest, db: AsyncSession = Depends(get_async_db)):
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == req.email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    # Create new user
    hashed = get_password_hash(req.password)
    user = User(email=req.email, hashed_password=hashed)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create JWT
    token = create_access_token(data={"sub": user.id})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={"id": user.id, "email": user.email},
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: AuthRequest, db: AsyncSession = Depends(get_async_db)):
    # Find user
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalars().first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Create JWT
    token = create_access_token(data={"sub": user.id})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={"id": user.id, "email": user.email},
    )


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "created_at": user.created_at}
