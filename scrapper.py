import requests
from bs4 import BeautifulSoup
import csv
import json
import time
import random
import logging
from pathlib import Path
from urllib.parse import urljoin

# ========== CONFIG ==========


BASE_URL = "https://books.toscrape.com/"
CATALOG_URL = urljoin(BASE_URL, "catalogue/page-1.html")

OUTPUT_CSV = "products.csv"
OUTPUT_JSON = "products.json"
LOG_FILE = "scraper.log"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

DELAY_MIN = 0.8
DELAY_MAX = 1.8
MAX_RETRIES = 3

RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

# ========== LOGGING SETUP ==========

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ========== CORE FUNCTIONS ==========

def fetch_with_retry(url: str, max_retries: int = MAX_RETRIES) -> requests.Response | None:
    """Fetches a URL with retry + exponential backoff on failure."""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            wait = 2 ** attempt
            logger.warning(f"Attempt {attempt}/{max_retries} failed for {url}: {e}. Retrying in {wait}s...")
            time.sleep(wait)

    logger.error(f"Giving up on {url} after {max_retries} attempts.")
    return None


def parse_product_card(card, category: str) -> dict | None:
    """Extracts data from a single product card on a catalogue page."""
    try:
        title_tag = card.find("h3").find("a")
        title = title_tag["title"]

        price_tag = card.find("p", class_="price_color")
        price_text = price_tag.get_text(strip=True)
        price = float(price_text.replace("£", "").replace("Â", ""))

        availability_tag = card.find("p", class_="instock availability")
        in_stock = "In stock" in availability_tag.get_text(strip=True)

        rating_tag = card.find("p", class_="star-rating")
        rating_word = rating_tag["class"][1]  # e.g. class="star-rating Three"
        rating = RATING_MAP.get(rating_word, None)

        relative_link = title_tag["href"]
        product_url = urljoin(CATALOG_URL, relative_link)

        return {
            "title": title,
            "price_gbp": price,
            "in_stock": in_stock,
            "rating": rating,
            "category": category,
            "url": product_url,
        }
    except (AttributeError, KeyError, ValueError) as e:
        logger.warning(f"Skipping a malformed product card: {e}")
        return None


def get_next_page_url(soup: BeautifulSoup, current_url: str) -> str | None:
    """Finds the 'next page' link, if it exists. Returns None on the last page."""
    next_button = soup.find("li", class_="next")
    if not next_button:
        return None
    next_href = next_button.find("a")["href"]
    return urljoin(current_url, next_href)


def scrape_catalog(start_url: str, max_pages: int | None = None) -> list[dict]:
    """
    Crawls the full catalogue, page by page, until there's no 'next' page
    or max_pages is reached (useful for quick tests without scraping everything).
    """
    all_products = []
    current_url = start_url
    page_num = 1

    while current_url:
        if max_pages and page_num > max_pages:
            logger.info(f"Reached max_pages limit ({max_pages}), stopping.")
            break

        logger.info(f"Scraping page {page_num}: {current_url}")
        response = fetch_with_retry(current_url)
        if response is None:
            break

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.find_all("article", class_="product_pod")

        for card in cards:
            product = parse_product_card(card, category="All")
            if product:
                all_products.append(product)

        current_url = get_next_page_url(soup, current_url)
        page_num += 1

        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    logger.info(f"Finished. Scraped {len(all_products)} products across {page_num - 1} pages.")
    return all_products


def save_to_csv(data: list[dict], filename: str):
    if not data:
        logger.warning("No data to save to CSV.")
        return
    keys = data[0].keys()
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys, delimiter=";")
        writer.writeheader()
        writer.writerows(data)
    logger.info(f"Saved {len(data)} products to {filename}")


def save_to_json(data: list[dict], filename: str):
    if not data:
        logger.warning("No data to save to JSON.")
        return
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(data)} products to {filename}")


# ========== ENTRY POINT ==========

if __name__ == "__main__":
    logger.info("Starting scrape...")

    products = scrape_catalog(CATALOG_URL, max_pages=3)

    save_to_csv(products, OUTPUT_CSV)
    save_to_json(products, OUTPUT_JSON)

    logger.info("Done.")