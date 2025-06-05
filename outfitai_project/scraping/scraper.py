# outfitai_project/scraping/scraper.py
import requests # requests and beautifulsoup not used in current func, but good to have if expanding
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse # Added urlparse for potential validation
from typing import Optional, Tuple

from pydantic import HttpUrl # For validation if needed, though returning str is safer for HttpUrl field

def is_valid_url(url_string: str) -> bool:
    """Helper to check if a string is a plausible URL for Pydantic HttpUrl."""
    try:
        # Basic check, Pydantic HttpUrl does more thorough validation
        parsed = urlparse(url_string)
        return all([parsed.scheme, parsed.netloc])
    except:
        return False

def find_product_urls_google_shopping(item_description: str) -> Optional[Tuple[Optional[str], Optional[str]]]:
    """
    Generates Google Shopping and Google Images search URLs based on item description.
    Returns a tuple (shopping_url, image_search_url). URLs are strings.
    """
    if not item_description:
        return None, None
        
    try:
        query = quote_plus(item_description)
        # Ensure scheme is present for HttpUrl compatibility
        shopping_search_url_str = f"https://www.google.com/search?tbm=shop&q={query}"
        image_search_url_str = f"https://www.google.com/search?tbm=isch&q={query}"
        
        print(f"INFO: Generated Google Shopping search URL for '{item_description}': {shopping_search_url_str}")
        # Return strings; Pydantic's HttpUrl will validate them upon model instantiation
        return shopping_search_url_str, image_search_url_str
    except Exception as e:
        print(f"ERROR: Error generating Google Shopping URLs for '{item_description}': {e}")
        return None, None


if __name__ == "__main__":
    desc1 = "classic white leather sneakers men"
    links1 = find_product_urls_google_shopping(desc1)
    if links1 and links1[0] and links1[1]:
        print(f"Shopping Search URL: {links1[0]}")
        # Example validation (optional here, as Pydantic model does it)
        # try:
        #     HttpUrl(links1[0])
        #     print("Shopping URL is valid HttpUrl.")
        # except Exception as val_err:
        #     print(f"Shopping URL Pydantic validation error: {val_err}")

        print(f"Image Search URL: {links1[1]}")
        # try:
        #     HttpUrl(links1[1])
        #     print("Image URL is valid HttpUrl.")
        # except Exception as val_err:
        #     print(f"Image URL Pydantic validation error: {val_err}")
    else:
        print("Failed to generate links.")

    desc2 = "" # Test empty description
    links2 = find_product_urls_google_shopping(desc2)
    if links2 and links2[0] is None:
        print(f"Handled empty description correctly: {links2}")