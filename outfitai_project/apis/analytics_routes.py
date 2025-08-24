# In outfitai_project/apis/analytics_routes.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db import orm_models as models
from ..models import analytics_models as schemas
from ..core.security import get_current_user
from ..services import analytics_service
from ..models import analytics_models as schemas

router = APIRouter(
    prefix="/analytics",
    tags=["Wardrobe Analytics"]
)

@router.get("/overview", response_model=schemas.OverviewAnalytics)
async def get_overview_analytics_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Provides analytics for the 'Overview' tab of the wardrobe analytics UI."""
    return await analytics_service.get_overview_analytics(db, user=current_user)

@router.get("/categories", response_model=schemas.CategoryAnalytics)
async def get_category_analytics_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Provides analytics for the 'Categories' tab, breaking down items by type and style."""
    return await analytics_service.get_category_analytics(db, user=current_user)

@router.get("/usage", response_model=schemas.UsageAnalytics)
async def get_usage_analytics_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Provides analytics for the 'Usage' tab, including most/least worn items."""
    return await analytics_service.get_usage_analytics(db, user=current_user)

@router.get("/color-palettes", response_model=schemas.ColorPaletteResponse)
async def get_color_palette_suggestions_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Analyzes the user's entire wardrobe to suggest 3-4 harmonious color palettes
    that can be created with their existing clothes.
    """
    return await analytics_service.get_color_palette_suggestions(db, user=current_user)
