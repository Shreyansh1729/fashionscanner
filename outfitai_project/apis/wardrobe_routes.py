from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from ..db.database import get_db
from ..db import orm_models as models
from ..models.outfit_models import WardrobeItem as WardrobeItemSchema, WardrobeItemCreateText
from ..models.outfit_models import ItemCategory as ItemCategoryEnum
from ..db.orm_models import AddedMethod
from ..core.security import get_current_user
from ..services import llm_service
import shutil
from pathlib import Path
from typing import List  

router = APIRouter(
    prefix="/wardrobe",
    tags=["Wardrobe Management"]
)

@router.post("/add-by-text", response_model=WardrobeItemSchema, status_code=status.HTTP_201_CREATED)
async def add_item_by_text(
    item_in: WardrobeItemCreateText,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Adds a new item to the user's wardrobe from a simple text description.
    The AI will parse the description and create a structured item.
    """
    parsed_data = llm_service.parse_item_from_text(item_in.description)
    if "error" in parsed_data or not parsed_data.get("category"):
        raise HTTPException(status_code=400, detail="Could not understand the item description.")

    # Convert category string from LLM to your Pydantic Enum member to validate
    try:
        # Pydantic's enum is in `outfit_models`, the DB one is in `orm_models`
        category_enum = ItemCategoryEnum(parsed_data.get("category"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category '{parsed_data.get('category')}' received from AI.")

    new_item = models.WardrobeItem(
        id=uuid.uuid4(), # Explicitly generate UUID
        user_id=current_user.id,
        name=parsed_data.get("name", "Unknown Item"),
        category=category_enum, # SQLAlchemy will handle the conversion
        color=parsed_data.get("color"),
        style=parsed_data.get("style"),
        material=parsed_data.get("material"),
        added_method=AddedMethod.TEXT
    )
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)
    return new_item

@router.post("/add-by-image", response_model=WardrobeItemSchema, status_code=status.HTTP_201_CREATED)
async def add_item_by_image(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    (Placeholder) Adds a new item to the user's wardrobe by uploading an image.
    The AI will analyze the image and create a structured item.
    """
    # In a real implementation:
    # 1. Read image bytes: image_bytes = await file.read()
    # 2. Upload to a cloud storage (e.g., S3) to get a persistent URL.
    # 3. Pass the image bytes or URL to a multimodal LLM (Gemini Vision) to get structured data.
    #    - This would be a new function in `llm_service.py`, similar to `parse_item_from_text`.
    # 4. Create the `WardrobeItem` in the database with the parsed data and the image URL.
    # 5. Return the created item.
    
    # For now, this is a placeholder response.
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Image upload and analysis is not yet implemented.")

@router.post("/add-by-text-bulk", response_model=List[WardrobeItemSchema], status_code=status.HTTP_201_CREATED)
async def add_items_by_text_bulk(
    item_in: WardrobeItemCreateText, # Re-using the same input schema
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Adds multiple wardrobe items from a single, comma-separated or natural
    language text description (e.g., "a blue shirt, black pants, and white sneakers").
    """
    parsed_response = llm_service.parse_multiple_items_from_text(item_in.description)
    
    if "error" in parsed_response or "items" not in parsed_response or not parsed_response["items"]:
        raise HTTPException(status_code=400, detail="Could not identify any distinct items in the description.")

    new_items_to_add = []
    created_items = []
    
    for item_data in parsed_response["items"]:
        category_str = item_data.get("category")
        if not category_str:
            continue # Skip items where the AI couldn't determine a category

        try:
            category_enum = ItemCategoryEnum(category_str)
        except ValueError:
            continue # Skip items with an invalid category

        new_item = models.WardrobeItem(
            id=uuid.uuid4(),
            user_id=current_user.id,
            name=item_data.get("name", "Unknown Item"),
            category=category_enum,
            color=item_data.get("color"),
            style=item_data.get("style"),
            material=item_data.get("material"),
            added_method=AddedMethod.TEXT
        )
        new_items_to_add.append(new_item)

    if not new_items_to_add:
        raise HTTPException(status_code=400, detail="AI identified items but could not validate any of them for addition.")

    # Add all validated items to the session
    db.add_all(new_items_to_add)
    await db.commit()

    # Refresh each item to load it from the DB and return it
    for item in new_items_to_add:
        # We need to vectorise and save to chromadb after committing to postgres
        description = f"{item.name} color {item.color} category {item.category.value} style {item.style or 'unspecified'}"
        embedding = embedding_service.get_embedding(description)
        if embedding:
            metadata = {
                "name": item.name,
                "category": item.category.value,
                "color": item.color or "unknown",
                "style": item.style or "unknown"
            }
            vector_db_service.add_or_update_item_vector(
                user_id=current_user.id, item_id=item.id, embedding=embedding, metadata=metadata
            )
        
        await db.refresh(item)
        created_items.append(item)
        
    return created_items