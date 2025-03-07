# conftest.py

import pytest
import logging
import asyncio

# Updated import to excel_scraper instead of src.excel_scraper
from src.excel_scraper import NYCInfoHubScraper

@pytest.fixture(scope="session")
def test_scraper():
    """
    A session-scoped fixture that returns a NYCInfoHubScraper instance.
    Any test can use 'test_scraper' as a parameter, and it will share
    the same instance if scope="session".
    """
    logging.info("Setting up NYCInfoHubScraper for tests.")
    scraper = NYCInfoHubScraper()
    yield scraper  # run tests using this instance

    # Teardown code after tests finish
    logging.info("Tearing down NYCInfoHubScraper after tests.")
    try:
        asyncio.run(scraper.close())
    except Exception as e:
        logging.error(f"Error closing scraper during teardown: {e}")
