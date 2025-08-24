# In outfitai_project/services/history_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from datetime import datetime, timezone
import uuid
from typing import List

from ..db import orm_models as models
from ..models.outfit_models import ConfirmWornRequest, WornOutfitHistoryResponse

async def mark_outfit_as_worn(db: AsyncSession, user: models.User, worn_request: ConfirmWornRequest) -> bool:
    """
    Updates last_worn on items and creates a history record.
    Returns True on success.
    """
    now = datetime.now(timezone.utc)
    
    # 1. Update the last_worn timestamp for each item
    # This ensures the anti-repetition rule works dynamically
    update_stmt = (
        update(models.WardrobeItem)
        .where(models.WardrobeItem.id.in_(worn_request.item_ids), models.WardrobeItem.user_id == user.id)
        .values(last_worn=now)
    )
    await db.execute(update_stmt)
    
    # 2. Create a new entry in the WornOutfitHistory table
    # Convert list of UUIDs to a comma-separated string for storage
    item_ids_str = ",".join(str(item_id) for item_id in worn_request.item_ids)
    
    new_history_entry = models.WornOutfitHistory(
        id=uuid.uuid4(),
        user_id=user.id,
        item_ids=item_ids_str,
        event_context=worn_request.event_context,
        worn_at=now
    )
    db.add(new_history_entry)
    
    await db.commit()
    return True

async def get_worn_outfit_history(db: AsyncSession, user: models.User) -> List[WornOutfitHistoryResponse]:
    """Retrieves and reconstructs the user's outfit history."""
    
    # 1. Fetch all history records for the user, ordered by most recent
    history_stmt = (
        select(models.WornOutfitHistory)
        .where(models.WornOutfitHistory.user_id == user.id)
        .order_by(models.WornOutfitHistory.worn_at.desc())
    )
    history_results = (await db.execute(history_stmt)).scalars().all()
    
    if not history_results:
        return []

    # 2. Collect all unique item IDs needed from the entire history
    all_item_ids_needed = set()
    for record in history_results:
        ids = [uuid.UUID(id_str) for id_str in record.item_ids.split(',')]
        all_item_ids_needed.update(ids)
        
    # 3. Fetch all required wardrobe items in a single efficient query
    items_stmt = select(models.WardrobeItem).where(models.WardrobeItem.id.in_(list(all_item_ids_needed)))
    item_results = (await db.execute(items_stmt)).scalars().all()
    items_map = {item.id: item for item in item_results} # Create a lookup map for quick access

    # 4. Reconstruct the response
    response_list = []
    for record in history_results:
        outfit_item_ids = [uuid.UUID(id_str) for id_str in record.item_ids.split(',')]
        # Use the map to find the full item details for the current outfit
        outfit_items = [items_map[item_id] for item_id in outfit_item_ids if item_id in items_map]
        
        response_list.append(
            WornOutfitHistoryResponse(
                worn_at=record.worn_at,
                event_context=record.event_context,
                items=outfit_items
            )
        )
        
    return response_list