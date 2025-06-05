# outfitai_project/core/recommender.py
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Union
import asyncio
import httpx # For fetching image from URL

import google.generativeai as genai
from PIL import Image # For handling image bytes with Gemini
import io # For byte streams

from fastapi import HTTPException, status

from config.settings import settings
from ..models.user_models import User
from ..models.outfit_models import (
    WardrobeItem, ItemCategory, RecommendationRequestContext,
    OutfitComponentSuggestion, OutfitRecommendation, OutfitRecommendationCreate,
    SavedOutfitCreate, SavedOutfit
)
from ..scraping import scraper

if settings.GOOGLE_GEMINI_API_KEY:
    genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
    print(f"{datetime.now(timezone.utc)} INFO: Google Gemini API configured.")
else:
    print(f"{datetime.now(timezone.utc)} WARNING: GOOGLE_GEMINI_API_KEY not found. AI recommendations via Gemini will fail.")

db_generated_recommendations: Dict[uuid.UUID, OutfitRecommendation] = {}
db_saved_outfits: Dict[uuid.UUID, SavedOutfit] = {}
# print(f"{datetime.now(timezone.utc)} DEBUG: recommender.py module loaded. Initial db_generated_recommendations is {db_generated_recommendations}")


def _format_user_profile_for_prompt(user: User) -> str: # ... (same as before)
    profile_parts = [f"User Profile:"]
    if user.gender: profile_parts.append(f"- Gender: {user.gender}")
    if user.age_range: profile_parts.append(f"- Age Range: {user.age_range}")
    if user.body_type and user.body_type.value != "Unspecified": profile_parts.append(f"- Body Type: {user.body_type.value}")
    if user.skin_tone and user.skin_tone.value != "Unspecified": profile_parts.append(f"- Skin Tone: {user.skin_tone.value}")
    if user.height_cm: profile_parts.append(f"- Height: {user.height_cm} cm")
    if user.weight_kg: profile_parts.append(f"- Weight: {user.weight_kg} kg")
    if user.body_measurements: profile_parts.append(f"- Body Measurements: {user.body_measurements}")
    return "\n".join(profile_parts)

def _format_wardrobe_for_prompt(wardrobe_items: List[WardrobeItem]) -> str: # ... (same as before)
    if not wardrobe_items:
        return "User's Wardrobe: Empty. Suggest items that can be purchased."
    items_str: List[str] = ["User's Wardrobe (items they own):"]
    for item in wardrobe_items:
        item_desc = f"- {item.name} (Category: {item.category.value}"
        if item.color: item_desc += f", Color: {item.color}"
        if item.material: item_desc += f", Material: {item.material}"
        if item.brand: item_desc += f", Brand: {item.brand}"
        item_desc += ")"
        items_str.append(item_desc)
    return "\n".join(items_str)

# MODIFIED to include analyzed image description
def _format_context_for_prompt(context: RecommendationRequestContext, analyzed_image_desc: Optional[str]) -> str:
    context_parts: List[str] = [f"Outfit Context:"]
    context_parts.append(f"- Event/Occasion: {context.event_type}")
    if context.style_goal:
        context_parts.append(f"- Desired Style/Mood: {context.style_goal}")
    
    if analyzed_image_desc:
        context_parts.append(f"- Analysis of Inspirational Image Provided: {analyzed_image_desc}")
    elif context.inspirational_image_url_input: # If URL was provided but analysis failed or not done yet
        context_parts.append(f"- User provided an inspirational image URL (consider its implied style): {str(context.inspirational_image_url_input)}")
    return "\n".join(context_parts)


async def analyze_inspirational_image(
    image_content: Union[bytes, Image.Image, None] = None, 
    image_url: Optional[str] = None
) -> Optional[str]:
    """
    Analyzes an inspirational image using Gemini Vision to extract fashion details.
    Accepts image_content (bytes or PIL.Image) or an image_url.
    """
    if not settings.GOOGLE_GEMINI_API_KEY:
        print(f"{datetime.now(timezone.utc)} WARNING: Cannot analyze image, GOOGLE_GEMINI_API_KEY missing.")
        return "Image analysis service unavailable due to missing API key."

    if not image_content and not image_url:
        return None # No image provided

    print(f"{datetime.now(timezone.utc)} INFO: Starting inspirational image analysis...")

    # Prepare parts for Gemini API request
    # Gemini API expects image parts to be PIL.Image objects or dicts like {'mime_type': 'image/jpeg', 'data': b'...'}.
    # For simplicity, we'll convert bytes to PIL.Image.
    
    parts = []
    prompt_text = "Analyze this image for fashion insights. Describe the key clothing items, their colors, materials (if discernible), styles (e.g., casual, formal, bohemian, minimalist), patterns, and the overall vibe or occasion it might suit. Focus on objective descriptions. Be concise but informative."
    parts.append(prompt_text)

    try:
        img_to_process = None
        if image_content:
            if isinstance(image_content, bytes):
                img_to_process = Image.open(io.BytesIO(image_content))
            elif isinstance(image_content, Image.Image):
                img_to_process = image_content
        elif image_url:
            # Fetch image from URL if PIL.Image from URL is not directly supported or fails
            # Gemini's Python SDK can handle image fetching for common types, but let's try to be explicit.
            print(f"{datetime.now(timezone.utc)} INFO: Fetching image from URL for analysis: {image_url}")
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url, timeout=10.0)
                response.raise_for_status() # Raise an exception for bad status codes
                img_to_process = Image.open(io.BytesIO(response.content))
        
        if img_to_process:
            parts.append(img_to_process)
        else:
            return "No valid image content to analyze."

        # Use a model that supports vision, e.g., 'gemini-1.5-flash-latest' or 'gemini-pro-vision'
        # For 'gemini-1.5-flash-latest', it can infer vision capabilities.
        # 'gemini-pro-vision' is explicitly for vision.
        vision_model = genai.GenerativeModel(
            'gemini-1.5-flash-latest', # or 'gemini-pro-vision' for older SDK/explicit model
             generation_config=genai.types.GenerationConfig(temperature=0.3) # Less creative for description
        )
        
        # Use generate_content with parts list for multimodal input
        print(f"{datetime.now(timezone.utc)} DEBUG: Sending image analysis request to Gemini with {len(parts)-1} image(s).")
        # response = await vision_model.generate_content_async(parts) # Older SDK
        response = await asyncio.to_thread(vision_model.generate_content, parts) # Synchronous call in thread


        description = ""
        if response.parts:
            description = "".join(part.text for part in response.parts if hasattr(part, 'text'))
        elif hasattr(response, 'text') and response.text:
            description = response.text

        print(f"{datetime.now(timezone.utc)} INFO: Inspirational image analysis result: {description[:200]}...")
        return description.strip() if description else "Could not analyze the image content."

    except httpx.RequestError as e:
        print(f"{datetime.now(timezone.utc)} ERROR: Failed to fetch image from URL '{image_url}': {e}")
        return f"Failed to fetch image from URL: {e}"
    except Exception as e:
        print(f"{datetime.now(timezone.utc)} ERROR: Exception during image analysis: {e}")
        # Check if it's an API key error
        if "API key not valid" in str(e) or "PERMISSION_DENIED" in str(e):
            return "Image analysis failed: API key issue or permission denied."
        return f"Could not analyze image: {str(e)}"


async def _generate_and_parse_llm_recommendation_response( # Renamed for clarity
    user_profile_str: str,
    wardrobe_str: str,
    context_str_with_image_analysis: str # This now includes the analyzed image desc
) -> OutfitRecommendationCreate:
    # ... (This function's internal prompt for *outfit generation* and parsing logic largely remains the same)
    # ... (as in previous correct versions, just ensure it takes the combined context_str)
    allowed_categories = ', '.join([cat.value for cat in ItemCategory])
    expected_format_description = f"""
    You MUST respond ONLY with a valid JSON object that strictly adheres to the following structure.
    Do not add any explanatory text, comments, or markdown fences like ```json ``` before or after the JSON object.
    The JSON object structure:
    {{
      "components": [
        {{
          "item_category": "A value from: {allowed_categories}",
          "description": "Detailed description of the suggested clothing item or accessory."
        }}
      ],
      "overall_reasoning": "A brief (1-3 sentences) explanation of why this outfit is suitable."
    }}
    """ # Simplified format instruction for this example

    prompt = f"""
    As "OutfitAI," an expert AI fashion stylist, your task is to recommend a complete and stylish outfit.
    Carefully analyze all the following information:

    {user_profile_str}

    {wardrobe_str}

    {context_str_with_image_analysis} 

    Now, generate an outfit recommendation.
    Your response MUST be ONLY the JSON object, strictly following this format:
    {expected_format_description}
    """
    response_content = "" 
    try:
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest',
            generation_config=genai.types.GenerationConfig(temperature=0.7) # Main recommendation can be more creative
        )
        response = await asyncio.to_thread(model.generate_content, prompt)
        # ... (response processing, JSON cleaning, and parsing as before) ...
        if response.parts: response_content = "".join(part.text for part in response.parts if hasattr(part, 'text'))
        elif hasattr(response, 'text') and response.text: response_content = response.text
        if not response_content: raise HTTPException(status_code=500, detail="Gemini (recommendation) returned empty.")
        
        response_content_cleaned = response_content.strip()
        if response_content_cleaned.startswith("```json"): response_content_cleaned = response_content_cleaned[7:-3] if response_content_cleaned.endswith("```") else response_content_cleaned[7:]
        elif response_content_cleaned.startswith("```"): response_content_cleaned = response_content_cleaned[3:-3] if response_content_cleaned.endswith("```") else response_content_cleaned[3:]
        response_content_cleaned = response_content_cleaned.strip()

        llm_output_json = json.loads(response_content_cleaned)
        recommendation_data = OutfitRecommendationCreate(**llm_output_json)

        # Enhance components with scraped URLs
        updated_components = []
        if recommendation_data.components:
            scraper_tasks = [
                asyncio.to_thread(scraper.find_product_urls_google_shopping, comp.description) if comp.description else asyncio.sleep(0, result=(None,None))
                for comp in recommendation_data.components
            ]
            scraped_results = await asyncio.gather(*scraper_tasks)
            for i, component_suggestion in enumerate(recommendation_data.components):
                new_comp = component_suggestion.model_copy(deep=True)
                scraped_links_tuple = scraped_results[i]
                if scraped_links_tuple and scraped_links_tuple[0] and scraped_links_tuple[1]:
                    try:
                        new_comp.product_store_url = str(scraped_links_tuple[0])
                        new_comp.product_image_url = str(scraped_links_tuple[1])
                    except Exception: pass # Ignore Pydantic HttpUrl validation errors during assignment for now
                updated_components.append(new_comp)
        recommendation_data.components = updated_components
        return recommendation_data
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500,detail=f"AI (reco) failed to gen JSON. Err: {e}. Raw: '{response_content[:100]}...'")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service (reco) or processing error: {str(e)[:100]}")


async def create_outfit_recommendation_service(
    user_id: uuid.UUID,
    context_in: RecommendationRequestContext,
    user_profile: User,
    user_wardrobe: List[WardrobeItem],
    # New parameters for image handling from the endpoint
    inspiration_image_bytes: Optional[bytes] = None,
    inspiration_image_filename: Optional[str] = None # For logging/reference
) -> OutfitRecommendation:
    print(f"{datetime.now(timezone.utc)} DEBUG: create_outfit_recommendation_service called for user {user_id}.")
    if not settings.GOOGLE_GEMINI_API_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI Recommender service (Gemini) is not configured.")
    
    analyzed_image_description: Optional[str] = None
    image_source_info: Optional[str] = None

    if inspiration_image_bytes:
        analyzed_image_description = await analyze_inspirational_image(image_content=inspiration_image_bytes)
        image_source_info = f"Uploaded: {inspiration_image_filename or 'image'}"
    elif context_in.inspirational_image_url_input:
        analyzed_image_description = await analyze_inspirational_image(image_url=str(context_in.inspirational_image_url_input))
        image_source_info = f"URL: {context_in.inspirational_image_url_input}"

    user_profile_str = _format_user_profile_for_prompt(user_profile)
    wardrobe_str = _format_wardrobe_for_prompt(user_wardrobe)
    # Pass the original context AND the analyzed image description to format the final context string
    context_str_with_analysis = _format_context_for_prompt(context_in, analyzed_image_description)
    
    llm_generated_data: OutfitRecommendationCreate = await _generate_and_parse_llm_recommendation_response(
        user_profile_str, wardrobe_str, context_str_with_analysis
    )
    
    generated_recommendation = OutfitRecommendation(
        user_id=user_id,
        components=llm_generated_data.components,
        overall_reasoning=llm_generated_data.overall_reasoning,
        created_at=datetime.now(timezone.utc),
        event_type_context=context_in.event_type,
        style_goal_context=context_in.style_goal,
        inspirational_image_source_info=image_source_info, # Store source info
        analyzed_inspirational_image_description=analyzed_image_description # Store LLM's analysis
    )
    
    db_generated_recommendations[generated_recommendation.id] = generated_recommendation
    print(f"{datetime.now(timezone.utc)} INFO: Outfit recommendation {generated_recommendation.id} generated and STORED for user {user_id}.")
    return generated_recommendation


def save_outfit_recommendation_service(user_id: uuid.UUID, save_input: SavedOutfitCreate) -> SavedOutfit: # ... (same as before)
    original_rec_id = save_input.original_recommendation_id
    original_recommendation = db_generated_recommendations.get(original_rec_id)
    if not original_recommendation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Original rec {original_rec_id} not found.")
    if original_recommendation.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="User mismatch.")
    for existing_saved_outfit in db_saved_outfits.values():
        if existing_saved_outfit.original_recommendation_id == original_rec_id and existing_saved_outfit.user_id == user_id:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Recommendation already saved.")
    saved_outfit_instance = SavedOutfit(
        # Copy fields from original_recommendation
        id=uuid.uuid4(), # New ID for saved outfit
        user_id=original_recommendation.user_id,
        created_at=original_recommendation.created_at,
        event_type_context=original_recommendation.event_type_context,
        style_goal_context=original_recommendation.style_goal_context,
        inspirational_image_source_info=original_recommendation.inspirational_image_source_info,
        analyzed_inspirational_image_description=original_recommendation.analyzed_inspirational_image_description,
        components=original_recommendation.components,
        overall_reasoning=original_recommendation.overall_reasoning,
        # Add SavedOutfit specific fields
        original_recommendation_id=original_rec_id,
        saved_at=datetime.now(timezone.utc),
        user_rating=save_input.user_rating,
        user_notes=save_input.user_notes
    )
    db_saved_outfits[saved_outfit_instance.id] = saved_outfit_instance
    return saved_outfit_instance

def get_saved_outfits_for_user_service(user_id: uuid.UUID) -> List[SavedOutfit]: # ... (same as before)
    return sorted([so for so in db_saved_outfits.values() if so.user_id == user_id], key=lambda so: so.saved_at, reverse=True)

def get_single_saved_outfit_service(user_id: uuid.UUID, saved_outfit_id: uuid.UUID) -> Optional[SavedOutfit]: # ... (same as before)
    so = db_saved_outfits.get(saved_outfit_id)
    return so if so and so.user_id == user_id else None

def delete_saved_outfit_service(user_id: uuid.UUID, saved_outfit_id: uuid.UUID) -> bool: # ... (same as before)
    so = db_saved_outfits.get(saved_outfit_id)
    if so and so.user_id == user_id:
        del db_saved_outfits[saved_outfit_id]
        return True
    return False