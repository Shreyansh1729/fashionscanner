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
from . import embedding_service, vector_db_service

async def add_wardrobe_item_for_user(db: AsyncSession, user_id: uuid.UUID, item_in: WardrobeItemCreate) -> models.WardrobeItem:
    if not await user_service.get_user_by_id(db, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id {user_id} not found.")
    
    db_item = models.WardrobeItem(
        id=uuid.uuid4(), # Explicitly create UUID to use for vector DB
        user_id=user_id,
        **item_in.model_dump()
    )
    
    # --- START: VECTORIZATION LOGIC ---
    # Create a descriptive text for embedding
    description = f"{item_in.name} color {item_in.color} category {item_in.category.value} style {item_in.style or 'unspecified'}"
    
    # Generate the embedding
    embedding = embedding_service.get_embedding(description)
    
    if embedding:
        # Create metadata for filtering in the vector DB
        metadata = {
            "name": item_in.name,
            "category": item_in.category.value,
            "color": item_in.color or "unknown",
            "style": item_in.style or "unknown"
        }
        # Add the vector to ChromaDB
        vector_db_service.add_or_update_item_vector(
            user_id=user_id,
            item_id=db_item.id,
            embedding=embedding,
            metadata=metadata
        )
    # --- END: VECTORIZATION LOGIC ---

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
    
    # Update the ORM model in memory
    for field, value in update_data.items():
        if value is not None:
            setattr(db_item, field, value)

    # --- START: VECTOR UPDATE LOGIC ---
    # After updating the db_item object, re-generate its description and embedding
    new_description = (
        f"{db_item.name} color {db_item.color} category {db_item.category.value} "
        f"style {db_item.style or 'unspecified'}"
    )
    
    new_embedding = embedding_service.get_embedding(new_description)
    
    if new_embedding:
        new_metadata = {
            "name": db_item.name,
            "category": db_item.category.value,
            "color": db_item.color or "unknown",
            "style": db_item.style or "unknown"
        }
        # Use 'upsert' to update the existing vector in ChromaDB
        vector_db_service.add_or_update_item_vector(
            user_id=user_id,
            item_id=db_item.id, # Use the same ID to overwrite
            embedding=new_embedding,
            metadata=new_metadata
        )
    # --- END: VECTOR UPDATE LOGIC ---

    await db.commit()
    await db.refresh(db_item)
    return db_item


async def delete_wardrobe_item_for_user(db: AsyncSession, item_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    db_item = await get_wardrobe_item_by_id(db, item_id)
    if not db_item:
        return False
    if db_item.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User cannot delete this item.")
    
    # --- ADD DELETION FROM VECTOR DB ---
    vector_db_service.delete_item_vector(user_id=user_id, item_id=item_id)
    # --- END ---

    await db.delete(db_item)
    await db.commit()
    return True