# outfitai_project/services/user_service.py
import uuid
from typing import Dict, List, Optional

from fastapi import HTTPException, status

from ..models.user_models import User, UserCreate, UserUpdate

# In-memory "database"
# We'll use a dictionary to store users. The key will be the user's UUID.
db_users: Dict[uuid.UUID, User] = {}

# --- Basic Password Hashing (for demonstration only - use a proper library like passlib in production) ---
# For a real application, you MUST use a strong password hashing library.
# Example: from passlib.context import CryptContext
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# def verify_password(plain_password, hashed_password):
#     return pwd_context.verify(plain_password, hashed_password)
# def get_password_hash(password):
#     return pwd_context.hash(password)
# For now, we'll store passwords in plain text for simplicity in this early stage.
# THIS IS NOT SECURE FOR PRODUCTION.

def get_user_by_email(email: str) -> Optional[User]:
    """Retrieves a user by their email."""
    for user in db_users.values():
        if user.email == email:
            return user
    return None

def get_user_by_id(user_id: uuid.UUID) -> Optional[User]:
    """Retrieves a user by their ID."""
    return db_users.get(user_id)

def create_user_in_db(user_in: UserCreate) -> User:
    """Creates a new user in the database."""
    if get_user_by_email(user_in.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered."
        )
    
    # In a real app, hash the password here:
    # hashed_password = get_password_hash(user_in.password)
    # For now, storing plain text (NOT SECURE):
    hashed_password = user_in.password # Placeholder

    user_id = uuid.uuid4()
    db_user = User(
        id=user_id,
        # **user_in.model_dump() # This would spread all fields from UserCreate
        # Manually map fields to ensure password isn't directly copied if User model evolves
        email=user_in.email,
        username=user_in.username,
        gender=user_in.gender,
        age_range=user_in.age_range,
        body_type=user_in.body_type,
        body_measurements=user_in.body_measurements,
        skin_tone=user_in.skin_tone,
        height_cm=user_in.height_cm,
        weight_kg=user_in.weight_kg,
        is_active=True
        # Note: We are not storing the plain password in the User model that goes into db_users.
        # If we were hashing, we'd store hashed_password.
        # For now, for login (which we'll build later), we'd compare user_in.password
        # with some stored (ideally hashed) password.
    )
    db_users[user_id] = db_user

    # We need to simulate storing the password somewhere to "log in" later.
    # This is highly insecure and only for MVP in-memory demonstration.
    # A better way for in-memory demo would be to add a `hashed_password` field to the `User` model
    # and store the (plain for now, then hashed) password there.
    # Let's do that for clarity. Add `hashed_password: str` to User model if taking this approach.
    # For this iteration, we'll just acknowledge the user object itself doesn't store it.

    print(f"User created: {db_user.email} with ID: {db_user.id}. Plain password (DEMO ONLY): {user_in.password}")
    return db_user

def update_user_in_db(user_id: uuid.UUID, user_in: UserUpdate) -> Optional[User]:
    """Updates an existing user in the database."""
    db_user = get_user_by_id(user_id)
    if not db_user:
        return None

    update_data = user_in.model_dump(exclude_unset=True) # Get only fields that are set in the input

    # In a real app, if password is being updated, hash it:
    # if "password" in update_data and update_data["password"]:
    #     hashed_password = get_password_hash(update_data["password"])
    #     db_user.hashed_password = hashed_password # Assuming User model has hashed_password
    #     del update_data["password"] # Don't store plain password directly

    for field, value in update_data.items():
        if value is not None: # Ensure we only update if a value is provided
            setattr(db_user, field, value)
    
    db_users[user_id] = db_user # Re-assign to ensure the dict has the updated object
    print(f"User updated: {db_user.email}")
    return db_user

def get_all_users_in_db() -> List[User]:
    """Retrieves all users from the database."""
    return list(db_users.values())