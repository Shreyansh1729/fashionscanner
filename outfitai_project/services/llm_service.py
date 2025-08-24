import google.generativeai as genai
import json
from typing import List, Dict, Any
# our existing settings import
from config.settings import settings 

genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)

llm_model = genai.GenerativeModel('gemini-1.5-flash-latest')

def parse_item_from_text(description: str) -> Dict[str, Any]:
    """Uses LLM to convert a text description into structured WardrobeItem data."""
    prompt = f"""
    Analyze the clothing description and extract its attributes in JSON format.
    The 'category' must be one of: 'Top', 'Bottom', 'Outerwear', 'Shoes', 'Accessory', 'Dress', 'Full Body', 'Traditional', 'Other'.
    
    Description: "{description}"
    
    JSON Output (include name, category, color, style, material if possible):
    """
    
    response = llm_model.generate_content(prompt)
    try:
        json_str = response.text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(json_str)
    except (json.JSONDecodeError, AttributeError):
        return {"error": "Failed to parse item from text."}

def generate_outfit_from_wardrobe(context: Dict, wardrobe: List[Dict]) -> Dict[str, Any]:
    """Core LLM function to suggest an outfit from the available wardrobe."""
    
    wardrobe_list_str = "\n".join([f"- ID {item['id']}: {item['name']} (Category: {item['category']}, Color: {item['color']}, Style: {item['style']})" for item in wardrobe])

    prompt = f"""
    You are an expert fashion stylist. Create a complete outfit from the user's available wardrobe based on the given context.

    **Context:**
    - Occasion: {context.get('occasion')}
    - Weather: {context.get('weather')}
    - Mood: {context.get('mood', 'any')}

    **Available Wardrobe Items:**
    {wardrobe_list_str}

    **Instructions:**
    1. Select the most appropriate item(s) to form a coherent outfit. A 'Dress', 'Full Body', or 'Traditional' item can replace 'Top' and 'Bottom'.
    2. You MUST ONLY use the UUIDs from the list above. Do not invent items.
    3. If a suitable item for a special occasion (e.g., a 'Traditional' wear for 'Diwali') is NOT in the wardrobe, you MUST return a purchase recommendation.
    4. Return your suggestion as a JSON object. The keys must be the item category (e.g., "top", "bottom", "shoes") and the value is the UUID string of the chosen item.

    Example for a casual outfit: {{ "top": "uuid-for-shirt", "bottom": "uuid-for-jeans", "shoes": "uuid-for-sneakers" }}
    
    If no suitable traditional wear is found for 'Diwali', the JSON response MUST be:
    {{ "purchase_recommendation": "I couldn't find a suitable traditional outfit like a Kurta for Diwali in your wardrobe. You might consider buying one for the occasion." }}

    **Your JSON Response:**
    """

    response = llm_model.generate_content(prompt)
    try:
        json_str = response.text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(json_str)
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"LLM Response Error: {e}")
        return {"error": "Failed to generate a valid suggestion."}
    
def generate_outfit_pairings(focal_item: Dict, wardrobe: List[Dict], context: Dict, num_outfits: int = 3) -> Dict[str, Any]:
    """
    Generates multiple outfit pairings for a specific focal item.
    """
    focal_item_str = f"ID {focal_item['id']}: {focal_item['name']} (Category: {focal_item['category']}, Color: {focal_item['color']}, Style: {focal_item['style']})"
    
    # Exclude the focal item from the rest of the wardrobe list to avoid duplication
    wardrobe_list_str = "\n".join([
        f"- ID {item['id']}: {item['name']} (Category: {item['category']}, Color: {item['color']}, Style: {item['style']})"
        for item in wardrobe if item['id'] != focal_item['id']
    ])

    prompt = f"""
    You are an expert fashion stylist. Your task is to create {num_outfits} different and distinct outfits built around one specific item the user wants to wear.

    **Focal Item (MUST BE INCLUDED IN EVERY OUTFIT):**
    {focal_item_str}

    **Context for the Outfits:**
    - Occasion: {context.get('occasion', 'versatile everyday wear')}
    - Weather: {context.get('weather')}
    - Mood: {context.get('mood', 'any')}

    **Other Available Wardrobe Items:**
    {wardrobe_list_str}

    **Instructions:**
    1.  Create {num_outfits} unique and complete outfits. Each outfit must include the Focal Item.
    2.  For the other components of each outfit, you MUST ONLY use the item UUIDs provided in the 'Other Available Wardrobe Items' list.
    3.  Return your suggestions as a single JSON object with a key "outfits".
    4.  The value of "outfits" should be a list, where each element is a JSON object representing one complete outfit.
    5.  Each outfit object should use item categories as keys (e.g., "top", "bottom") and the chosen item's UUID string as the value.

    **Example JSON Response Format:**
    {{
      "outfits": [
        {{
          "top": "focal-item-uuid",
          "bottom": "uuid-for-jeans-1",
          "shoes": "uuid-for-sneakers"
        }},
        {{
          "top": "focal-item-uuid",
          "bottom": "uuid-for-skirt-2",
          "shoes": "uuid-for-heels",
          "outerwear": "uuid-for-jacket"
        }}
      ]
    }}

    **Your JSON Response:**
    """

    response = llm_model.generate_content(prompt)
    try:
        json_str = response.text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(json_str)
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"LLM Pairing Response Error: {e}")
        return {"error": "Failed to generate valid outfit pairings."}
    
def generate_weekly_outfit_plan(wardrobe: List[Dict], weekly_forecast: List[Dict], occasion: str) -> Dict[str, Any]:
    """
    Generates a multi-day outfit plan, considering weather and avoiding repetition.
    """
    wardrobe_list_str = "\n".join([f"- ID {item['id']}: {item['name']} (Category: {item['category']}, Color: {item['color']}, Style: {item['style']})" for item in wardrobe])
    forecast_str = "\n".join([f"- {day['date']}: {day['avg_temp']}°C, {day['condition']}" for day in weekly_forecast])

    prompt = f"""
    You are an expert personal stylist tasked with creating a {len(weekly_forecast)}-day outfit plan for a user.

    **Primary Goal:** Create a logical and stylish sequence of outfits for the upcoming week for the specified occasion.

    **User's Wardrobe:**
    {wardrobe_list_str}

    **Weekly Weather Forecast:**
    {forecast_str}

    **General Occasion for the Week:**
    - {occasion} (e.g., "Office Work," "Casual University Days," "Vacation")

    **Strict Instructions:**
    1.  **Plan Sequentially:** Create one complete outfit for each day in the weather forecast.
    2.  **Weather Appropriateness:** Each day's outfit MUST be appropriate for that day's specific weather.
    3.  **Avoid Repetition:** Do NOT use the same item of clothing more than once in the entire plan, unless it's a very versatile basic like jeans or a white shirt and absolutely necessary. Prioritize variety.
    4.  **Use Only Provided Items:** You MUST ONLY use the item UUIDs from the provided wardrobe list.
    5.  **Return a Single JSON Object:** The response must be a single JSON object with a key "weekly_plan".
    6.  The value of "weekly_plan" must be a list of objects, one for each day.
    7.  Each daily object must have three keys: "date", "weather_summary", and "outfit".
    8.  The "outfit" value must be an object where keys are item categories (e.g., "top", "bottom") and values are the chosen item's UUID string.

    **Example JSON Response Format:**
    {{
      "weekly_plan": [
        {{
          "date": "2025-08-26",
          "weather_summary": "22.5°C, Clouds",
          "outfit": {{ "top": "uuid-for-shirt-1", "bottom": "uuid-for-trousers-A", "shoes": "uuid-for-loafers" }}
        }},
        {{
          "date": "2025-08-27",
          "weather_summary": "24.1°C, Sun",
          "outfit": {{ "dress": "uuid-for-dress-X", "shoes": "uuid-for-sandals", "outerwear": "uuid-for-cardigan" }}
        }}
      ]
    }}

    **Your JSON Response:**
    """

    response = llm_model.generate_content(prompt)
    try:
        json_str = response.text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(json_str)
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"LLM Weekly Plan Response Error: {e}")
        return {"error": "Failed to generate a valid weekly plan."}
    
def generate_color_palettes(wardrobe_items: List[Dict[str, Any]], num_palettes: int = 4) -> Dict[str, Any]:
    """
    Analyzes a list of clothing items and suggests harmonious color palettes.
    """
    
    # Create a simple list of item names and colors for the prompt
    item_list_str = "\n".join([f"- {item['name']} (Color: {item['color']})" for item in wardrobe_items])

    prompt = f"""
    You are an expert fashion color theorist and personal stylist. Your task is to analyze the provided list of clothing items from a user's wardrobe and identify {num_palettes} distinct, harmonious color palettes that can be created using these clothes.

    **User's Wardrobe Items:**
    {item_list_str}

    **Strict Instructions:**
    1.  **Identify Palettes:** Create {num_palettes} unique and appealing color palettes.
    2.  **Name Each Palette:** Give each palette a creative, descriptive name (e.g., "Coastal Blues," "Monochromatic Grayscale," "Autumn Sunset," "Urban Explorer").
    3.  **Describe Each Palette:** Provide a brief, one-sentence description for each palette that captures its mood or best use case.
    4.  **Assign Items:** For each palette, list the EXACT item names from the provided wardrobe that fit within that color scheme. An item can appear in more than one palette if its color is versatile.
    5.  **Return a Single JSON Object:** Your response must be a single JSON object with a key "palettes".
    6.  The value of "palettes" must be a list of objects, where each object represents one color palette.
    7.  Each palette object must have three keys: "palette_name", "description", and "item_names" (which is a list of strings).

    **Example JSON Response Format:**
    {{
      "palettes": [
        {{
          "palette_name": "Earthy Tones",
          "description": "A warm and grounded palette perfect for casual autumn days.",
          "item_names": [
            "Brown Leather Boots",
            "Beige Cashmere Sweater",
            "Olive Green Chinos"
          ]
        }},
        {{
          "palette_name": "Classic Monochrome",
          "description": "A timeless and sophisticated black and white combination for any occasion.",
          "item_names": [
            "White Cotton T-Shirt",
            "Black Denim Jeans",
            "White Sneakers"
          ]
        }}
      ]
    }}

    **Your JSON Response:**
    """

    response = llm_model.generate_content(prompt)
    try:
        json_str = response.text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(json_str)
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"LLM Color Palette Response Error: {e}")
        return {"error": "Failed to generate valid color palettes."}

def parse_multiple_items_from_text(description: str) -> Dict[str, Any]:
    """
    Identifies and extracts attributes for multiple clothing items from a single text string.
    """
    prompt = f"""
    You are an expert fashion data extraction AI. Your task is to analyze the following text, identify each distinct clothing item mentioned, and extract structured attributes for each one.

    **ATTRIBUTES TO EXTRACT FOR EACH ITEM:**
    - "name": A descriptive name for the item (e.g., "blue shirt", "black pants").
    - "category": Must be one of: 'Top', 'Bottom', 'Outerwear', 'Shoes', 'Accessory', 'Dress', 'Full Body', 'Traditional', 'Other'.
    - "color": The dominant color.
    - "style": The style, if mentioned (e.g., "casual", "formal").
    - "material": The material, if mentioned (e.g., "cotton", "denim").

    **INPUT TEXT:**
    "{description}"

    **INSTRUCTIONS:**
    Respond with a single JSON object containing a key "items".
    The value should be a list of JSON objects, one for each distinct item you identified.
    If you cannot identify any items, return an empty list.

    **EXAMPLE RESPONSE FORMAT for "a red floral dress and my brown leather boots":**
    {{
      "items": [
        {{
          "name": "red floral dress",
          "category": "Dress",
          "color": "red",
          "style": "floral"
        }},
        {{
          "name": "brown leather boots",
          "category": "Shoes",
          "color": "brown",
          "material": "leather"
        }}
      ]
    }}

    **Your JSON Response:**
    """
    
    response = llm_model.generate_content(prompt)
    try:
        json_str = response.text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(json_str)
    except (json.JSONDecodeError, AttributeError):
        return {"error": "Failed to parse multiple items from text."}