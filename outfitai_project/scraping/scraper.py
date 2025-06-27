# outfitai_project/scraping/scraper.py
from typing import List, Dict, Any
from urllib.parse import urlencode, quote_plus
import asyncio
import logging
import random
import time
import httpx
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
import re
from ..core import attribute_extractor # <-- NEW IMPORT
from urllib.parse import quote_plus
from urllib.parse import urljoin # <-- NEW, SAFER IMPORT

from config.settings import settings

logger = logging.getLogger(__name__)


# --- HTML PARSERS (Used by both API and Selenium methods) ---

def parse_myntra_html(html: str, base_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    products = []
    # UPDATED SELECTOR: Myntra has changed its layout. Products are now often in 'div.product-productMetaInfo' containers
    # We will search for the parent list item to keep the structure.
    for item in soup.select("li.product-base"):
        try:
            brand_tag = item.select_one("h3.product-brand")
            name_tag = item.select_one("h4.product-product")
            # This price selector is still quite robust
            price_tag = item.select_one("span.product-discountedPrice, div.product-price")
            link_tag = item.select_one("a")
            img_tag = item.select_one("img.img-responsive")

            if name_tag and brand_tag and link_tag:
                href = link_tag.get('href', '')
                #product_url = f"{base_url}{href}" if not href.startswith('http') else href
                product_url = urljoin(base_url, href)
                # A better way to handle lazy-loaded images
                image_src = None
                if img_tag and img_tag.has_attr('src'):
                    image_src = img_tag['src']
                
                products.append({
                    "retailer": "Myntra",
                    "product_name": f"{brand_tag.text.strip()} {name_tag.text.strip()}",
                    "price": price_tag.text.strip() if price_tag else "N/A",
                    "product_url": product_url,
                    "image_url": image_src
                })
        except Exception as e:
            logger.debug(f"Could not parse a Myntra item. Error: {e}")
            continue
    logger.info(f"Myntra parser found {len(products)} products.")
    return products


def parse_ajio_html(html: str, base_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    products = []
    # UPDATED SELECTOR: Looking for the a.rilrtl-products-list__item-link and then finding its parent 'item' div.
    # This is often more stable.
    for link_tag in soup.select("a.rilrtl-products-list__item-link"):
        try:
            item = link_tag.find_parent('div', class_='item')
            if not item:
                continue

            brand_tag = item.select_one("div.brand")
            name_tag = item.select_one("div.nameCls")
            price_tag = item.select_one("span.price")
            img_tag = item.select_one("img.rilrtl-lazy-img")

            if name_tag and brand_tag and link_tag:
                href = link_tag.get('href', '')
                # product_url = f"{base_url}{href}" if not href.startswith('http') else href
                product_url = urljoin(base_url, href)
                products.append({
                    "retailer": "Ajio",
                    "product_name": f"{brand_tag.text.strip()} {name_tag.text.strip()}",
                    "price": price_tag.text.strip() if price_tag else "N/A",
                    "product_url": product_url,
                    "image_url": img_tag.get('src') if img_tag else None
                })
        except Exception as e:
            logger.debug(f"Could not parse an Ajio item. Error: {e}")
            continue
    logger.info(f"Ajio parser found {len(products)} products.")
    return products


def parse_amazon_in_html(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    products = []
    for item in soup.select("div[data-component-type='s-search-result']"):
        name_tag = item.select_one("h2 a.a-link-normal span.a-text-normal")
        price_tag = item.select_one("span.a-price-whole")
        link_tag = item.select_one("h2 a.a-link-normal")
        img_tag = item.select_one("img.s-image")
        if name_tag and link_tag and price_tag:
            products.append({
                "retailer": "Amazon",
                "product_name": name_tag.text.strip(),
                "price": f"₹{price_tag.text.strip()}",
                "product_url": f"https://www.amazon.in{link_tag.get('href', '')}",
                "image_url": img_tag.get('src') if img_tag else None
            })
    return products

SITE_CONFIGS = {
    "Myntra": {"name": "Myntra", "base_url": "https://www.myntra.com", "url_template": "https://www.myntra.com/{query}", "parser": parse_myntra_html, "container_selector": "ul.results-base"},
    "Ajio": {"name": "Ajio", "base_url": "https://www.ajio.com", "url_template": "https://www.ajio.com/search/?text={query}", "parser": parse_ajio_html, "container_selector": ".list-container"},
    "Amazon": {"name": "Amazon", "base_url": "https://www.amazon.in", "url_template": "https://www.amazon.in/s?k={query}", "parser": parse_amazon_in_html, "container_selector": "div.s-main-slot"},
}

# --- 3. SCRAPING METHODS ---
CONCURRENCY_LIMIT = 2
scraper_semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

# --- Method A: 3rd Party API (Primary) ---
async def scrape_site_with_api(client: httpx.AsyncClient, query: str, retailer_name: str) -> List[Dict[str, Any]]:
    config = SITE_CONFIGS[retailer_name]
    target_url = config['url_template'].format(query=quote_plus(query))
    payload = {'api_key': settings.SCRAPER_API_KEY, 'url': target_url, 'render': 'true'}
    api_endpoint = f'http://api.scraperapi.com?{urlencode(payload)}'
    
    async with scraper_semaphore:
        logger.info(f"Scraping (JS Enabled) {retailer_name} for '{query}'...")
        try:
            await asyncio.sleep(random.uniform(1, 2))
            response = await client.get(api_endpoint, timeout=90.0)
            if response.status_code != 200:
                logger.warning(f"Got status {response.status_code} from ScraperAPI for {retailer_name}")
                return []
            return config['parser'](response.text, config['base_url'])
        except httpx.RequestError as e:
            logger.error(f"API call to ScraperAPI failed for {retailer_name}: {e}")
            return []
        


def get_google_shopping_url(query: str) -> str:
    """Generates a Google Shopping search URL for a given query."""
    return f"https://www.google.com/search?tbm=shop&q={quote_plus(query)}"



# --- Method B: Selenium (Fallback) ---
def setup_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new"); options.add_argument("--no-sandbox")
    options.add_experimental_option("excludeSwitches", ["enable-automation"]); options.add_experimental_option('useAutomationExtension', False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32")
    return driver

async def scrape_site_with_selenium(query: str, site_config: Dict) -> List[Dict[str, Any]]:
    def scraping_task() -> List[Dict[str, Any]]:
        time.sleep(random.uniform(1, 3))
        driver = setup_driver()
        try:
            url = site_config['url_template'].format(query=quote_plus(query))
            driver.get(url)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, site_config['container_selector'])))
            time.sleep(random.uniform(2, 4))
            return site_config['parser'](driver.page_source, site_config['base_url'])
        except Exception as e:
            logger.warning(f"Selenium scraping failed for {site_config['name']} with query '{query}': {e}")
            return []
        finally:
            driver.quit()
    return await asyncio.to_thread(scraping_task)


# --- 4. MASTER ORCHESTRATOR ---
# --- THIS IS THE UPDATED ORCHESTRATOR ---
async def find_products_for_query(
    query: str,
    retailers: List[str],
    limit_per_retailer: int
) -> List[Dict[str, Any]]:
    if not query or not retailers: return []
    
    logger.info(f"Initial scraping attempt for query: '{query}' on {retailers}")
    async with httpx.AsyncClient() as client:
        tasks = [scrape_site_with_api(client, query, retailer) for retailer in retailers if retailer in SITE_CONFIGS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_products = []
    for result_set in results:
        if isinstance(result_set, list):
            all_products.extend(result_set[:limit_per_retailer])

    # --- RETRY LOGIC (from your version) ---
    if not all_products and len(query.split()) > 2:
        broader_query = " ".join(query.split()[-2:]) # Using last 2 words is often safer
        logger.warning(f"Initial query for '{query}' failed. Retrying with broader query: '{broader_query}'")
        
        async with httpx.AsyncClient() as client:
            tasks = [scrape_site_with_api(client, broader_query, retailer) for retailer in retailers if retailer in SITE_CONFIGS]
            retry_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result_set in retry_results:
            if isinstance(result_set, list):
                all_products.extend(result_set[:limit_per_retailer])
    
    # If we still have no products, return an empty list.
    if not all_products:
        logger.info(f"Aggregated 0 products for query '{query}' after retry.")
        return []
    
    # --- ATTRIBUTE EXTRACTION STEP ---
    # Only if we found products, we enrich them.
    logger.info(f"Enriching {len(all_products)} raw products with structured attributes...")
    enriched_products = await attribute_extractor.extract_attributes_from_products(all_products)
    
    logger.info(f"Finished processing query '{query}'. Returning {len(enriched_products)} enriched products.")
    return enriched_products