# outfitai_project/core/recommender.py
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Union, Dict, Any
import asyncio
import httpx
from urllib.parse import quote_plus
from ..scraping.scraper import get_google_shopping_url
from ..services import product_service # <-- NEW IMPORT



import google.generativeai as genai
from PIL import Image
import io
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from pydantic import HttpUrl, ValidationError
from fastapi import HTTPException, status

from config.settings import settings
from ..models.user_models import User
from ..models.outfit_models import (
    WardrobeItem, ItemCategory, RecommendationRequestContext,
    OutfitComponentSuggestion,
    OutfitRecommendationCreate, SavedOutfitCreate, SavedOutfit, OutfitRecommendation,
    ScrapedProduct, # <-- Added ScrapedProduct for type hinting
    SortBy # <-- Added SortBy for type hinting
)
from ..scraping import scraper
# --- NEW IMPORTS for Database interaction ---
from ..db import orm_models
from . import context_engine

# Configure logging
logger = logging.getLogger(__name__)

# Configure Gemini API
if settings.GOOGLE_GEMINI_API_KEY:
    genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
else:
    print(f"{datetime.now(timezone.utc)} WARNING: GOOGLE_GEMINI_API_KEY not found.")

# ---- The following functions are UNCHANGED. They deal with generating the recommendation. ----
def _format_user_profile_for_prompt(user: User) -> str:
    profile_parts = [f"User Profile:"]
    if user.gender: profile_parts.append(f"- Gender: {user.gender}")
    if user.age_range: profile_parts.append(f"- Age Range: {user.age_range}")
    if user.body_type and user.body_type.value != "Unspecified": profile_parts.append(f"- Body Type: {user.body_type.value}")
    if user.skin_tone and user.skin_tone.value != "Unspecified": profile_parts.append(f"- Skin Tone: {user.skin_tone.value}")
    if user.height_cm: profile_parts.append(f"- Height: {user.height_cm} cm")
    if user.weight_kg: profile_parts.append(f"- Weight: {user.weight_kg} kg")
    if user.body_measurements: profile_parts.append(f"- Body Measurements: {user.body_measurements}")
    return "\n".join(profile_parts)

def _format_wardrobe_for_prompt(wardrobe_items: List[WardrobeItem]) -> str:
    if not wardrobe_items: return "User's Wardrobe: Empty. Suggest items that can be purchased."
    items_str: List[str] = ["User's Wardrobe (items they own):"]
    for item in wardrobe_items:
        item_desc = f"- {item.name} (Category: {item.category.value}"
        if item.color: item_desc += f", Color: {item.color}"
        if item.material: item_desc += f", Material: {item.material}"
        if item.brand: item_desc += f", Brand: {item.brand}"
        item_desc += ")"
        items_str.append(item_desc)
    return "\n".join(items_str)

def _format_location_weather_for_prompt(context_data: Optional[Dict[str, Any]]) -> str:
    """Formats the weather and location data into a string for the LLM prompt."""
    if not context_data or not context_data.get("weather"):
        return "**Location/Weather Context**: Not provided or unavailable."

    weather = context_data.get("weather", {})
    if "error" in weather:
        return f"**Location/Weather Context**: Weather data not available ({weather['error']})."

    loc_name = context_data.get('location_name', 'Unknown Location')
    temp = weather.get('temperature_c', 'N/A')
    condition = weather.get('condition', 'N/A')
    description = weather.get('description', 'no additional details')
    
    return (
        f"**Location & Weather Context**\n"
        f"- Location: {loc_name}\n"
        f"- Forecast for: {context_data.get('event_date', 'Today')}\n"
        f"- Temperature: {temp}°C\n"
        f"- Condition: {condition} ({description})"
    )
def _format_context_for_prompt(
    context: RecommendationRequestContext, 
    analyzed_image_desc: Optional[str]
) -> str:
    context_parts: List[str] = [f"**Event Context**"]
    context_parts.append(f"- Event/Occasion/Outfit: {context.event_type}")
    if context.style_goal: 
        context_parts.append(f"- Desired Style/Mood: {context.style_goal}")
    if analyzed_image_desc: 
        context_parts.append(f"- Analysis of Inspirational Image Provided: {analyzed_image_desc}")
    # This correctly checks for the URL from the Pydantic model
    elif context.inspirational_image_url: 
        context_parts.append(f"- User provided an inspirational image URL: {str(context.inspirational_image_url)}")
    return "\n".join(context_parts)


# In outfitai_project/core/recommender.py

async def analyze_inspirational_image(
    image_content: Union[bytes, Image.Image, None] = None, 
    image_url: Optional[HttpUrl] = None # Accepts Pydantic's HttpUrl
) -> Optional[str]:
    """
    Analyzes an inspirational image using Gemini Vision to deconstruct a fashion look.
    """
    if not settings.GOOGLE_GEMINI_API_KEY:
        return "Image analysis service unavailable."
    if not image_content and not image_url:
        return None

    print("[INFO] Starting detailed 'Look-Alike' style analysis...")
    
    # --- NEW, MORE DETAILED PROMPT FOR LOOK-ALIKE STYLING ---
    prompt_text = """
    You are a fashion analyst. Your task is to deconstruct the outfit in this image into a detailed, descriptive summary that can be used to recreate the look.

    Analyze the following, if visible:
    1.  **Overall Vibe:** Describe the style (e.g., "Bohemian Chic", "Minimalist Streetwear", "Formal Classic", "Edgy Rocker").
    2.  **Key Garments:** Identify the main pieces (e.g., "distressed high-waisted denim jeans", "oversized cashmere sweater", "A-line floral midi dress"). Be specific about cut, fit, and texture.
    3.  **Color Palette:** Describe the main colors and any accent colors.
    4.  **Accessories:** Note any significant accessories like jewelry, bags, hats, or belts.
    5.  **Occasion:** What type of event would this outfit be suitable for?

    Provide a concise, single-paragraph summary of your analysis.
    """
    
    try:
        image_for_gemini = None
        if image_content:
            image_for_gemini = Image.open(io.BytesIO(image_content))
        elif image_url:
            async with httpx.AsyncClient() as client:
                response = await client.get(str(image_url), timeout=15.0)
                response.raise_for_status()
                image_for_gemini = Image.open(io.BytesIO(response.content))
        
        if not image_for_gemini: return "No valid image content to analyze."
        
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = await asyncio.to_thread(model.generate_content, [prompt_text, image_for_gemini])

        description = response.text.strip() if hasattr(response, 'text') else ""
        
        logger.info(f"Look-Alike analysis result: {description[:150]}...")
        return description if description else "Could not generate a style analysis for the image."

    except Exception as e:
        logger.error(f"Error during 'Look-Alike' image analysis: {e}", exc_info=True)
        return "An error occurred while analyzing the inspirational image."

# --- NEW FUNCTION: Product filtering and sorting ---
def filter_and_sort_products(
    products: List[ScrapedProduct],
    sort_by: SortBy,
    min_rating: Optional[float]
) -> List[ScrapedProduct]:
    """Applies sorting and filtering to a list of scraped products."""
    
    # 1. Filter by rating (if applicable)
    # This is a placeholder for when scrapers can get ratings
    if min_rating:
        # products = [p for p in products if p.rating and p.rating >= min_rating]
        pass # Placeholder
        
    # 2. Sort the products
    if sort_by == 'price_asc':
        # Safely convert price string to float for comparison, handle non-numeric parts
        products.sort(key=lambda p: float(p.price.replace('₹', '').replace(',', '')), reverse=False)
    elif sort_by == 'price_desc':
        products.sort(key=lambda p: float(p.price.replace('₹', '').replace(',', '')), reverse=True)
    # Add logic for 'rating_desc' later if ratings are available
    # For 'default' or unknown sort_by, no specific sort is applied, maintaining original order
    
    return products

# --- START: Modified _generate_and_parse_llm_recommendation_response function ---
# In outfitai_project/core/recommender.py


async def _generate_and_parse_llm_recommendation_response(
   # db: AsyncSession,
    user_profile_str: str,
    wardrobe_str: str,
    event_context_str: str,
    location_weather_str: str,
    context_in: RecommendationRequestContext
) -> OutfitRecommendationCreate:
    
    allowed_categories = ', '.join([cat.value for cat in ItemCategory])

    expected_format_description = f"""
    {{
      "components": [
        {{
          "item_category": "A value from: {allowed_categories}",
          "description": "A highly detailed, descriptive summary of the item.",
          "search_query": "A short, 3-4 word search query INCLUDING THE GENDER (e.g., 'men white linen shirt', 'women tan loafers').",
          "attributes": {{
            "color": "e.g., 'dark wash blue', 'off-white'",
            "material": "e.g., 'denim', 'silk', 'cotton-blend'",
            "fit": "e.g., 'slim-fit', 'A-line', 'oversized'",
            "pattern": "e.g., 'floral', 'striped', 'solid'"
          }}
        }}
      ],
      "overall_reasoning": "A brief explanation for the outfit."
    }}
    """
    
    prompt = prompt = f"""
As "OutfitAI," you are a culturally-aware, world-class fashion stylist with mastery in outfit recreation, age-appropriate fashion, gender-specific styling, body shape adaptation, weather readiness, and color theory.

---

🎯 **PRIMARY OBJECTIVE: INSPIRATION-BASED OUTFIT RECREATION**
Your main task is to **recreate a complete outfit based on the provided Inspiration Image Analysis**, which represents the look the user wants to emulate.

You must:
- **Match the spirit, silhouette, and signature elements** of the inspiration image.
- **Strictly adapt the outfit to the user’s personal profile**, based on:
  - ✅ **Gender**: Suggest fashion items exclusively for the user's gender identity.
  - ✅ **Age Group**: Style recommendations must reflect age-appropriate trends.
    - For example:
      - Teens: Trendy, expressive, experimental.
      - 20s–30s: Modern, confident, versatile.
      - 40s–50s: Refined, sophisticated, elevated basics.
      - 60+: Elegant, classic, comfortable with class.
  - ✅ Cultural, regional, and personal preferences (if provided).

---

🧩 **CONTEXTUAL STYLING DIRECTIVES (Strictly Follow In Order):**

1. **EVENT & ACTIVITY PRIORITY:**
   - First analyze the `event_context` (e.g., wedding, office, pooja, hiking).
   - For **functional events** (hiking, adventure, sports), prioritize comfort and durability (e.g., hiking shoes, backpacks).
   - For **formal/cultural events** (business, wedding, traditional ceremonies), prioritize appropriate silhouettes, fabrics, and accessories.

2. **GENDER ALIGNMENT (NON-NEGOTIABLE):**
   - Every fashion item MUST match the user's gender.
   - Examples:
     - If gender = "Man" → suggest only “men’s kurta”, “men’s jeans”, “men’s jacket”.
     - If gender = "Woman" → suggest only “women’s saree”, “women’s blouse”, etc.
   - Unisex items (like sneakers or jackets) are allowed **only if they genuinely suit the outfit and event**.
   - ❗ **Absolutely no gender mismatches allowed** in categories or descriptions.

3. **AGE-APPROPRIATE STYLE FILTERING (CRITICAL):**
   - The outfit must reflect the user's **age group**.
   - Avoid youth-centric styles for older users (e.g., crop tops for 50+).
   - Avoid overly formal/conservative looks for younger users unless context demands it.
   - Fashion should feel **natural, flattering, and age-aligned**.

4. **BODY TYPE FLATTERING SILHOUETTES:**
   - Adjust garment fits to suit body shape:
     - **Pear (F):** Emphasize shoulders/top; A-line skirts.
     - **Apple (F):** Elongate torso; avoid tight waists.
     - **Hourglass (F):** Define waistline; fitted clothes.
     - **Rectangle (F):** Add shape via layering.
     - **Ectomorph (M):** Add bulk with layers or textures.
     - **Mesomorph (M):** Use well-fitted or athletic styles.
     - **Endomorph (M):** Choose structure; avoid clingy clothes.

5. **COLOR THEORY & SKIN TONE MATCHING:**
   - Color palette must enhance the user's skin tone:
     - Warm: Earthy tones like mustard, rust, olive.
     - Cool: Jewel tones like emerald, sapphire, silver.
     - Neutral: Muted pastels or mixed neutrals.
   - If a `color_palette` is specified in `event_context`, follow it strictly.

6. **LOCATION & WEATHER SMART ADAPTATION:**
   - Make the outfit **fully weather-appropriate** using `location_weather_str`.
     - Example: Adapt summer looks to winter with thermals, coats, or warmer fabrics.
   - Preserve the inspiration outfit’s essence while ensuring comfort.

7. **USE FROM WARDROBE IF POSSIBLE:**
   - Reuse relevant wardrobe items to reduce buying new ones.
   - Smartly mix owned items with new suggestions for a complete look.

---

📦 **INPUT DATA:**
{user_profile_str}

{wardrobe_str}

{event_context_str}

{location_weather_str}

---

🧠 **TASK:**
Generate a fashion-forward outfit recommendation that:
- Recreates the inspiration look authentically.
- Respects gender and age-specific styling rules.
- Flatters the body type and skin tone.
- Fits the weather, event, and available wardrobe.

---

🧾 **RESPONSE FORMAT:**
Respond with **only one valid JSON object**, adhering strictly to the expected schema.
 No markdown, comments, or additional text—**just the JSON object.**

{expected_format_description}
"""


    
    response_text = ""
    try:
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest',
            generation_config=genai.types.GenerationConfig(temperature=0.7)
        )
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        if response.parts:
            response_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))
        elif hasattr(response, 'text') and response.text:
            response_text = response.text
        else:
            raise HTTPException(status_code=500, detail="Gemini returned an empty response.")

        response_text_cleaned = response_text.strip().replace("```json", "").replace("```", "").strip()
        parsed_json = json.loads(response_text_cleaned)
        
        # --- DEFENSIVE PARSING LOGIC TO PREVENT VALIDATION ERROR ---
        final_data_to_validate = {}
        if 'components' in parsed_json:
            # Case 1: The AI returned the correct format.
            final_data_to_validate = parsed_json
        elif 'outfit' in parsed_json and isinstance(parsed_json['outfit'], dict) and 'components' in parsed_json['outfit']:
            # Case 2: The AI nested the result under an 'outfit' key.
            logger.warning("AI response was nested under an 'outfit' key. Adapting to format.")
            final_data_to_validate = parsed_json['outfit']
        else:
            # Case 3: The format is unknown and invalid.
            raise ValueError("LLM response is missing the required 'components' key at the top level.")
            
        recommendation_data = OutfitRecommendationCreate(**final_data_to_validate)

        # Scraper Integration Logic
        scraper_tasks = []
        if recommendation_data.components:
             scraper_tasks = [
                scraper.find_products_for_query(
                    comp.search_query,
                    retailers=context_in.retailers_to_search,
                    limit_per_retailer=context_in.product_limit_per_retailer
                ) for comp in recommendation_data.components if comp.search_query
            ]
        
                # --- THIS IS THE CORRECTED AND COMPLETE BLOCK ---
                # --- THIS IS THE CORRECTED AND COMPLETE BLOCK ---
        if scraper_tasks:
            all_scraped_results = await asyncio.gather(*scraper_tasks, return_exceptions=True)
            scraped_idx = 0
            for component in recommendation_data.components:
                if component.search_query:
                    raw_products = all_scraped_results[scraped_idx]
                    
                    # Check if scraping was successful and returned a non-empty list
                    if isinstance(raw_products, list) and raw_products:
                        # SUCCESS CASE: Products were found.
                        
                        validated_products = []
                        for product_data in raw_products:
                            try:
                                # Ensure we don't try to validate empty dicts
                                if product_data:
                                    validated_products.append(ScrapedProduct(**product_data))
                            except ValidationError as e:
                                logger.warning(f"Could not validate a scraped product: {product_data}. Error: {e}")
                        
                        # --- NEW: SAVE PRODUCTS TO DATABASE IN THE BACKGROUND ---
                        # This task runs independently and does not block the user's response.
                        if validated_products:
                            # IMPORTANT: This assumes 'db' session is available in this function's scope.
                            # We will need to pass it in.
                            asyncio.create_task(
                                product_service.bulk_create_or_update_products(validated_products)
                            )
                        
                        # Apply sorting and filtering to the validated products for the current response
                        component.scraped_products = filter_and_sort_products(
                            validated_products,
                            context_in.sort_by,
                            context_in.min_rating
                        )
                    else:
                        # FALLBACK CASE: Scraping failed or returned an empty list.
                        
                        logger.warning(f"Scraping for '{component.search_query}' yielded no results. Generating fallback URL.")
                        # Create the fallback search URL.
                        try:
                            # Make sure this import is at the top of recommender.py
                            from ..scraping.scraper import get_google_shopping_url 
                            component.fallback_search_url = HttpUrl(get_google_shopping_url(component.search_query))
                        except Exception as e:
                            logger.error(f"Could not create fallback URL. Error: {e}")
                            component.fallback_search_url = None

                    scraped_idx += 1
        return recommendation_data

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Pydantic validation or JSON parsing failed. Error: {e}. Raw LLM text: '{response_text[:500]}'")
        raise HTTPException(status_code=500, detail=f"AI failed to generate a valid or understandable outfit structure.")
    except Exception as e:
        logger.error(f"An unexpected error occurred in LLM/Scraper response handling: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Error processing AI response or scraping products.")
# --- Service functions are REFACTORED to use the database ---

async def create_outfit_recommendation_service(
    db: AsyncSession,
    user_id: uuid.UUID,
    context_in: RecommendationRequestContext,
    user_profile: User,  # This is the Pydantic User model
    user_wardrobe: List[WardrobeItem],
    inspiration_image_bytes: Optional[bytes] = None, # For file uploads
    inspiration_image_filename: Optional[str] = None
) -> OutfitRecommendation:
    """
    Master service to generate recommendations. Handles multiple image sources.
    """
    if not settings.GOOGLE_GEMINI_API_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI service not configured.")

    analyzed_image_description, image_source_info = None, None
    image_url_for_analysis = context_in.inspirational_image_url

    # Determine the image source based on provided inputs
    if inspiration_image_bytes:
        # Case 1: A file was uploaded
        analyzed_image_description = await analyze_inspirational_image(image_content=inspiration_image_bytes)
        image_source_info = f"Uploaded File: {inspiration_image_filename or 'image'}"
    elif image_url_for_analysis:
        # Case 2: A URL was provided in the JSON body
        analyzed_image_description = await analyze_inspirational_image(image_url=str(image_url_for_analysis))
        image_source_info = f"URL: {image_url_for_analysis}"
    # Case 3 (using profile picture) is handled in the endpoint for now

    # --- The rest of the function remains the same ---
    # Call context engine
    location_context_data = await context_engine.get_context_for_location_name(
        context_in.location, context_in.event_date
    )
    
    # Format all contexts
    user_profile_str = _format_user_profile_for_prompt(user_profile)
    wardrobe_str = _format_wardrobe_for_prompt(user_wardrobe)
    event_context_str = _format_context_for_prompt(context_in, analyzed_image_description)
    
    location_weather_str = _format_location_weather_for_prompt(location_context_data)
    
    # Call the LLM
    llm_generated_data = await _generate_and_parse_llm_recommendation_response(
        user_profile_str, wardrobe_str, event_context_str, location_weather_str,
        context_in # <-- Passed context_in here
    )
    
    # Save the recommendation to the database
    components_dict_list = [comp.model_dump(mode='json') for comp in llm_generated_data.components]
    db_recommendation = orm_models.GeneratedRecommendation(
        user_id=user_id,
        event_type_context=context_in.event_type,
        style_goal_context=context_in.style_goal,
        inspirational_image_source_info=image_source_info,
        analyzed_inspirational_image_description=analyzed_image_description,
        components_json=components_dict_list,
        overall_reasoning=llm_generated_data.overall_reasoning,
    )
    db.add(db_recommendation)
    await db.commit()
    await db.refresh(db_recommendation)
    
    # Return the final Pydantic model
    return OutfitRecommendation(
        id=db_recommendation.id,
        user_id=db_recommendation.user_id,
        created_at=db_recommendation.created_at,
        components=[OutfitComponentSuggestion(**item) for item in db_recommendation.components_json],
        overall_reasoning=db_recommendation.overall_reasoning,
        event_type_context=db_recommendation.event_type_context,
        style_goal_context=db_recommendation.style_goal_context,
        inspirational_image_source_info=db_recommendation.inspirational_image_source_info,
        analyzed_inspirational_image_description=db_recommendation.analyzed_inspirational_image_description
    )

async def save_outfit_recommendation_service(
    db: AsyncSession, user_id: uuid.UUID, save_input: SavedOutfitCreate
) -> SavedOutfit:
    # Check if the generated recommendation exists
    rec_to_save_result = await db.execute(select(orm_models.GeneratedRecommendation).where(orm_models.GeneratedRecommendation.id == save_input.generated_recommendation_id))
    rec_to_save = rec_to_save_result.scalars().first()
    if not rec_to_save:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Recommendation to save not found.")

    # Check if this user has already saved this recommendation
    existing_save_result = await db.execute(select(orm_models.SavedOutfit).where(
        orm_models.SavedOutfit.user_id == user_id,
        orm_models.SavedOutfit.recommendation_id == save_input.generated_recommendation_id
    ))
    if existing_save_result.scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Recommendation already saved.")

    db_saved_outfit = orm_models.SavedOutfit(
        user_id=user_id,
        recommendation_id=save_input.generated_recommendation_id,
        user_rating=save_input.user_rating,
        user_notes=save_input.user_notes,
    )
    db.add(db_saved_outfit)
    await db.commit()
    await db.refresh(db_saved_outfit, ["recommendation"]) # Eagerly load the related recommendation

    # Convert the ORM object to a Pydantic response model
    pydantic_recommendation = OutfitRecommendation.model_validate(db_saved_outfit.recommendation, from_attributes=True)
    return SavedOutfit(
        id=db_saved_outfit.id,
        user_id=db_saved_outfit.user_id,
        saved_at=db_saved_outfit.saved_at,
        user_rating=db_saved_outfit.user_rating,
        user_notes=db_saved_outfit.user_notes,
        recommendation=pydantic_recommendation
    )


async def get_saved_outfits_for_user_service(
    db: AsyncSession, user_id: uuid.UUID
) -> List[SavedOutfit]:
    result = await db.execute(
        select(orm_models.SavedOutfit)
        .where(orm_models.SavedOutfit.user_id == user_id)
        .options(selectinload(orm_models.SavedOutfit.recommendation)) # Eagerly load recommendations
        .order_by(orm_models.SavedOutfit.saved_at.desc())
    )
    saved_outfits_orm = result.scalars().all()

    # Convert list of ORM objects to list of Pydantic models
    response_list = []
    for so in saved_outfits_orm:
        pydantic_rec = OutfitRecommendation.model_validate(so.recommendation, from_attributes=True)
        response_list.append(SavedOutfit(
            id=so.id,
            user_id=so.user_id,
            saved_at=so.saved_at,
            user_rating=so.user_rating,
            user_notes=so.user_notes,
            recommendation=pydantic_rec
        ))
    return response_list


async def get_single_saved_outfit_service(
    db: AsyncSession, user_id: uuid.UUID, saved_outfit_id: uuid.UUID
) -> Optional[SavedOutfit]:
    result = await db.execute(
        select(orm_models.SavedOutfit)
        .where(orm_models.SavedOutfit.id == saved_outfit_id, orm_models.SavedOutfit.user_id == user_id)
        .options(selectinload(orm_models.SavedOutfit.recommendation))
    )
    so = result.scalars().first()
    if not so:
        return None
    
    pydantic_rec = OutfitRecommendation.model_validate(so.recommendation, from_attributes=True)
    return SavedOutfit(
        id=so.id,
        user_id=so.user_id,
        saved_at=so.saved_at,
        user_rating=so.user_rating,
        user_notes=so.user_notes,
        recommendation=pydantic_rec
    )


async def delete_saved_outfit_service(
    db: AsyncSession, user_id: uuid.UUID, saved_outfit_id: uuid.UUID
) -> bool:
    result = await db.execute(select(orm_models.SavedOutfit).where(
        orm_models.SavedOutfit.id == saved_outfit_id,
        orm_models.SavedOutfit.user_id == user_id
    ))
    saved_outfit_to_delete = result.scalars().first()

    if not saved_outfit_to_delete:
        return False # Not found or not owned by user
    
    await db.delete(saved_outfit_to_delete)
    await db.commit()
    return True

# --- The following are helper functions to convert ORM models with JSON to Pydantic models ---
# This is a temporary measure because OutfitRecommendation.model_validate can't directly parse components_json
# In a more advanced setup, we might use a custom Pydantic validator for this.
@classmethod
def from_orm_with_json(cls, orm_obj: orm_models.GeneratedRecommendation):
    # This helper function is now integrated into the service functions directly
    # and no longer needed as a standalone function.
    pass