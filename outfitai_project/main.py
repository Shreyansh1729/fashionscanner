# outfitai_project/main.py
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
import shutil
import uuid
from typing import Optional

from config.settings import settings
from .apis import routes as api_routes_v1
from .models.outfit_models import RecommendationRequestContext, OutfitRecommendation
from .models.user_models import User, UserCreate # UserCreate for the form
from .services import user_service, wardrobe_service
from .core import recommender

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOAD_DIR = BASE_DIR / "uploads"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"{Path(__file__).name}: Starting up {settings.PROJECT_NAME}...")
    # ... other startup messages ...
    print(f"User creation UI at http://127.0.0.1:8000/ui/users/create")
    yield
    print(f"{Path(__file__).name}: Shutting down {settings.PROJECT_NAME}...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

app.include_router(api_routes_v1.router, prefix=settings.API_V1_STR, tags=["API v1 Endpoints"])
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# --- User Creation UI Routes ---
@app.get("/ui/users/create", response_class=HTMLResponse, tags=["UI Pages"])
async def get_user_creation_form_page(request: Request, success_message: Optional[str] = None):
    """Serves the HTML form to create a new user."""
    return templates.TemplateResponse(
        "create_user_form.html",
        {"request": request, "error_message": None, "success_message": success_message, "user_data": {}}
    )

@app.post("/ui/users/create", response_class=HTMLResponse, tags=["UI Pages"])
async def handle_user_creation_form_submission(
    request: Request,
    email: str = Form(...),
    username: Optional[str] = Form(None),
    password: str = Form(...),
    confirm_password: str = Form(...) # For password confirmation
    # Add more fields if you want them on the UI registration form (gender, age etc.)
    # For simplicity, we'll stick to email, username, password for UI creation
):
    """Handles user creation form submission."""
    error_message: Optional[str] = None
    success_message: Optional[str] = None
    
    # Keep form data to re-populate on error
    user_form_data = {"email": email, "username": username}

    if password != confirm_password:
        error_message = "Passwords do not match."
    elif len(password) < 8: # Basic validation matching Pydantic model
        error_message = "Password must be at least 8 characters long."
    else:
        try:
            user_in = UserCreate(
                email=email,
                username=username,
                password=password
                # Default other UserCreate fields if not provided by form
            )
            created_user = user_service.create_user_in_db(user_in)
            success_message = f"User '{created_user.email}' created successfully! You can now select this user on the recommendation page."
            # Redirect to recommendation page with a success message or back to create form
            # For simplicity, let's re-render the create form with a success message
            return templates.TemplateResponse(
                "create_user_form.html",
                {"request": request, "error_message": None, "success_message": success_message, "user_data": {}} # Clear form on success
            )

        except HTTPException as e: # Catch errors from user_service (e.g., email already exists)
            error_message = e.detail
        except Exception as e:
            print(f"ERROR: Unexpected error during UI user creation: {e}")
            error_message = "An unexpected server error occurred during user creation."

    return templates.TemplateResponse(
        "create_user_form.html",
        {"request": request, "error_message": error_message, "success_message": None, "user_data": user_form_data}
    )


# --- Recommendation UI Routes (Mostly same as before, but with error handling for user ID) ---
@app.get("/ui/recommend", response_class=HTMLResponse, tags=["UI Pages"])
async def get_recommendation_form_page(request: Request):
    all_users = user_service.get_all_users_in_db()
    return templates.TemplateResponse(
        "recommend_form.html",
        {
            "request": request, "users": all_users,
            "selected_user_id": None, "event_type_val": "", "style_goal_val": "",
            "error_message": None, "recommendation": None, "uploaded_image_url": None
        }
    )

@app.post("/ui/recommend", response_class=HTMLResponse, tags=["UI Pages"])
async def handle_recommendation_form_submission(
    request: Request,
    user_id_str: str = Form(..., alias="user_id_str"),
    event_type: str = Form(...),
    style_goal: Optional[str] = Form(None),
    inspirational_image: Optional[UploadFile] = File(None)
):
    all_users = user_service.get_all_users_in_db()
    error_message: Optional[str] = None
    recommendation_result: Optional[OutfitRecommendation] = None
    image_public_url_for_context: Optional[str] = None
    uploaded_image_display_url: Optional[str] = None # For displaying back to user
    selected_user_id_on_error_or_success: Optional[str] = user_id_str

    # Validate user_id_str selection
    if not user_id_str:
        error_message = "Please select a user."
    else:
        try:
            user_id_uuid = uuid.UUID(user_id_str)
        except ValueError:
            error_message = "Invalid User ID selected. Please select a valid user from the list."
            user_id_uuid = None # Ensure it's None if conversion fails

    if not error_message and user_id_uuid: # Proceed if user_id_str was valid and converted
        user_profile = user_service.get_user_by_id(user_id_uuid)
        if not user_profile:
            error_message = f"User with ID {user_id_uuid} not found."
        else:
            if inspirational_image and inspirational_image.filename:
                if not inspirational_image.content_type or not inspirational_image.content_type.startswith("image/"):
                    error_message = "Invalid file type. Please upload an image."
                else:
                    try:
                        file_extension = Path(inspirational_image.filename).suffix.lower()
                        if file_extension not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                             error_message = "Unsupported image format. Please use JPG, PNG, GIF, or WEBP."
                        else:
                            unique_filename = f"user_{user_id_uuid}_insp_{uuid.uuid4()}{file_extension}"
                            file_save_path = UPLOAD_DIR / unique_filename
                            with open(file_save_path, "wb+") as file_object:
                                shutil.copyfileobj(inspirational_image.file, file_object)
                            
                            image_public_url_for_context = f"/uploads/{unique_filename}"
                            uploaded_image_display_url = image_public_url_for_context # Same URL for display
                            print(f"INFO: User {user_id_uuid} uploaded '{inspirational_image.filename}', saved as '{unique_filename}'")
                    except Exception as e:
                        print(f"ERROR: Saving uploaded file '{inspirational_image.filename}'. Error: {e}")
                        error_message = "Error uploading inspirational image."
            
            if not error_message:
                context_request = RecommendationRequestContext(
                    event_type=event_type, style_goal=style_goal,
                    inspirational_image_url=image_public_url_for_context # This is what LLM prompt gets
                )
                user_wardrobe_items = wardrobe_service.get_wardrobe_items_for_user(user_id_uuid)
                try:
                    print(f"DEBUG: Requesting recommendation for user {user_id_uuid} with context: {context_request.model_dump_json(indent=2)}")
                    recommendation_result = await recommender.create_outfit_recommendation_service(
                        user_id=user_id_uuid, context_in=context_request,
                        user_profile=user_profile, user_wardrobe=user_wardrobe_items
                    )
                    print(f"DEBUG: Recommendation received: ID {recommendation_result.id if recommendation_result else 'None'}")
                except HTTPException as e:
                    error_message = f"Could not get recommendation: {e.detail}"
                except Exception as e:
                    print(f"ERROR: Unexpected error in recommendation generation: {e}")
                    error_message = "An unexpected server error occurred while generating recommendation."

    return templates.TemplateResponse(
        "recommend_form.html",
        {
            "request": request, "users": all_users,
            "selected_user_id": selected_user_id_on_error_or_success if user_id_str else None, # Keep selection
            "event_type_val": event_type, "style_goal_val": style_goal,
            "uploaded_image_url": uploaded_image_display_url, # For displaying the uploaded image
            "error_message": error_message, "recommendation": recommendation_result
        }
    )

@app.get("/", include_in_schema=False)
async def root_redirect_to_ui():
    return RedirectResponse(url="/ui/recommend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("outfitai_project.main:app", host="0.0.0.0", port=8000, reload=True)