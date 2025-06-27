from typing import Dict, Any, Optional
import numpy as np
import asyncio
import json
from PIL import Image
import io

from deepface import DeepFace
import google.generativeai as genai
from config.settings import settings


# Fallback function using Gemini for face analysis (age & gender)
async def _analyze_face_with_gemini(image_bytes: bytes) -> Optional[Dict[str, Any]]:
    if not settings.GOOGLE_GEMINI_API_KEY:
        print("Cannot use Gemini fallback, GOOGLE_GEMINI_API_KEY missing.")
        return None

    print("[INFO] DeepFace failed. Falling back to Gemini for face analysis.")
    try:
        image_for_gemini = Image.open(io.BytesIO(image_bytes))
        prompt_text = """
        Analyze the person in this image to estimate their age and identify their gender.
        Provide your response as a JSON object with two keys: 'age' (an integer) and 'dominant_gender' (a string, either "Man" or "Woman").
        Your entire response must be ONLY the JSON object.
        Example: {"age": 28, "dominant_gender": "Man"}
        """

        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = await asyncio.to_thread(
            model.generate_content,
            [prompt_text, image_for_gemini]
        )
        response_text = response.text.strip().replace("```json", "").replace("```", "")
        analysis_result = json.loads(response_text)

        if "age" in analysis_result and "dominant_gender" in analysis_result:
            return analysis_result
        return None

    except Exception as e:
        print(f"[ERROR] Gemini face analysis fallback failed: {e}")
        return None


# Main function: Analyze face attributes (tries DeepFace first)
async def analyze_face_attributes(image_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Analyzes face attributes (age, gender) from an image. Tries DeepFace first,
    then falls back to Gemini Vision.
    """
    try:
        # --- THE FIX ---
        # We are changing the detector from 'mtcnn' to 'ssd'.
        # 'ssd' is often more robust for general-purpose, clear images.
        analysis_results = await asyncio.to_thread(
            DeepFace.analyze,
            img_path=np.frombuffer(image_bytes, np.uint8),
            actions=('age', 'gender'),
            enforce_detection=True,
            detector_backend='ssd'  # <-- CHANGED FROM 'mtcnn'
        )
        
        # This part is just for printing a success message to the log
        print("[SUCCESS] Face attributes analyzed successfully using DeepFace.")
        
        if isinstance(analysis_results, list) and len(analysis_results) > 0:
            first_face = analysis_results[0]
            dominant_gender = max(first_face.get('gender', {}), key=first_face.get('gender', {}).get)
            return {"age": first_face.get('age'), "dominant_gender": dominant_gender.title()}

    except ValueError:
        print("[INFO] DeepFace could not detect a face with 'ssd' backend. Using Gemini fallback.")
        return await _analyze_face_with_gemini(image_bytes)
        
    except Exception as e:
        print(f"[ERROR] An unexpected DeepFace error occurred: {e}. Falling back to Gemini.")
        return await _analyze_face_with_gemini(image_bytes)

    # This is a final catch-all, in case the try block completes but returns nothing
    print("[INFO] DeepFace analysis was inconclusive. Using Gemini fallback.")
    return await _analyze_face_with_gemini(image_bytes)


# Skin tone, skin color, and body type analysis using Gemini
async def analyze_skin_and_body(image_bytes: bytes) -> Optional[Dict[str, Any]]:
    if not settings.GOOGLE_GEMINI_API_KEY:
        print("Cannot analyze skin/body, GOOGLE_GEMINI_API_KEY missing.")
        return None

    print("[INFO] Analyzing skin tone, skin color, and body type with Gemini...")
    try:
        image_for_gemini = Image.open(io.BytesIO(image_bytes))
        prompt_text = """
        You are an expert stylist and body analyst.

        Analyze the person in this image and classify their fashion-relevant physical features. 
        Provide your response strictly as a JSON object with three keys: "skin_tone", "skin_color", and "body_type".

        1. "skin_tone":
            - Choose one of: "Warm", "Cool", or "Neutral"
            - Warm: Yellow, golden, or olive undertones.
            - Cool: Pink, red, or bluish undertones.
            - Neutral: Balanced between warm and cool.

        2. "skin_color":
            - Choose one of: "Fair", "Light", "Medium", "Olive", "Dark", or "Deep"
            - This is the visible skin color, regardless of undertone.

        3. "body_type":
            - First, estimate the person's gender visually.
            - If the person appears **male**, choose one:
                - "Ectomorph", "Mesomorph", or "Endomorph"
            - If the person appears **female**, choose one:
                - "Rectangle", "Hourglass", "Pear", or "Apple"

        ⚠️ Your entire response must be strictly formatted as a JSON object:
        Examples:
        - Male: {"skin_tone": "Cool", "skin_color": "Medium", "body_type": "Mesomorph"}
        - Female: {"skin_tone": "Warm", "skin_color": "Olive", "body_type": "Hourglass"}

        ⚠️ Do not add any explanation or text. Only return the JSON object.
        """

        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = await asyncio.to_thread(model.generate_content, [prompt_text, image_for_gemini])
        response_text = response.text.strip().replace("```json", "").replace("```", "")
        analysis_result = json.loads(response_text)

        if all(key in analysis_result for key in ("skin_tone", "skin_color", "body_type")):
            print(f"[SUCCESS] Gemini skin/body analysis result: {analysis_result}")
            return analysis_result
        return None

    except Exception as e:
        print(f"[ERROR] Gemini skin/body analysis failed: {e}")
        return None
