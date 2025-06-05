# outfitai_project/models/outfit_models.py
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from enum import Enum
import uuid
from datetime import datetime, timezone

# --- Wardrobe Item Models ---
class ItemCategory(str, Enum):
    TOP = "Top"
    BOTTOM = "Bottom"
    OUTERWEAR = "Outerwear"
    SHOES = "Shoes"
    ACCESSORY = "Accessory"
    DRESS = "Dress"
    OTHER = "Other"

class WardrobeItemBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, example="Blue Denim Jacket")
    category: ItemCategory = Field(..., example=ItemCategory.OUTERWEAR)
    color: Optional[str] = Field(None, max_length=50, example="Blue")
    material: Optional[str] = Field(None, max_length=50, example="Denim")
    brand: Optional[str] = Field(None, max_length=50, example="Levi's")
    size: Optional[str] = Field(None, max_length=20, example="M")
    purchase_date: Optional[datetime] = Field(None, example=datetime.now().isoformat())
    image_url: Optional[HttpUrl] = Field(None, example="http://example.com/image.jpg")
    notes: Optional[str] = Field(None, example="Goes well with white t-shirt.")

class WardrobeItemCreate(WardrobeItemBase):
    pass

class WardrobeItemUpdate(WardrobeItemBase):
    name: Optional[str] = Field(None, min_length=2, max_length=100, example="Dark Blue Denim Jacket")
    category: Optional[ItemCategory] = None
    color: Optional[str] = Field(None, max_length=50, example="Dark Blue")
    material: Optional[str] = Field(None, max_length=50, example="Cotton Denim")
    brand: Optional[str] = Field(None, max_length=50, example="Levi's")
    size: Optional[str] = Field(None, max_length=20, example="M")
    purchase_date: Optional[datetime] = None
    image_url: Optional[HttpUrl] = None
    notes: Optional[str] = Field(None, example="Slightly faded. Still good for casual wear.")

class WardrobeItem(WardrobeItemBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_worn: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Context Input Model ---
class RecommendationRequestContext(BaseModel):
    event_type: str = Field(..., example="Casual dinner with friends")
    style_goal: Optional[str] = Field(None, example="Chic but comfortable")
    inspirational_image_url: Optional[HttpUrl] = Field(None, example="http://example.com/inspiration.jpg")

# --- Outfit Suggestion & Recommendation Models ---
class OutfitComponentSuggestion(BaseModel):
    item_category: ItemCategory = Field(..., example=ItemCategory.TOP)
    description: str = Field(..., example="A light blue linen shirt")
    product_image_url: Optional[HttpUrl] = Field(None, example="http://example.com/imagesearch_product.jpg")
    product_store_url: Optional[HttpUrl] = Field(None, example="http://shop.example.com/product_search")

    class Config:
        from_attributes = True

class OutfitRecommendationBase(BaseModel):
    components: List[OutfitComponentSuggestion] = Field(...)
    overall_reasoning: Optional[str] = Field(None)

class OutfitRecommendationCreate(OutfitRecommendationBase): # Input from LLM/scraper
    pass

class OutfitRecommendation(OutfitRecommendationBase): # Generated recommendation object
    id: uuid.UUID = Field(default_factory=uuid.uuid4) # Unique ID for this generated recommendation
    user_id: uuid.UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type_context: Optional[str] = Field(None)
    style_goal_context: Optional[str] = Field(None)
    inspirational_image_url_context: Optional[HttpUrl] = Field(None)

    class Config:
        from_attributes = True

# --- Saved Outfit Models ---
class SavedOutfitCreate(BaseModel): # Request body for saving an outfit
    original_recommendation_id: uuid.UUID # ID of the OutfitRecommendation being saved
    user_rating: Optional[int] = Field(None, ge=1, le=5, example=4)
    user_notes: Optional[str] = Field(None, example="Really liked the color combination!")

class SavedOutfit(OutfitRecommendation): # The saved entity
    # Inherits: id (this will be the NEW id of the SavedOutfit record), 
    # user_id, components, overall_reasoning, created_at (from original), context fields...
    original_recommendation_id: uuid.UUID # Links back to the specific OutfitRecommendation that was generated.
    saved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Timestamp for when this instance was saved
    user_rating: Optional[int] = Field(None, ge=1, le=5)
    user_notes: Optional[str] = Field(None)

    class Config:
        from_attributes = True