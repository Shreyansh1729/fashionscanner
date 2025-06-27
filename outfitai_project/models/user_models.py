# outfitai_project/models/user_models.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from enum import Enum
import uuid # For generating unique IDs

class BodyType(str, Enum):
    ECTOMORPH = "Ectomorph"
    MESOMORPH = "Mesomorph"
    ENDOMORPH = "Endomorph"
    UNSPECIFIED = "Unspecified"

class SkinTone(str, Enum):
    WARM = "Warm"
    COOL = "Cool"
    NEUTRAL = "Neutral"
    UNSPECIFIED = "Unspecified"

# --- User Models ---
class UserBase(BaseModel):
    email: EmailStr = Field(..., example="user@example.com")
    username: Optional[str] = Field(None, min_length=3, max_length=50, example="fashionista123")
    # Manual input for MVP as per F-MVP-01
    gender: Optional[str] = Field(None, example="Female")
    age_range: Optional[str] = Field(None, example="25-35") # e.g., "18-24", "25-34"
    body_type: Optional[BodyType] = BodyType.UNSPECIFIED
    body_measurements: Optional[str] = Field(None, example="Bust: 34in, Waist: 28in, Hips: 38in")
    skin_tone: Optional[SkinTone] = SkinTone.UNSPECIFIED
    skin_color: Optional[str] = Field(None, example="Olive")
    height_cm: Optional[int] = Field(None, gt=0, example=165) # Height in centimeters
    weight_kg: Optional[float] = Field(None, gt=0, example=60.5) # Weight in kilograms

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, example="strongpassword123")

class UserUpdate(UserBase):
    # For updates, all fields are optional
    email: Optional[EmailStr] = Field(None, example="user@example.com")
    username: Optional[str] = Field(None, min_length=3, max_length=50, example="fashionista123")
    password: Optional[str] = Field(None, min_length=8, example="newstrongpassword")
    gender: Optional[str] = Field(None, example="Female")
    age_range: Optional[str] = Field(None, example="25-35")
    body_type: Optional[BodyType] = None
    body_measurements: Optional[str] = Field(None, example="Bust: 34in, Waist: 28in, Hips: 38in")
    skin_tone: Optional[SkinTone] = None
    skin_color: Optional[str] = Field(None, example="Medium")
    height_cm: Optional[int] = Field(None, gt=0, example=170)
    weight_kg: Optional[float] = Field(None, gt=0, example=62.0)

class User(UserBase): # This model represents a user object as stored in the DB or returned by API
    id: uuid.UUID = Field(default_factory=uuid.uuid4, example=uuid.uuid4())
    is_active: bool = True
    # wardrobe_items: List['WardrobeItem'] = [] # We'll handle relations later if using an ORM

    class Config:
        # Deprecated in Pydantic v2, use model_config instead
        # orm_mode = True
        # Pydantic v2 equivalent:
        from_attributes = True # Allows creating Pydantic model from ORM objects

# This is needed for Pydantic to correctly handle the forward reference of WardrobeItem if defined in another file and imported
# However, for now, we'll keep them separate. If we define WardrobeItem below User, this is not strictly needed.
# For circular dependencies if WardrobeItem also referenced User, we'd need model_rebuild().