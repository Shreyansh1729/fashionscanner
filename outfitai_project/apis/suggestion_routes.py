from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db import orm_models as models

from ..core.security import get_current_user
from ..services import suggestion_service
from ..models.outfit_models import DailyOutfitResponse, WeeklyPlanRequest, WeeklyPlanResponse

router = APIRouter(
    prefix="/suggestions",
    tags=["Outfit Suggestions"]
)

@router.get("/today", response_model=DailyOutfitResponse)
async def get_todays_outfits(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Generates a set of hyper-personalized outfit suggestions for the day.
    
    This endpoint considers:
    - Your calendar events for the day (or a default schedule).
    - The current weather in your city (requires user profile to have a city).
    - Your existing wardrobe items.
    - An anti-repetition rule to ensure variety.
    
    If it cannot find a suitable item for a special occasion, it will
    suggest that you might want to purchase one. The response will be structured
    with keys for each occasion (e.g., 'office_formal', 'gym_sports').
    """
    suggestions = await suggestion_service.generate_daily_outfits(db, user=current_user)
    return suggestions

@router.post("/weekly-plan", response_model=WeeklyPlanResponse)
async def get_weekly_outfit_plan(
    plan_request: WeeklyPlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Generates a multi-day (3-7 days) outfit plan for a general occasion.
    It considers the weather forecast and avoids repeating clothes to ensure variety.
    """
    return await suggestion_service.generate_weekly_plan(db, user=current_user, plan_request=plan_request)