# outfitai_project/main.py
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException # Added HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
import shutil
import uuid
from typing import Optional # Added Optional

from pydantic import HttpUrl # For URL validation

from config.settings import settings
from .apis import routes as api_routes_v1
from .models.outfit_models import RecommendationRequestContext, OutfitRecommendation # For form and display
from .models.user_models import User
from .services import user_service, wardrobe_service
from .core import recommender

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
# UPLOAD_DIR = BASE_DIR / "uploads" # No longer saving inspirational images locally for this approach
# UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI): # ... (same as before)
    print(f"Starting up {settings.PROJECT_NAME}...")
    # ...
    yield
    print("Shutting down...")

app = FastAPI( # ... (same as before) ...
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

app.include_router(api_routes_v1.router, prefix=settings.API_V1_STR, tags=["API v1"])
# app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads") # No longer needed if not saving images


@app.get("/ui/recommend", response_class=HTMLResponse, tags=["UI"])
async def get_recommendation_form(request: Request): # ... (same as before)
    users = user_service.get_all_users_in_db()
    return templates.TemplateResponse(
        "recommend_form.html", 
        {"request": request, "users": users, "error_message": None, "recommendation": None}
    )

@app.post("/ui/recommend", response_class=HTMLResponse, tags=["UI"])
async def handle_recommendation_form(
    request: Request,
    user_id_str: str = Form(...),
    event_type: str = Form(...),
    style_goal: Optional[str] = Form(None),
    inspirational_image_url_input: Optional[str] = Form(None), # For URL input
    inspirational_image_upload: Optional[UploadFile] = File(None) # For file upload
):
    users = user_service.get_all_users_in_db()
    error_message = None
    recommendation_result = None
    
    inspiration_image_bytes: Optional[bytes] = None
    inspiration_image_filename: Optional[str] = None
    parsed_image_url: Optional[HttpUrl] = None

    # Validate User ID
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return templates.TemplateResponse("recommend_form.html", {"request": request, "users": users, "error_message": "Invalid User ID format.", "recommendation": None})

    user_profile = user_service.get_user_by_id(user_id)
    if not user_profile:
        return templates.TemplateResponse("recommend_form.html", {"request": request, "users": users, "error_message": f"User with ID {user_id} not found.", "recommendation": None})

    # Handle image input
    if inspirational_image_upload and inspirational_image_upload.filename:
        print(f"INFO: Received image upload: {inspirational_image_upload.filename}, size: {inspirational_image_upload.size}")
        if inspirational_image_upload.size > 5 * 1024 * 1024: # Max 5MB example limit
             error_message = "Uploaded image is too large (max 5MB)."
        else:
            try:
                inspiration_image_bytes = await inspirational_image_upload.read()
                inspiration_image_filename = inspirational_image_upload.filename
                # Clear URL input if file is uploaded to prioritize file
                parsed_image_url = None 
            except Exception as e:
                error_message = f"Error reading uploaded image: {e}"
                print(f"ERROR: Reading upload: {e}")
    elif inspirational_image_url_input:
        try:
            # Validate and parse the URL using Pydantic's HttpUrl
            parsed_image_url = HttpUrl(inspirational_image_url_input)
            print(f"INFO: Received image URL: {parsed_image_url}")
        except Exception as e: # Pydantic's ValidationError
            error_message = f"Invalid inspirational image URL provided: {e}"
            print(f"ERROR: Invalid URL: {e}")
            parsed_image_url = None # Ensure it's None if validation fails

    if error_message: # If error from user/image input, re-render form
         return templates.TemplateResponse(
            "recommend_form.html", 
            {"request": request, "users": users, "selected_user_id": str(user_id), "event_type_val": event_type, "style_goal_val": style_goal, "error_message": error_message, "recommendation": None}
        )
        
    # Proceed with recommendation
    context_in = RecommendationRequestContext(
        event_type=event_type,
        style_goal=style_goal,
        inspirational_image_url_input=parsed_image_url if parsed_image_url else None # Pass the validated HttpUrl or None
    )
    user_wardrobe = wardrobe_service.get_wardrobe_items_for_user(user_id)
    
    try:
        recommendation_result = await recommender.create_outfit_recommendation_service(
            user_id=user_id,
            context_in=context_in,
            user_profile=user_profile,
            user_wardrobe=user_wardrobe,
            inspiration_image_bytes=inspiration_image_bytes, # Pass bytes if uploaded
            inspiration_image_filename=inspiration_image_filename
        )
    except HTTPException as e:
        error_message = f"API Error: {e.status_code} - {e.detail}"
    except Exception as e:
        error_message = f"An unexpected error occurred: {str(e)}"
        print(f"ERROR: Unexpected during recommendation: {e}")


    return templates.TemplateResponse(
        "recommend_form.html", 
        {"request": request, "users": users, "selected_user_id": str(user_id), "event_type_val": event_type, "style_goal_val": style_goal, "error_message": error_message, "recommendation": recommendation_result}
    )

@app.get("/", include_in_schema=False)
async def root_redirect(): # ... (same as before)
    return RedirectResponse(url="/ui/recommend")

# Main block if running directly
if __name__ == "__main__": # ... (same as before)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)