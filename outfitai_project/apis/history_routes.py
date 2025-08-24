# In outfitai_project/apis/history_routes.py

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..db.database import get_db
from ..db import orm_models as models
from ..models.outfit_models import ConfirmWornRequest, WornOutfitHistoryResponse
from ..core.security import get_current_user
from ..services import history_service

router = APIRouter(
    prefix="/history",
    tags=["Outfit History & Analytics"]
)

@router.post("/confirm-worn", status_code=status.HTTP_202_ACCEPTED)
async def confirm_outfit_worn(
    worn_request: ConfirmWornRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Confirms that an outfit was worn. This updates the 'last_worn' date for
    each item (improving future recommendations) and logs the outfit to the user's history.
    """
    await history_service.mark_outfit_as_worn(db, user=current_user, worn_request=worn_request)
    return {"message": "Outfit wear confirmed and logged successfully."}

@router.get("/", response_model=List[WornOutfitHistoryResponse])
async def get_history(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Retrieves a chronological log of all outfits the user has previously marked as worn.
    """
    return await history_service.get_worn_outfit_history(db, user=current_user)