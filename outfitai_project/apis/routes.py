# outfitai_project/apis/routes.py
from fastapi import APIRouter, HTTPException, status, Body, Path, Response
from typing import List, Optional
import uuid

from ..models.user_models import User, UserCreate, UserUpdate
from ..models.outfit_models import (
    WardrobeItem, WardrobeItemCreate, WardrobeItemUpdate,
    OutfitRecommendation, RecommendationRequestContext,
    SavedOutfitCreate, SavedOutfit
)
from ..services import user_service, wardrobe_service
from ..core import recommender

router = APIRouter()

# --- User Endpoints (Ensure these are complete and correct) ---
@router.post("/users/", response_model=User, status_code=status.HTTP_201_CREATED, tags=["Users"])
async def create_user_endpoint(user_in: UserCreate = Body(...)): # Renamed for clarity if needed
    try: return user_service.create_user_in_db(user_in)
    except HTTPException as e: raise e
    except Exception as e: raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

@router.get("/users/", response_model=List[User], tags=["Users"])
async def read_users_endpoint(skip: int = 0, limit: int = 100): # Renamed
    return user_service.get_all_users_in_db()[skip : skip + limit]

@router.get("/users/{user_id}", response_model=User, tags=["Users"])
async def read_user_endpoint(user_id: uuid.UUID = Path(..., description="ID of user")): # Renamed
    db_user = user_service.get_user_by_id(user_id)
    if not db_user: raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return db_user

@router.put("/users/{user_id}", response_model=User, tags=["Users"])
async def update_user_endpoint(user_id: uuid.UUID = Path(..., description="ID of user"), user_in: UserUpdate = Body(...)): # Renamed
    updated_user = user_service.update_user_in_db(user_id, user_in)
    if not updated_user: raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return updated_user

# --- Wardrobe Item Endpoints (Ensure these are complete and correct) ---
@router.post("/users/{user_id}/wardrobe/", response_model=WardrobeItem, status_code=status.HTTP_201_CREATED, tags=["Wardrobe"])
async def add_wardrobe_item_endpoint(user_id: uuid.UUID = Path(..., description="ID user"), item_in: WardrobeItemCreate = Body(...)): # Renamed
    if not user_service.get_user_by_id(user_id): raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    try: return wardrobe_service.add_wardrobe_item_for_user(user_id, item_in)
    except HTTPException as e: raise e
    except Exception as e: raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

@router.get("/users/{user_id}/wardrobe/", response_model=List[WardrobeItem], tags=["Wardrobe"])
async def get_wardrobe_items_endpoint(user_id: uuid.UUID = Path(..., description="ID user")): # Renamed
    if not user_service.get_user_by_id(user_id): raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return wardrobe_service.get_wardrobe_items_for_user(user_id)

@router.get("/users/{user_id}/wardrobe/{item_id}", response_model=WardrobeItem, tags=["Wardrobe"])
async def get_single_wardrobe_item_endpoint(user_id: uuid.UUID = Path(..., description="User ID"), item_id: uuid.UUID = Path(..., description="Item ID")): # Renamed
    if not user_service.get_user_by_id(user_id): raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    item = wardrobe_service.get_wardrobe_item_by_id(item_id=item_id, user_id=user_id) # Pass user_id for ownership check in service
    if not item: raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found or no access")
    return item

@router.put("/users/{user_id}/wardrobe/{item_id}", response_model=WardrobeItem, tags=["Wardrobe"])
async def update_wardrobe_item_endpoint(user_id: uuid.UUID = Path(..., description="User ID"), item_id: uuid.UUID = Path(..., description="Item ID"), item_in: WardrobeItemUpdate = Body(...)): # Renamed
    if not user_service.get_user_by_id(user_id): raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    try: 
        updated = wardrobe_service.update_wardrobe_item_for_user(item_id, user_id, item_in)
        # Service now raises HTTPException for not found/forbidden, so this check is redundant
        # if not updated: raise HTTPException(status.HTTP_404_NOT_FOUND, "Update failed: Item not found or no access")
        return updated
    except HTTPException as e: raise e
    except Exception as e: raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

@router.delete("/users/{user_id}/wardrobe/{item_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Wardrobe"])
async def delete_wardrobe_item_endpoint(user_id: uuid.UUID = Path(..., description="User ID"), item_id: uuid.UUID = Path(..., description="Item ID")): # Renamed
    if not user_service.get_user_by_id(user_id): raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    try: 
        deleted = wardrobe_service.delete_wardrobe_item_for_user(item_id, user_id)
        # Service now raises HTTPException if not found/forbidden
        # if not deleted: raise HTTPException(status.HTTP_404_NOT_FOUND, "Delete failed: Item not found or no access")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException as e: raise e
    except Exception as e: raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

# --- AI Recommendation Endpoint ---
@router.post("/users/{user_id}/recommend-outfit/", response_model=OutfitRecommendation, tags=["AI Recommendations"])
async def get_outfit_recommendation_endpoint( # Name kept
    user_id: uuid.UUID = Path(..., description="ID of user"), context_in: RecommendationRequestContext = Body(...)
):
    user_profile = user_service.get_user_by_id(user_id)
    if not user_profile: raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    user_wardrobe = wardrobe_service.get_wardrobe_items_for_user(user_id)
    try:
        return await recommender.create_outfit_recommendation_service(
            user_id=user_id, context_in=context_in, user_profile=user_profile, user_wardrobe=user_wardrobe
        )
    except HTTPException as e: raise e
    except Exception as e:
        print(f"ERR Recommender Endpoint: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to generate recommendation: {str(e)[:100]}")

# --- Saved Outfits Endpoints (F-MVP-07) ---
@router.post("/users/{user_id}/saved-outfits/", response_model=SavedOutfit, status_code=status.HTTP_201_CREATED, tags=["Saved Outfits"])
async def create_saved_outfit_endpoint( # Name changed
    user_id: uuid.UUID = Path(..., description="User ID saving outfit"),
    save_input_body: SavedOutfitCreate = Body(..., description="Original Rec ID and user notes/rating.")
):
    if not user_service.get_user_by_id(user_id): raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    try:
        return recommender.save_outfit_recommendation_service(user_id, save_input_body)
    except HTTPException as e: raise e
    except Exception as e:
        print(f"ERR Saving Outfit: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not save outfit.")

@router.get("/users/{user_id}/saved-outfits/", response_model=List[SavedOutfit], tags=["Saved Outfits"])
async def get_user_saved_outfits_endpoint(user_id: uuid.UUID = Path(..., description="User ID")): # Name changed
    if not user_service.get_user_by_id(user_id): raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return recommender.get_saved_outfits_for_user_service(user_id)

@router.get("/users/{user_id}/saved-outfits/{saved_outfit_id}", response_model=SavedOutfit, tags=["Saved Outfits"])
async def get_user_single_saved_outfit_endpoint( # Name changed
    user_id: uuid.UUID = Path(..., description="User ID"),
    saved_outfit_id: uuid.UUID = Path(..., description="ID of the saved outfit record")
):
    if not user_service.get_user_by_id(user_id): raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    so = recommender.get_single_saved_outfit_service(user_id, saved_outfit_id)
    if not so: raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved outfit not found or no access.")
    return so

@router.delete("/users/{user_id}/saved-outfits/{saved_outfit_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Saved Outfits"])
async def delete_user_saved_outfit_endpoint( # Name changed
    user_id: uuid.UUID = Path(..., description="User ID"),
    saved_outfit_id: uuid.UUID = Path(..., description="ID of saved outfit to delete")
):
    if not user_service.get_user_by_id(user_id): raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if not recommender.delete_saved_outfit_service(user_id, saved_outfit_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delete failed: Saved outfit not found or no access.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)