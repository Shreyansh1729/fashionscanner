# In outfitai_project/apis/pairing_routes.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from ..db.database import get_db
from ..db import orm_models as models
from ..models.outfit_models import ItemPairingResponse
from ..core.security import get_current_user
from ..services import suggestion_service

router = APIRouter(
    prefix="/pairings",
    tags=["Advanced Suggestions"]
)

@router.get("/with-item/{item_id}", response_model=ItemPairingResponse)
async def get_pairings_for_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    "What Goes With This?" - Generates multiple complete outfit suggestions
    built around a single, specific item from the user's wardrobe.
    """
    return await suggestion_service.generate_pairings_for_item(db=db, user=current_user, item_id=item_id)