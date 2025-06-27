# outfitai_project/models/outfit_models.py

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List , Literal
from enum import Enum
import uuid
from datetime import datetime, timezone


# --- NEW: Enums for sorting and filtering ---
Retailer = Literal["Myntra", "Ajio", "Amazon"] # Add more as we build parsers
SortBy = Literal["relevance", "price_asc", "price_desc", "rating_desc"]

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
    purchase_date: Optional[datetime] = Field(None, example=datetime.now(timezone.utc).isoformat())
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
    event_type: str = Field(..., example="Couples photoshoot")
    style_goal: Optional[str] = Field(None, example="Coordinated but not identical; earthy tones.")
    location: Optional[str] = Field(None, description="e.g., 'Udaipur, India'. For weather context.")
    event_date: Optional[str] = Field(None, description="e.g., '2025-07-21'. For weather forecast.")
    inspirational_image_url: Optional[HttpUrl] = Field(None, description="URL of an image for style inspiration.")
    use_profile_picture_for_inspiration: bool = Field(False, description="Set to true to use the user's own profile picture as style inspiration.")


    # --- NEW FIELD for Color Palette ---
    color_palette: Optional[str] = Field(None, description="Optional color scheme to follow (e.g., 'Earthy Tones', 'Monochromatic').")


    # --- ADVANCED SCRAPING CONTROLS ---
    retailers_to_search: List[Retailer] = Field(
        default=["Myntra", "Ajio"], 
        description="A list of preferred retailers to search."
    )
    product_limit_per_retailer: int = Field(
        default=5, ge=1, le=5,
        description="Max products to fetch from each retailer before filtering."
    )
    # --- ADVANCED FILTERING/SORTING ---
    sort_by: SortBy = Field(
        default="relevance", 
        description="How to sort the final list of products."
    )
    min_rating: Optional[float] = Field(
        None, ge=0, le=5, 
        description="Minimum product rating to include (if available)."
    )

# --- Scraped Product Model ---
class ScrapedProduct(BaseModel):
    retailer: str
    product_name: str
    price: str
    product_url: HttpUrl
    image_url: Optional[HttpUrl] = None

# --- Outfit Component Suggestion with scraped products ---
class OutfitComponentSuggestion(BaseModel):
    item_category: ItemCategory
    description: str  # e.g., "A-line blue floral kurta"
    scraped_products: List[ScrapedProduct] = Field(default_factory=list)
    search_query: str 
    fallback_search_url: Optional[HttpUrl] = Field(None, description="A Google Shopping link if direct scraping fails.")
    

    class Config:
        from_attributes = True

# --- Outfit Recommendation Models ---
class OutfitRecommendationBase(BaseModel):
    components: List[OutfitComponentSuggestion] = Field(...)
    overall_reasoning: Optional[str] = Field(None, example="The linen shirt keeps it breathable and adds elegance.")

class OutfitRecommendationCreate(OutfitRecommendationBase):
    pass

class OutfitRecommendation(OutfitRecommendationBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type_context: Optional[str] = Field(None, example="Dinner party")
    style_goal_context: Optional[str] = Field(None, example="Elegant but comfortable")
    inspirational_image_source_info: Optional[str] = Field(
        None, example="URL: http://example.com/image.jpg or Uploaded: user_upload.jpg"
    )
    analyzed_inspirational_image_description: Optional[str] = Field(
        None, example="The image shows a person wearing a red floral dress with gold sandals."
    )

    class Config:
        from_attributes = True

# --- Saved Outfit Models ---
class SavedOutfitCreate(BaseModel):
    original_recommendation_id: uuid.UUID = Field(..., example="550e8400-e29b-41d4-a716-446655440000")
    user_rating: Optional[int] = Field(None, ge=1, le=5, example=4)
    user_notes: Optional[str] = Field(None, example="Really liked the color combination!")

class SavedOutfit(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    saved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    original_recommendation_id: uuid.UUID
    user_rating: Optional[int] = Field(None, ge=1, le=5, example=5)
    user_notes: Optional[str] = Field(None, example="Loved this look for the office.")
    recommendation: OutfitRecommendation

    class Config:
        from_attributes = True
