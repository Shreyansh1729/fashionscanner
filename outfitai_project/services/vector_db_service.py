# In outfitai_project/services/vector_db_service.py

import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Any
import uuid
import logging

logger = logging.getLogger(__name__)

# Initialize ChromaDB client. It will store data in a 'chroma_db' directory.
client = chromadb.PersistentClient(path="./chroma_db")

# This is a placeholder. In a real app, you would pass the embedding function from embedding_service.
# For now, we'll use a mock function to set up the structure.
# We will integrate the real one in the wardrobe service.
mock_ef = embedding_functions.DefaultEmbeddingFunction()

def get_user_collection(user_id: uuid.UUID):
    """
    Gets or creates a dedicated collection for a user in ChromaDB.
    Each user's wardrobe is isolated in their own collection.
    """
    collection_name = f"user_{str(user_id).replace('-', '')}"
    try:
        # We pass the mock embedding function here because get_or_create_collection requires one,
        # but our actual embedding logic happens outside this service.
        collection = client.get_or_create_collection(name=collection_name, embedding_function=mock_ef)
        return collection
    except Exception as e:
        logger.error(f"Failed to get or create Chroma collection for user {user_id}: {e}")
        return None

def add_or_update_item_vector(user_id: uuid.UUID, item_id: uuid.UUID, embedding: List[float], metadata: Dict[str, Any]):
    """Adds or updates an item's vector in the user's collection."""
    collection = get_user_collection(user_id)
    if collection:
        collection.upsert(
            ids=[str(item_id)],
            embeddings=[embedding],
            metadatas=[metadata]
        )
        logger.info(f"Upserted vector for item {item_id} for user {user_id}.")

def search_similar_items(user_id: uuid.UUID, query_embedding: List[float], n_results: int = 10) -> List[Dict[str, Any]]:
    """Searches for the most similar items in a user's collection based on a query vector."""
    collection = get_user_collection(user_id)
    if not collection or not query_embedding:
        return []
        
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )
    
    # The result is nested; we need to extract the documents and distances
    if results and results['ids'] and len(results['ids'][0]) > 0:
        return [{"id": results['ids'][0][i], "metadata": results['metadatas'][0][i], "distance": results['distances'][0][i]} for i in range(len(results['ids'][0]))]
    
    return []

def delete_item_vector(user_id: uuid.UUID, item_id: uuid.UUID):
    """Deletes an item's vector from the user's collection."""
    collection = get_user_collection(user_id)
    if collection:
        collection.delete(ids=[str(item_id)])
        logger.info(f"Deleted vector for item {item_id} for user {user_id}.")