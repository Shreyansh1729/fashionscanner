# In outfitai_project/services/embedding_service.py

import google.generativeai as genai
from typing import List, Union
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

# Configure the client
genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)

def get_embedding(text: Union[str, List[str]]):
    """
    Generates an embedding for a given text or list of texts.
    
    Returns:
        A list of floats for a single text, or a list of lists of floats.
    """
    if not text:
        return None
    try:
        # Using the recommended model for text search and retrieval
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="RETRIEVAL_DOCUMENT" # Use 'RETRIEVAL_QUERY' for search queries
        )
        return result['embedding']
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return None

def get_query_embedding(text: str):
    """Generates an embedding specifically for a search query."""
    if not text:
        return None
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="RETRIEVAL_QUERY" # Optimized for search
        )
        return result['embedding']
    except Exception as e:
        logger.error(f"Failed to generate query embedding: {e}")
        return None