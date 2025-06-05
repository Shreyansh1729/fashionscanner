# outfitai_project/services/wardrobe_service.py
import uuid
from typing import Dict, List, Optional
from datetime import datetime ,timezone


from fastapi import HTTPException, status

from ..models.outfit_models import WardrobeItem, WardrobeItemCreate, WardrobeItemUpdate
from .user_service import get_user_by_id # To verify user exists

# In-memory "database" for wardrobe items
# Key will be the wardrobe item's UUID.
db_wardrobe_items: Dict[uuid.UUID, WardrobeItem] = {}

def add_wardrobe_item_for_user(user_id: uuid.UUID, item_in: WardrobeItemCreate) -> WardrobeItem:
    """Adds a new wardrobe item for a specific user."""
    # Check if user exists
    if not get_user_by_id(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found. Cannot add wardrobe item."
        )

    item_id = uuid.uuid4()
    db_item = WardrobeItem(
        id=item_id,
        user_id=user_id,
        **item_in.model_dump(), 
        added_at=datetime.now(timezone.utc) # Fixed
    )
    db_wardrobe_items[item_id] = db_item
    print(f"Wardrobe item '{db_item.name}' added for user {user_id}.")
    return db_item

def get_wardrobe_items_for_user(user_id: uuid.UUID) -> List[WardrobeItem]:
    """Retrieves all wardrobe items for a specific user."""
    if not get_user_by_id(user_id): # Optional: Check if user exists, or just return empty if no items
        # Depending on desired behavior, you might raise 404 if user doesn't exist
        # or simply return an empty list if the user exists but has no items.
        # For now, let's assume if no items are found for a user_id, it's just an empty list.
        # The API layer can check user existence if stricter control is needed before calling this.
        pass

    user_items = [item for item in db_wardrobe_items.values() if item.user_id == user_id]
    return user_items

def get_wardrobe_item_by_id(item_id: uuid.UUID, user_id: Optional[uuid.UUID] = None) -> Optional[WardrobeItem]:
    """
    Retrieves a specific wardrobe item by its ID.
    If user_id is provided, ensures the item belongs to that user.
    """
    item = db_wardrobe_items.get(item_id)
    if item and user_id:
        if item.user_id != user_id:
            # This case should ideally be caught by authorization layer,
            # but good for service to be aware for direct calls.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have permission to access this item."
            )
    return item


def update_wardrobe_item_for_user(
    item_id: uuid.UUID,
    user_id: uuid.UUID, # Ensure user is owner
    item_in: WardrobeItemUpdate
) -> Optional[WardrobeItem]:
    """Updates an existing wardrobe item for a specific user."""
    db_item = get_wardrobe_item_by_id(item_id)
    if not db_item:
        return None # Item not found

    if db_item.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User cannot update an item they do not own."
        )

    update_data = item_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(db_item, field): # Check if the attribute exists on the model
            setattr(db_item, field, value)
    
    db_wardrobe_items[item_id] = db_item # Re-assign to ensure the dict has the updated object
    print(f"Wardrobe item '{db_item.name}' updated for user {user_id}.")
    return db_item


def delete_wardrobe_item_for_user(item_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Deletes a wardrobe item for a specific user. Returns True if deleted, False otherwise."""
    db_item = get_wardrobe_item_by_id(item_id)
    if not db_item:
        return False # Item not found

    if db_item.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User cannot delete an item they do not own."
        )
    
    del db_wardrobe_items[item_id]
    print(f"Wardrobe item with id {item_id} deleted for user {user_id}.")
    return True