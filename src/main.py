import os
import sys
import logging
import asyncio
from logging.handlers import RotatingFileHandler
from .excel_scraper import NYCInfoHubScraper

# Ensure stdout is line-buffered so logs appear in real time
sys.stdout.reconfigure(line_buffering=True)

# -------------------- SCRAPER EXECUTION --------------------
async def main():
    """
    Main entry point for running the NYCInfoHubScraper.
    Delegates the entire scraping workflow to the scraper's scrape_data().
    """
    scraper = NYCInfoHubScraper()
    try:
        # The new refactored pipeline is entirely within scrape_data()
        await scraper.scrape_data()
    except Exception as e:
        logging.error(f"Some error occurred: {e}", exc_info=True)
        return 1  # Non-zero exit code indicates an error
    finally:
        # Clean up Selenium & httpx
        await scraper.close()

    return 0  # Signals success to the caller

# Run scraper process if script is executed directly
if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # Create rotating log handler
    log_file_path = os.path.join(logs_dir, "excel_fetch.log")
    rotating_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=5_242_880,  # ~5 MB
        backupCount=2,
        encoding="utf-8"
    )
    rotating_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    ))

    # Configure logging with both file & console handlers
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[rotating_handler, logging.StreamHandler()],
        force=True
    )

    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logging.error(f"Script failed: {e}", exc_info=True)
        sys.exit(1)
