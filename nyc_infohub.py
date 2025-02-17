import os
import logging
import asyncio
from url_scraper import NYCInfoHubScraper
from logging.handlers import RotatingFileHandler

# -------------------- CONFIGURATION --------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
HASH_DIR = os.path.join(BASE_DIR, "hashes")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE_PATH = os.path.join(LOG_DIR, "excel_fetch.log")

# Ensure necessary directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(HASH_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Set up Rotating Log Handler
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
rotating_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=5 * 1024 * 1024, backupCount=2)
rotating_handler.setFormatter(log_formatter)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[rotating_handler, logging.StreamHandler()]
)


# -------------------- SCRAPER EXECUTION --------------------
async def run_scraper():
    """Run the full scraping process"""
    scraper = NYCInfoHubScraper()

    try:
        # Scraping logic (scrape links, download files, etc.)
        excel_links = await scraper.scrape_excel_links()

        # Fetch Excel files
        content = await scraper.concurrent_fetch(excel_links)  # Awaiting download process

        # Save downloaded files
        for url, file_content in content.items():
            if file_content:
                scraper.save_file(file_content, url)
                
    except Exception as e:
        logging.error(f"❌ Error during scraping process: {e}")

    finally:
        # Ensure proper closing of session and WebDriver
        await scraper.close()  # Await the closing of the session asynchronously


# Run the scraper process
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scraper())
