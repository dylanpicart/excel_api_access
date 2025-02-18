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
async def main():
        scraper = NYCInfoHubScraper()
        try:
            # 1. Gather Excel links
            excel_links = await scraper.scrape_excel_links()
            if not excel_links:
                logging.info("No Excel links found.")
                return

            # 2. Concurrently download them (async)
            files_map = await scraper.concurrent_fetch(excel_links)
            if not files_map:
                logging.info("No files downloaded.")
                return

            # 3. Hash them in parallel (CPU-bound) using ProcessPoolExecutor
            logging.info("🔬 Hashing files in parallel...")
            hash_results = scraper.parallel_hashing(files_map)

            # 4. Save files if changed
            for url, content in files_map.items():
                new_hash = hash_results.get(url, None)
                if new_hash:
                    scraper.save_file(url, content, new_hash)

        finally:
            # Clean up Selenium & httpx
            await scraper.close()


# Run the scraper process
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
