# outfitai_project/main.py
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from pathlib import Path
import uuid
from typing import Optional
import logging
from .core import image_analyzer
import asyncio

from pydantic import HttpUrl, ValidationError

# Configuration and Routers
from config.settings import settings
from .apis import routes as api_routes_v1, login_routes, context_routes ,product_routes , log_routes , wardrobe_routes, suggestion_routes , analytics_routes , history_routes , pairing_routes

# Pydantic Models for validation
from .models.outfit_models import RecommendationRequestContext, WardrobeItem as PydanticWardrobeItem
from .models.user_models import User as PydanticUser, UserUpdate

# Core logic and services
from .services import user_service, wardrobe_service
from .core import recommender
from .db.database import get_db

# --- Constants ---
MAX_IMAGE_SIZE_MB = 5
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting up {settings.PROJECT_NAME}...")
    yield
    print("Shutting down...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Include all routers
app.include_router(login_routes.router, prefix=settings.API_V1_STR)
app.include_router(context_routes.router, prefix=settings.API_V1_STR)
app.include_router(api_routes_v1.router, prefix=settings.API_V1_STR)
app.include_router(product_routes.router, prefix=settings.API_V1_STR) # <-- ADD 
app.include_router(log_routes.router, prefix=settings.API_V1_STR) # <-- ADD THIS LINE
app.include_router(wardrobe_routes.router, prefix=settings.API_V1_STR)
app.include_router(suggestion_routes.router, prefix=settings.API_V1_STR)
app.include_router(analytics_routes.router, prefix=settings.API_V1_STR)
app.include_router(history_routes.router, prefix=settings.API_V1_STR)
app.include_router(pairing_routes.router, prefix=settings.API_V1_STR)


# --- UI Endpoints ---
@app.get("/ui/recommend", response_class=HTMLResponse, tags=["UI"])
async def get_recommendation_form(request: Request, db: AsyncSession = Depends(get_db)):
    """Renders the main recommendation form for the UI."""
    users_orm = await user_service.get_all_users_in_db(db)
    users_pydantic = [PydanticUser.model_validate(user) for user in users_orm]
    return templates.TemplateResponse(
        "recommend_form.html",
        {"request": request, "users": users_pydantic, "error_message": None, "recommendation": None}
    )

@app.post("/ui/recommend", response_class=HTMLResponse, tags=["UI"])
async def handle_recommendation_form(
    request: Request,
    user_id_str: str = Form(...),
    user_photo_upload: Optional[UploadFile] = File(None),
    event_type: str = Form(...),
    style_goal: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    event_date: Optional[str] = Form(None),
    color_palette: Optional[str] = Form(None),
    inspirational_image_url_input: Optional[str] = Form(None),
    inspirational_image_upload: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Handles submission from the UI, with correct dual-analysis workflow.
    """
    users_orm = await user_service.get_all_users_in_db(db)
    users_pydantic = [PydanticUser.model_validate(user) for user in users_orm]
    error_message, recommendation_result, user_id = None, None, None
    
    # Initialize variables for the inspiration image
    inspiration_image_bytes, inspiration_image_filename = None, None

    try:
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            error_message = "Invalid user ID format."
            return templates.TemplateResponse("recommend_form.html", {"request": request, "users": users_pydantic, "error_message": error_message})

        user_profile_orm = await user_service.get_user_by_id(db, user_id)
        if not user_profile_orm:
            error_message = f"User with ID {user_id} not found."
            return templates.TemplateResponse("recommend_form.html", {"request": request, "users": users_pydantic, "error_message": error_message})

        # --- STEP A: ANALYZE AND UPDATE USER PROFILE (if user photo provided) ---
        if user_photo_upload and user_photo_upload.filename:
            logger.info(f"Analyzing uploaded user photo for user {user_id}...")
            user_image_bytes = await user_photo_upload.read()
            
            # This logic remains the same
            face_task = image_analyzer.analyze_face_attributes(user_image_bytes)
            body_skin_task = image_analyzer.analyze_skin_and_body(user_image_bytes)
            face_results, body_skin_results = await asyncio.gather(face_task, body_skin_task)
            face_results, body_skin_results = face_results or {}, body_skin_results or {}
            
            age = face_results.get('age')
            update_payload = {
                'age_range': f"{age-2}-{age+2}" if age else None,
                'gender': face_results.get('dominant_gender'),
                'skin_tone': body_skin_results.get('skin_tone'),
                'skin_color': body_skin_results.get('skin_color'),
                'body_type': body_skin_results.get('body_type')
            }
            update_data_filtered = {k: v for k, v in update_payload.items() if v}
            if update_data_filtered:
                update_dto = UserUpdate(**update_data_filtered)
                # Re-assign to ensure the 'user_profile_orm' variable has the latest data
                user_profile_orm = await user_service.update_user_in_db(db, user_id, update_dto)
                logger.info(f"User profile updated with new analysis: {update_data_filtered}")
        
        # --- STEP B: HANDLE INSPIRATION IMAGE INPUTS ---
        parsed_image_url = None
        if inspirational_image_upload and inspirational_image_upload.filename:
            if inspirational_image_upload.size > MAX_IMAGE_SIZE_BYTES:
                error_message = f"Inspiration image is too large (max {MAX_IMAGE_SIZE_MB}MB)."
            else:
                inspiration_image_bytes = await inspirational_image_upload.read()
                inspiration_image_filename = inspirational_image_upload.filename
        elif inspirational_image_url_input:
            try:
                parsed_image_url = HttpUrl(inspirational_image_url_input)
            except ValidationError:
                error_message = "Invalid inspirational image URL."
        
        if error_message:
            return templates.TemplateResponse("recommend_form.html", {"request": request, "users": users_pydantic, "selected_user_id": str(user_id), "error_message": error_message})

        # --- STEP C: PREPARE AND GENERATE RECOMMENDATION ---
        
        # Now create the context object
        context_in = RecommendationRequestContext(
            event_type=event_type,
            style_goal=style_goal,
            location=location,
            event_date=event_date,
            color_palette=color_palette,
            inspirational_image_url=parsed_image_url
        )

        user_wardrobe_orm = await wardrobe_service.get_wardrobe_items_for_user(db, user_id)
        # Create the pydantic user from the potentially updated user_profile_orm
        pydantic_user = PydanticUser.model_validate(user_profile_orm)
        pydantic_wardrobe = [PydanticWardrobeItem.model_validate(item) for item in user_wardrobe_orm]

        # Generate recommendation with all correct, final data
        recommendation_result = await recommender.create_outfit_recommendation_service(
            db=db,
            user_id=user_id,
            context_in=context_in,
            user_profile=pydantic_user,
            user_wardrobe=pydantic_wardrobe,
            inspiration_image_bytes=inspiration_image_bytes,
            inspiration_image_filename=inspiration_image_filename
        )

    except Exception as e:
        logger.error(f"Error in UI recommendation handler: {e}", exc_info=True)
        error_message = f"An unexpected error occurred: {str(e)}"

    return templates.TemplateResponse(
        "recommend_form.html",
        {
            "request": request,
            "users": users_pydantic,
            "selected_user_id": str(user_id) if user_id else None,
            "error_message": error_message,
            "recommendation": recommendation_result
        }
    )

@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/ui/recommend")
