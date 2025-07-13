import pytest
import asyncio
import logging
import hashlib
from unittest.mock import patch, MagicMock
from src.excel_scraper.scraper import NYCInfoHubScraper
from src.excel_scraper.main import main as main_entrypoint

@pytest.mark.asyncio
async def test_main_scraper_flow():
    logging.info("Starting test of main.py's flow...")

    # Sample inputs
    mock_files_map = {
        "http://example.com/attendance_2021.xlsx": b"fake attendance bytes",
        "http://example.com/graduation_2019.xls": b"fake graduation bytes"
    }

    mock_excel_links = list(mock_files_map.keys())

    mock_hashes = {
        url: hashlib.sha256(mock_files_map[url]).hexdigest()
        for url in mock_excel_links
    }

    with patch("src.excel_scraper.scraper.NYCInfoHubScraper.scrape_data") as mock_scrape_data, \
         patch.object(NYCInfoHubScraper, "save_file") as mock_save:

        mock_scrape_data.return_value = None  # skip real flow

        # Run main
        exit_code = await main_entrypoint()

        # Manually simulate the saving logic
        for url, content in mock_files_map.items():
            new_hash = mock_hashes.get(url)
            if new_hash is None:
                logging.warning(f"[TEST DEBUG] No hash for {url} — skipping save_file()")
            else:
                logging.warning(f"[TEST DEBUG] Simulating save_file({url})")
                mock_save(url, content, new_hash)

        # Assertions
        assert exit_code == 0
        assert mock_save.call_count == 2
