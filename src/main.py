import os
import sys
import logging
import asyncio
from src.excel_scraper import NYCInfoHubScraper
from logging.handlers import RotatingFileHandler

sys.stdout.reconfigure(line_buffering=True) # Real-time logging 

# -------------------- SCRAPER EXECUTION --------------------
async def main():
        scraper = NYCInfoHubScraper()
        try:
            # Gather Excel links
            excel_links = await scraper.scrape_excel_links()
            if not excel_links:
                logging.info("No Excel links found.")
                return

            # Concurrently download them (async)
            files_map = await scraper.concurrent_fetch(excel_links)
            if not files_map:
                logging.info("No files downloaded.")
                return

            # Hash them in parallel (CPU-bound) using ProcessPoolExecutor
            logging.info("🔬 Hashing files in parallel...")
            hash_results = scraper.parallel_hashing(files_map)

            # Save files if changed
            for url, content in files_map.items():
                new_hash = hash_results.get(url, None)
                if new_hash:
                    scraper.save_file(url, content, new_hash)
                    
        except Exception as e:
            logging.error(f"Some error occurred: {e}", exc_info=True)
        finally:
            # Clean up Selenium & httpx
            await scraper.close()  # logs “WebDriver closed.”
        return 0

# Run scraper process
if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # Create rotating log handler
    log_file_path = os.path.join(logs_dir, "excel_fetch.log")
    rotating_handler = RotatingFileHandler(log_file_path, maxBytes=5_242_880, backupCount=2, encoding="utf-8")
    rotating_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # Call basicConfig once, referencing rotating file handler
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[rotating_handler, logging.StreamHandler()],
        force=True
    )    

    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)  # Signals a successful run to caller (cron or other processes)
    except Exception as e:
        logging.error(f"Script failed: {e}", exc_info=True)
        sys.exit(1)  # Signals an error code to caller (cron or other processes)
