# outfitai_project/services/user_service.py
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fastapi import HTTPException, status

from ..models.user_models import UserCreate, UserUpdate
from ..db import orm_models as models
# Make sure both security functions are imported
from ..core.security import get_password_hash, verify_password

# --- AUTHENTICATION SERVICE ---
async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[models.User]:
    """Authenticates a user by checking email and verifying password."""
    user = await get_user_by_email(db, email=email)
    if not user:
        return None
    # This function compares the plain password to the HASHED password from the DB
    if not verify_password(password, user.hashed_password):
        return None
    return user

# --- CRUD SERVICES (Updated) ---
async def get_user_by_email(db: AsyncSession, email: str) -> Optional[models.User]:
    """Retrieves a user by their email from the database."""
    result = await db.execute(select(models.User).filter(models.User.email == email))
    return result.scalars().first()

async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[models.User]:
    """Retrieves a user by their ID from the database."""
    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    return result.scalars().first()

async def create_user_in_db(db: AsyncSession, user_in: UserCreate) -> models.User:
    """Creates a new user in the database with a hashed password."""
    if await get_user_by_email(db, user_in.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered."
        )
    
    # --- THIS IS THE CRITICAL LINE THAT WAS LIKELY MISSING ---
    # Hash the password before saving
    hashed_password = get_password_hash(user_in.password)
    
    db_user = models.User(
        email=user_in.email,
        hashed_password=hashed_password, # <-- Store the HASH, not the plain password
        username=user_in.username,
        gender=user_in.gender,
        age_range=user_in.age_range,
        body_type=user_in.body_type,
        body_measurements=user_in.body_measurements,
        skin_tone=user_in.skin_tone,
        height_cm=user_in.height_cm,
        weight_kg=user_in.weight_kg,
        is_active=True
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def update_user_in_db(db: AsyncSession, user_id: uuid.UUID, user_in: UserUpdate) -> Optional[models.User]:
    """Updates an existing user in the database."""
    db_user = await get_user_by_id(db, user_id)
    if not db_user:
        return None

    update_data = user_in.model_dump(exclude_unset=True)

    if "password" in update_data and update_data["password"]:
        db_user.hashed_password = get_password_hash(update_data["password"])
        del update_data["password"]

    for field, value in update_data.items():
        if value is not None:
            setattr(db_user, field, value)
    
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def get_all_users_in_db(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[models.User]:
    """Retrieves all users from the database with pagination."""
    result = await db.execute(select(models.User).offset(skip).limit(limit))
    return result.scalars().all()