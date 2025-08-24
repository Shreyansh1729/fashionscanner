# In outfitai_project/models/analytics_models.py

from pydantic import BaseModel, Field
from typing import List, Optional
from .outfit_models import WardrobeItemResponse, ItemCategory
import uuid

class OverviewAnalytics(BaseModel):
    """Analytics for the 'Overview' tab."""
    total_items: int = Field(..., description="Total number of items in the user's wardrobe.")
    weekly_items_worn: int = Field(..., description="Number of unique items worn in the last 7 days.")
    monthly_items_worn: int = Field(..., description="Number of unique items worn in the last 30 days.")
    repeat_rate_percent: float = Field(..., description="Percentage of wears in the last 30 days that were repeat wears of the same item.", example=75.5)
    items_worn_count: int = Field(..., description="Number of items in the wardrobe that have been worn at least once.")
    items_unworn_count: int = Field(..., description="Number of items in the wardrobe that have never been worn.")

class CategoryCount(BaseModel):
    """Represents the count of items in a specific category."""
    category: ItemCategory
    count: int

class StyleCount(BaseModel):
    """Represents the count of items of a specific style (e.g., formal, casual)."""
    style: str
    count: int

class CategoryAnalytics(BaseModel):
    """Analytics for the 'Categories' tab."""
    by_category: List[CategoryCount] = Field(..., description="Breakdown of wardrobe items by their main category.")
    by_style: List[StyleCount] = Field(..., description="Breakdown of wardrobe items by style (formal, casual, etc.).")

class ItemUsage(BaseModel):
    """Detailed usage statistics for a single wardrobe item."""
    item: WardrobeItemResponse
    wear_count: int

class UsageAnalytics(BaseModel):
    """Analytics for the 'Usage' tab."""
    most_worn_item: Optional[ItemUsage] = None
    least_worn_item: Optional[ItemUsage] = None
    total_wears: int = Field(..., description="The total number of times any item has been recorded as worn in the history.")
    average_wear_per_item: float = Field(..., description="Average number of times each item in the wardrobe has been worn.", example=11.7)

class PaletteItem(BaseModel):
    """A simplified representation of a wardrobe item for a palette."""
    id: uuid.UUID
    name: str
    color: Optional[str] = None
    category: ItemCategory

    class Config:
        from_attributes = True

class ColorPaletteSuggestion(BaseModel):
    """Represents a single, complete color palette suggestion."""
    palette_name: str = Field(..., example="Earthy Tones")
    description: str = Field(..., example="A warm and grounded palette perfect for casual autumn days.")
    items: List[PaletteItem]

class ColorPaletteResponse(BaseModel):
    """The final API response containing a list of suggested color palettes."""
    palettes: List[ColorPaletteSuggestion]