# outfitai_project/services/wardrobe_service.py
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fastapi import HTTPException, status

# CORRECTED IMPORTS: Relative paths within the package
from ..models.outfit_models import WardrobeItemCreate, WardrobeItemUpdate
from ..db import orm_models as models
from . import user_service

async def add_wardrobe_item_for_user(db: AsyncSession, user_id: uuid.UUID, item_in: WardrobeItemCreate) -> models.WardrobeItem:
    if not await user_service.get_user_by_id(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found."
        )
    db_item = models.WardrobeItem(
        user_id=user_id,
        **item_in.model_dump()
    )
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def get_wardrobe_items_for_user(db: AsyncSession, user_id: uuid.UUID) -> List[models.WardrobeItem]:
    result = await db.execute(
        select(models.WardrobeItem).filter(models.WardrobeItem.user_id == user_id)
    )
    return result.scalars().all()

async def get_wardrobe_item_by_id(db: AsyncSession, item_id: uuid.UUID) -> Optional[models.WardrobeItem]:
    result = await db.execute(select(models.WardrobeItem).filter(models.WardrobeItem.id == item_id))
    return result.scalars().first()

async def update_wardrobe_item_for_user(
    db: AsyncSession, item_id: uuid.UUID, user_id: uuid.UUID, item_in: WardrobeItemUpdate
) -> Optional[models.WardrobeItem]:
    db_item = await get_wardrobe_item_by_id(db, item_id)
    if not db_item:
        return None
    if db_item.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User cannot update this item.")
    update_data = item_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_item, field, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def delete_wardrobe_item_for_user(db: AsyncSession, item_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    db_item = await get_wardrobe_item_by_id(db, item_id)
    if not db_item:
        return False
    if db_item.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User cannot delete this item.")
    await db.delete(db_item)
    await db.commit()
    return True