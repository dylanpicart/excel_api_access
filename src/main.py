import os
import logging
import asyncio
from excel_scraper import NYCInfoHubScraper
from logging.handlers import RotatingFileHandler


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
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # (2) Create the rotating log handler
    log_file_path = os.path.join(logs_dir, "excel_fetch.log")
    rotating_handler = RotatingFileHandler(log_file_path, maxBytes=5_242_880, backupCount=2)
    rotating_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # (3) Call basicConfig once, referencing your rotating handler
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[rotating_handler, logging.StreamHandler()]
    )    
    asyncio.run(main())
