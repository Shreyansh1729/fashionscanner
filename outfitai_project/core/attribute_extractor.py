# outfitai_project/core/attribute_extractor.py
import json
import asyncio
from typing import Dict, Any, List

import google.generativeai as genai
from config.settings import settings

async def extract_attributes_from_products(
    products_data: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Takes a list of raw scraped products and uses an LLM to enrich them with structured attributes.
    """
    if not settings.GOOGLE_GEMINI_API_KEY:
        print("WARN: Cannot extract attributes, GOOGLE_GEMINI_API_KEY missing.")
        return products_data # Return original data if key is missing

    # Prepare one large prompt with all product titles for batch processing
    product_titles = [p.get("product_name", "") for p in products_data]
    
    prompt = f"""
    You are an expert data extraction AI for a fashion e-commerce platform.
    Your task is to analyze a list of product titles and extract structured attributes for each one.

    **ATTRIBUTES TO EXTRACT:**
    - "gender": "men", "women", or "unisex"
    - "category": "kurta", "jeans", "t-shirt", "blazer", "chinos", etc.
    - "color": "blue", "dark grey", "off-white", "multi-color", etc.
    - "material": "cotton", "linen", "denim", "silk-blend", etc. (if mentioned)
    - "fit": "slim-fit", "regular", "straight-leg", "A-line", etc. (if mentioned)
    - "brand": The brand name (e.g., "FabIndia", "Invictus").

    **INPUT LIST OF PRODUCT TITLES:**
    {json.dumps(product_titles, indent=2)}

    **INSTRUCTIONS:**
    Respond with a single JSON object containing a key "enriched_products".
    The value should be a list of JSON objects, one for each product title in the same order as the input.
    Each object should contain the extracted attributes. If an attribute is not found, omit the key.

    **EXAMPLE RESPONSE FORMAT:**
    {{
      "enriched_products": [
        {{
          "gender": "men",
          "color": "blue",
          "category": "kurta",
          "material": "cotton",
          "fit": "straight",
          "brand": "FabIndia"
        }},
        {{
          "gender": "women",
          "color": "black",
          "category": "jeans",
          "brand": "Levi's"
        }}
      ]
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        response_text = response.text.strip().replace("```json", "").replace("```", "")
        parsed_response = json.loads(response_text)
        
        enriched_list = parsed_response.get("enriched_products", [])
        
        # Merge the new attributes back into the original product data
        for i, original_product in enumerate(products_data):
            if i < len(enriched_list):
                original_product.update(enriched_list[i])
                
        return products_data

    except Exception as e:
        print(f"ERROR: Failed to extract attributes with LLM. Error: {e}")
        return products_data # Return original data on failure