# outfitai_project/db/orm_models.py
import uuid
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float, DateTime, Enum, ForeignKey, JSON, TypeDecorator
)
# REMOVE: from sqlalchemy.dialects.postgresql import UUID  <-- Remove this old import
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from .database import Base
from ..models.user_models import BodyType, SkinTone
from ..models.outfit_models import ItemCategory
from sqlalchemy import UniqueConstraint


# --- NEW: Custom UUID Type for cross-database compatibility ---
class GUID(TypeDecorator):
    """
    Platform-independent GUID type.
    Uses PostgreSQL's UUID type, and otherwise uses
    CHAR(32), storing as stringified hex values.
    """
    impl = String(32)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import UUID
            return dialect.type_descriptor(UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(String(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % uuid.UUID(value).int
            else:
                # hexstring
                return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(value)
            return value

# --- Models updated to use the new GUID type ---
class User(Base):
    __tablename__ = "users"
    id = Column(GUID, primary_key=True, default=uuid.uuid4) # <-- Use GUID
    email = Column(String, unique=True, index=True, nullable=False)
    # ... rest of the User model is the same
    username = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    gender = Column(String, nullable=True)
    age_range = Column(String, nullable=True)
    body_type = Column(Enum(BodyType), default=BodyType.UNSPECIFIED)
    body_measurements = Column(String, nullable=True)
    skin_tone = Column(Enum(SkinTone), default=SkinTone.UNSPECIFIED)
    skin_color = Column(String, nullable=True) # e.g., 'Fair', 'Olive', 'Medium'
    height_cm = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    wardrobe_items = relationship("WardrobeItem", back_populates="owner", cascade="all, delete-orphan")
    generated_recommendations = relationship("GeneratedRecommendation", back_populates="user", cascade="all, delete-orphan")
    saved_outfits = relationship("SavedOutfit", back_populates="user", cascade="all, delete-orphan")

class WardrobeItem(Base):
    __tablename__ = "wardrobe_items"
    id = Column(GUID, primary_key=True, default=uuid.uuid4) # <-- Use GUID
    user_id = Column(GUID, ForeignKey("users.id"), nullable=False) # <-- Use GUID
    # ... rest of the WardrobeItem model is the same
    name = Column(String, index=True, nullable=False)
    category = Column(Enum(ItemCategory), nullable=False)
    color = Column(String, nullable=True)
    material = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    size = Column(String, nullable=True)
    purchase_date = Column(DateTime, nullable=True)
    image_url = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_worn = Column(DateTime, nullable=True)
    owner = relationship("User", back_populates="wardrobe_items")

class GeneratedRecommendation(Base):
    __tablename__ = "generated_recommendations"
    id = Column(GUID, primary_key=True, default=uuid.uuid4) # <-- Use GUID
    user_id = Column(GUID, ForeignKey("users.id"), nullable=False) # <-- Use GUID
    # ... rest of the GeneratedRecommendation model is the same
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    event_type_context = Column(String, nullable=True)
    style_goal_context = Column(String, nullable=True)
    inspirational_image_source_info = Column(String, nullable=True)
    analyzed_inspirational_image_description = Column(Text, nullable=True)
    components_json = Column(JSON, nullable=False)
    overall_reasoning = Column(Text, nullable=True)
    user = relationship("User", back_populates="generated_recommendations")
    saved_by_users = relationship("SavedOutfit", back_populates="recommendation", cascade="all, delete-orphan")

class SavedOutfit(Base):
    __tablename__ = "saved_outfits"
    id = Column(GUID, primary_key=True, default=uuid.uuid4) # <-- Use GUID
    user_id = Column(GUID, ForeignKey("users.id"), nullable=False) # <-- Use GUID
    recommendation_id = Column(GUID, ForeignKey("generated_recommendations.id"), nullable=False) # <-- Use GUID
    # ... rest of the SavedOutfit model is the same
    saved_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    user_rating = Column(Integer, nullable=True)
    user_notes = Column(Text, nullable=True)
    user = relationship("User", back_populates="saved_outfits")
    recommendation = relationship("GeneratedRecommendation", back_populates="saved_by_users")

# --- NEW TABLE FOR ENRICHED PRODUCT DATA ---
class Product(Base):
    __tablename__ = "products"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    product_url = Column(String, nullable=False, unique=True, index=True) # Unique key
    retailer = Column(String, index=True)
    product_name = Column(String)
    price = Column(String)
    image_url = Column(String)
    
    # --- STRUCTURED ATTRIBUTES (From AI Enrichment) ---
    gender = Column(String, index=True, nullable=True)
    category = Column(String, index=True, nullable=True)
    color = Column(String, index=True, nullable=True)
    material = Column(String, index=True, nullable=True)
    fit = Column(String, index=True, nullable=True)
    brand = Column(String, index=True, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('product_url', name='_product_url_uc'),)


# --- CORRECTED UserEvent TABLE ---
class UserEvent(Base):
    __tablename__ = "user_events"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID, ForeignKey("users.id"), nullable=False)
    event_type = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # --- RENAMED THIS COLUMN ---
    # From 'metadata' to 'event_data' to avoid keyword conflict
    event_data = Column(JSON, nullable=True)

    user = relationship("User")
