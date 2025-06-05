# outfitai_project/core/recommender.py
import json
import uuid
from datetime import datetime, timezone # Added timezone for consistency
from typing import List, Optional, Dict
import asyncio

# Using google.generativeai for Gemini
import google.generativeai as genai

from fastapi import HTTPException, status

from config.settings import settings
from ..models.user_models import User
from ..models.outfit_models import (
    WardrobeItem,
    ItemCategory,
    RecommendationRequestContext,
    OutfitComponentSuggestion,
    OutfitRecommendation,
    OutfitRecommendationCreate, # Data structure expected from LLM
    SavedOutfitCreate,
    SavedOutfit
)
from ..scraping import scraper # Import the scraper module

# Configure Google Gemini API
if settings.GOOGLE_GEMINI_API_KEY:
    genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
    print(f"{datetime.now(timezone.utc)} INFO: Google Gemini API configured.")
else:
    print(f"{datetime.now(timezone.utc)} WARNING: GOOGLE_GEMINI_API_KEY not found in settings. AI recommendations via Gemini will fail.")

# Global in-memory stores
db_generated_recommendations: Dict[uuid.UUID, OutfitRecommendation] = {}
db_saved_outfits: Dict[uuid.UUID, SavedOutfit] = {}
print(f"{datetime.now(timezone.utc)} DEBUG: recommender.py module loaded. Initial db_generated_recommendations is {db_generated_recommendations}")


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

def _format_context_for_prompt(context: RecommendationRequestContext) -> str:
    context_parts: List[str] = [f"Outfit Context:"]
    context_parts.append(f"- Event/Occasion: {context.event_type}")
    if context.style_goal:
        context_parts.append(f"- Desired Style/Mood: {context.style_goal}")
    if context.inspirational_image_url:
        context_parts.append(f"- Style Inspiration (consider the style of an image found at this URL, if relevant): {str(context.inspirational_image_url)}")
    return "\n".join(context_parts)

async def _generate_and_parse_llm_response(
    user_profile_str: str,
    wardrobe_str: str,
    context_str: str
) -> OutfitRecommendationCreate:
    """Helper function to call LLM, parse response, and integrate scraping."""

    allowed_categories = ', '.join([cat.value for cat in ItemCategory])
    expected_format_description = f"""
    You MUST respond ONLY with a valid JSON object that strictly adheres to the following structure.
    Do not add any explanatory text, comments, or markdown fences like ```json ``` before or after the JSON object.
    The JSON object structure:
    {{
      "components": [
        {{
          "item_category": "A value from: {allowed_categories}",
          "description": "Detailed description of the suggested clothing item or accessory. Be specific about type, color, material, and style. Example: 'A vibrant red, A-line, knee-length, silk cocktail dress with a V-neckline.'"
        }}
      ],
      "overall_reasoning": "A brief (1-3 sentences) explanation of why this outfit is suitable for the given context and user, and how the components work together to achieve the desired style goal. Explain specific choices if relevant (e.g., why a certain color or silhouette was chosen for the user/event)."
    }}
    Ensure the 'item_category' is one of the allowed values.
    If suggesting items from the user's wardrobe, explicitly mention them by name (e.g., 'Your blue denim jacket') in the 'description' for that component.
    If suggesting new items to purchase, make that clear in the 'description'.
    Provide at least 2 components, ideally a complete outfit including appropriate accessories if the context calls for them.
    """

    prompt = f"""
    As "OutfitAI," an expert AI fashion stylist, your task is to recommend a complete and stylish outfit.
    Carefully analyze all the following information:

    {user_profile_str}

    {wardrobe_str}

    {context_str}

    Now, generate an outfit recommendation.
    Your response MUST be ONLY the JSON object, strictly following this format:
    {expected_format_description}
    """
    # print(f"{datetime.now(timezone.utc)} DEBUG: Sending prompt to Gemini:\n{prompt[:500]}...") # Log truncated prompt
    
    response_content = "" 
    try:
        if not settings.GOOGLE_GEMINI_API_KEY:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Gemini API key not configured.")

        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest',
            generation_config=genai.types.GenerationConfig(temperature=0.6)
        )
        
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        if response.parts:
            response_content = "".join(part.text for part in response.parts if hasattr(part, 'text'))
        elif hasattr(response, 'text') and response.text:
            response_content = response.text
        
        if not response_content:
            # print(f"{datetime.now(timezone.utc)} ERROR: Gemini response structure unexpected or empty. Full response: {response}") # Potentially large
            raise HTTPException(status_code=500, detail="Gemini returned an empty or malformed response. Check server logs for details.")

        # print(f"{datetime.now(timezone.utc)} DEBUG: Google Gemini Raw Response:\n{response_content}") # Potentially verbose

        response_content_cleaned = response_content.strip()
        if response_content_cleaned.startswith("```json"):
            response_content_cleaned = response_content_cleaned[7:] # Remove ```json
            if response_content_cleaned.endswith("```"):
                response_content_cleaned = response_content_cleaned[:-3] # Remove ```
        elif response_content_cleaned.startswith("```"): # Handles case where only ``` is present at start
             response_content_cleaned = response_content_cleaned[3:]
             if response_content_cleaned.endswith("```"):
                response_content_cleaned = response_content_cleaned[:-3]

        response_content_cleaned = response_content_cleaned.strip()
        
        llm_output_json = json.loads(response_content_cleaned)
        recommendation_data = OutfitRecommendationCreate(**llm_output_json)

        # Enhance components with scraped URLs
        updated_components = []
        if recommendation_data.components:
            scraper_tasks = []
            original_components = recommendation_data.components # Keep a reference for iteration
            for component_suggestion in original_components:
                if component_suggestion.description: # Only scrape if description is not empty
                    scraper_tasks.append(
                        asyncio.to_thread(scraper.find_product_urls_google_shopping, component_suggestion.description)
                    )
                else:
                    scraper_tasks.append(asyncio.sleep(0, result=(None, None))) # Placeholder for empty description

            scraped_results = await asyncio.gather(*scraper_tasks)
            
            for i, component_suggestion in enumerate(original_components):
                new_comp = component_suggestion.model_copy(deep=True)
                scraped_links_tuple = scraped_results[i]
                if scraped_links_tuple and scraped_links_tuple[0] and scraped_links_tuple[1]:
                    try:
                        new_comp.product_store_url = str(scraped_links_tuple[0])
                        new_comp.product_image_url = str(scraped_links_tuple[1])
                    except Exception as e_url: # Catch Pydantic validation error if HttpUrl type is strict
                        print(f"{datetime.now(timezone.utc)} WARNING: Could not assign scraped URLs for '{new_comp.description}'. URLs: {scraped_links_tuple}. Error: {e_url}")
                        new_comp.product_store_url = None
                        new_comp.product_image_url = None

                updated_components.append(new_comp)
        
        recommendation_data.components = updated_components
        return recommendation_data

    except json.JSONDecodeError as e:
        # print(f"{datetime.now(timezone.utc)} ERROR: Failed to decode JSON from Gemini: '{response_content}'. Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI (Gemini) failed to generate valid JSON. Error: {e}. Raw: '{response_content[:200]}...'"
        )
    except Exception as e:
        error_detail = f"AI service or processing error: {str(e)[:200]}"
        if hasattr(e, 'message') and ("API key not valid" in e.message or "PERMISSION_DENIED" in e.message):
             error_detail = "AI service (Gemini) error: API key invalid or permission denied."
        elif "quota" in str(e).lower():
             error_detail = "AI service (Gemini) error: Quota exceeded."
        # print(f"{datetime.now(timezone.utc)} ERROR: {error_detail}. Raw response (if available): '{response_content[:200]}...'")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error_detail)


async def create_outfit_recommendation_service(
    user_id: uuid.UUID,
    context_in: RecommendationRequestContext,
    user_profile: User,
    user_wardrobe: List[WardrobeItem]
) -> OutfitRecommendation:
    print(f"{datetime.now(timezone.utc)} DEBUG: create_outfit_recommendation_service called for user {user_id}.")
    if not settings.GOOGLE_GEMINI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="AI Recommender service (Gemini) is not configured."
        )
        
    user_profile_str = _format_user_profile_for_prompt(user_profile)
    wardrobe_str = _format_wardrobe_for_prompt(user_wardrobe)
    context_str = _format_context_for_prompt(context_in)

    llm_generated_data: OutfitRecommendationCreate = await _generate_and_parse_llm_response(
        user_profile_str, wardrobe_str, context_str
    )
    
    generated_recommendation = OutfitRecommendation(
        user_id=user_id,
        components=llm_generated_data.components,
        overall_reasoning=llm_generated_data.overall_reasoning,
        created_at=datetime.now(timezone.utc),
        event_type_context=context_in.event_type,
        style_goal_context=context_in.style_goal,
        inspirational_image_url_context=context_in.inspirational_image_url
    )
    
    print(f"{datetime.now(timezone.utc)} DEBUG: Before adding to db_generated_recommendations. ID to add: {generated_recommendation.id}. Current dict keys count: {len(db_generated_recommendations)}")
    db_generated_recommendations[generated_recommendation.id] = generated_recommendation
    print(f"{datetime.now(timezone.utc)} INFO: Outfit recommendation {generated_recommendation.id} generated and STORED for user {user_id}.")
    print(f"{datetime.now(timezone.utc)} DEBUG: After adding. Current dict keys count: {len(db_generated_recommendations)}")
    return generated_recommendation


def save_outfit_recommendation_service(user_id: uuid.UUID, save_input: SavedOutfitCreate) -> SavedOutfit:
    original_rec_id = save_input.original_recommendation_id
    
    print(f"{datetime.now(timezone.utc)} DEBUG: save_outfit_recommendation_service called for user {user_id}, trying to save original_rec_id '{original_rec_id}'.")
    print(f"{datetime.now(timezone.utc)} DEBUG: State of db_generated_recommendations at save attempt. Keys count: {len(db_generated_recommendations)}. Looking for {original_rec_id}")
    
    original_recommendation = db_generated_recommendations.get(original_rec_id)
    
    if not original_recommendation:
        print(f"{datetime.now(timezone.utc)} ERROR: original_rec_id '{original_rec_id}' NOT FOUND in db_generated_recommendations during save attempt.")
        # For more detailed debug:
        # print(f"{datetime.now(timezone.utc)} DEBUG: Current keys in db_generated_recommendations: {list(db_generated_recommendations.keys())}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Original recommendation with ID {original_rec_id} not found. Please generate a new one if you wish to save it."
        )
    
    print(f"{datetime.now(timezone.utc)} DEBUG: Found original_recommendation {original_rec_id} in db_generated_recommendations.")
    if original_recommendation.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User mismatch: cannot save a recommendation generated for another user.")

    for existing_saved_outfit in db_saved_outfits.values():
        if existing_saved_outfit.original_recommendation_id == original_rec_id and existing_saved_outfit.user_id == user_id:
            print(f"{datetime.now(timezone.utc)} INFO: Outfit based on original recommendation {original_rec_id} already saved by user {user_id} as {existing_saved_outfit.id}.")
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"This recommendation (original ID {original_rec_id}) has already been saved by you.")

    saved_outfit_instance = SavedOutfit(
        user_id=original_recommendation.user_id,
        created_at=original_recommendation.created_at,
        components=original_recommendation.components,
        overall_reasoning=original_recommendation.overall_reasoning,
        event_type_context=original_recommendation.event_type_context,
        style_goal_context=original_recommendation.style_goal_context,
        inspirational_image_url_context=original_recommendation.inspirational_image_url_context,
        original_recommendation_id=original_rec_id,
        saved_at=datetime.now(timezone.utc),
        user_rating=save_input.user_rating,
        user_notes=save_input.user_notes
    )
    
    db_saved_outfits[saved_outfit_instance.id] = saved_outfit_instance
    print(f"{datetime.now(timezone.utc)} INFO: Original recommendation {original_rec_id} now saved as SavedOutfit {saved_outfit_instance.id} for user {user_id}.")
    return saved_outfit_instance


def get_saved_outfits_for_user_service(user_id: uuid.UUID) -> List[SavedOutfit]:
    user_saved_outfits = [
        so for so in db_saved_outfits.values() if so.user_id == user_id
    ]
    return sorted(user_saved_outfits, key=lambda so: so.saved_at, reverse=True)

def get_single_saved_outfit_service(user_id: uuid.UUID, saved_outfit_id: uuid.UUID) -> Optional[SavedOutfit]:
    saved_outfit = db_saved_outfits.get(saved_outfit_id)
    if saved_outfit and saved_outfit.user_id == user_id:
        return saved_outfit
    return None

def delete_saved_outfit_service(user_id: uuid.UUID, saved_outfit_id: uuid.UUID) -> bool:
    saved_outfit = db_saved_outfits.get(saved_outfit_id)
    if saved_outfit and saved_outfit.user_id == user_id:
        del db_saved_outfits[saved_outfit_id]
        print(f"{datetime.now(timezone.utc)} INFO: SavedOutfit record {saved_outfit_id} deleted for user {user_id}.")
        return True
    return False