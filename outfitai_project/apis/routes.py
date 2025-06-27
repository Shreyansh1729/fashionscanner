# outfitai_project/apis/routes.py
from fastapi import APIRouter, HTTPException, status, Depends, Response, Form, File, UploadFile
from typing import List, Optional
import uuid
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

# Models for request/response validation
from ..models.user_models import User, UserCreate, UserUpdate
from ..models.outfit_models import (
    WardrobeItem, WardrobeItemCreate, WardrobeItemUpdate,
    OutfitRecommendation, RecommendationRequestContext,
    SavedOutfit, SavedOutfitCreate
)
# Pydantic models needed for converting DB objects
from ..models.user_models import User as PydanticUser
from ..models.outfit_models import WardrobeItem as PydanticWardrobeItem

# Core services and helpers
from ..services import user_service, wardrobe_service
from ..core import recommender, image_analyzer, context_engine
from ..db.database import get_db
from ..core.security import get_current_user
from ..db import orm_models as models


logger = logging.getLogger(__name__)
router = APIRouter()

# --- Public Endpoint ---
@router.post("/users/", response_model=User, status_code=status.HTTP_201_CREATED, tags=["Users"])
async def create_user_endpoint(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Create a new user. This is a public endpoint."""
    return await user_service.create_user_in_db(db=db, user_in=user_in)


# --- Protected User & Profile Endpoints ---
@router.get("/users/me", response_model=User, tags=["Users"])
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    """Retrieve profile of the current logged-in user."""
    return current_user

@router.put("/users/me", response_model=User, tags=["Users"])
async def update_users_me(user_in: UserUpdate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Update the profile of the current logged-in user."""
    return await user_service.update_user_in_db(db=db, user_id=current_user.id, user_in=user_in)

@router.post("/users/me/analyze-profile", response_model=User, tags=["Users"])
async def analyze_and_update_profile(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Upload a profile picture to automatically analyze and update user attributes."""
    image_bytes = await file.read()
    face_task = image_analyzer.analyze_face_attributes(image_bytes)
    body_skin_task = image_analyzer.analyze_skin_and_body(image_bytes)
    face_results, body_skin_results = await asyncio.gather(face_task, body_skin_task)
    face_results = face_results or {}
    body_skin_results = body_skin_results or {}

    if not face_results and not body_skin_results:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not analyze image. Ensure a clear face and body are visible.")
    
    age = face_results.get('age')
    update_payload = {
        'age_range': f"{age-2}-{age+2}" if age else None,
        'gender': face_results.get('dominant_gender'),
        'skin_tone': body_skin_results.get('skin_tone'),
        'body_type': body_skin_results.get('body_type')
    }
    update_data_filtered = {k: v for k, v in update_payload.items() if v is not None}
    
    if not update_data_filtered:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Analysis did not yield any new attributes to update.")
    
    update_dto = UserUpdate(**update_data_filtered)
    updated_user = await user_service.update_user_in_db(db=db, user_id=current_user.id, user_in=update_dto)
    return updated_user


# --- Wardrobe Endpoints ---
@router.get("/wardrobe/", response_model=List[WardrobeItem], tags=["Wardrobe"])
async def get_my_wardrobe_items(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Get all wardrobe items for the current logged-in user."""
    return await wardrobe_service.get_wardrobe_items_for_user(db=db, user_id=current_user.id)

@router.post("/wardrobe/", response_model=WardrobeItem, status_code=status.HTTP_201_CREATED, tags=["Wardrobe"])
async def add_my_wardrobe_item(item_in: WardrobeItemCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Add a new wardrobe item for the current logged-in user."""
    return await wardrobe_service.add_wardrobe_item_for_user(db=db, user_id=current_user.id, item_in=item_in)

@router.put("/wardrobe/{item_id}", response_model=WardrobeItem, tags=["Wardrobe"])
async def update_my_wardrobe_item(item_id: uuid.UUID, item_in: WardrobeItemUpdate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Update a wardrobe item owned by the current logged-in user."""
    updated = await wardrobe_service.update_wardrobe_item_for_user(db=db, item_id=item_id, user_id=current_user.id, item_in=item_in)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Update failed: Item not found.")
    return updated

@router.delete("/wardrobe/{item_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Wardrobe"])
async def delete_my_wardrobe_item(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Delete a wardrobe item owned by the current logged-in user."""
    deleted = await wardrobe_service.delete_wardrobe_item_for_user(db=db, item_id=item_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delete failed: Item not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- AI Recommendation Endpoints ---
@router.post("/recommend-outfit/context", response_model=OutfitRecommendation, tags=["AI Recommendations"])
async def get_outfit_recommendation_with_context(context_in: RecommendationRequestContext, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Get an outfit recommendation using text context, an optional inspiration URL, or by flagging to use the user's profile picture."""
    if context_in.use_profile_picture_for_inspiration:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Using profile picture for inspiration is not yet implemented.")
    
    user_wardrobe_orm = await wardrobe_service.get_wardrobe_items_for_user(db, current_user.id)
    pydantic_user = PydanticUser.model_validate(current_user)
    pydantic_wardrobe = [PydanticWardrobeItem.model_validate(item) for item in user_wardrobe_orm]
    
    return await recommender.create_outfit_recommendation_service(db=db, user_id=current_user.id, context_in=context_in, user_profile=pydantic_user, user_wardrobe=pydantic_wardrobe)

@router.post("/recommend-outfit/upload", response_model=OutfitRecommendation, tags=["AI Recommendations"])
async def get_outfit_recommendation_with_upload(event_type: str = Form(...), style_goal: Optional[str] = Form(None), location: Optional[str] = Form(None), event_date: Optional[str] = Form(None), inspirational_image: UploadFile = File(...), db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Get an outfit recommendation by uploading an inspiration image."""
    context_in = RecommendationRequestContext(event_type=event_type, style_goal=style_goal, location=location, event_date=event_date)
    image_bytes = await inspirational_image.read()
    
    user_wardrobe_orm = await wardrobe_service.get_wardrobe_items_for_user(db, current_user.id)
    pydantic_user = PydanticUser.model_validate(current_user)
    pydantic_wardrobe = [PydanticWardrobeItem.model_validate(item) for item in user_wardrobe_orm]
    
    return await recommender.create_outfit_recommendation_service(db=db, user_id=current_user.id, context_in=context_in, user_profile=pydantic_user, user_wardrobe=pydantic_wardrobe, inspiration_image_bytes=image_bytes, inspiration_image_filename=inspirational_image.filename)


# --- Saved Outfits Endpoints ---
@router.post("/saved-outfits/", response_model=SavedOutfit, status_code=status.HTTP_201_CREATED, tags=["Saved Outfits"])
async def save_an_outfit(save_input: SavedOutfitCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Save a generated outfit recommendation for the current user."""
    return await recommender.save_outfit_recommendation_service(db=db, user_id=current_user.id, save_input=save_input)

@router.get("/saved-outfits/", response_model=List[SavedOutfit], tags=["Saved Outfits"])
async def get_my_saved_outfits(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Retrieve all saved outfits for the current user."""
    return await recommender.get_saved_outfits_for_user_service(db=db, user_id=current_user.id)

@router.get("/saved-outfits/{saved_outfit_id}", response_model=SavedOutfit, tags=["Saved Outfits"])
async def get_a_single_saved_outfit(saved_outfit_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Retrieve a specific saved outfit by its ID."""
    saved_outfit = await recommender.get_single_saved_outfit_service(db=db, user_id=current_user.id, saved_outfit_id=saved_outfit_id)
    if not saved_outfit: raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved outfit not found.")
    return saved_outfit

@router.delete("/saved-outfits/{saved_outfit_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Saved Outfits"])
async def delete_a_saved_outfit(saved_outfit_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Delete a saved outfit owned by the current user."""
    deleted = await recommender.delete_saved_outfit_service(db=db, user_id=current_user.id, saved_outfit_id=saved_outfit_id)
    if not deleted: raise HTTPException(status.HTTP_404_NOT_FOUND, "Delete failed: Saved outfit not found or not owned by user.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)