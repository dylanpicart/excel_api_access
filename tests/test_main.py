# tests/test_main.py

import pytest
import asyncio
import logging
from unittest.mock import patch, MagicMock

# This import path assumes that inside main.py you have:
#    from src.excel_scraper import NYCInfoHubScraper
# And that your directory structure has "src/" as a package.
from src.main import main as main_entrypoint

@pytest.mark.asyncio
async def test_main_scraper_flow():
    """
    Example test that runs the entire 'main' flow from main.py
    in a controlled or mocked environment.
    """
    logging.info("Starting test of main.py's flow...")

    # We'll mock out:
    # 1) scraper.scrape_excel_links
    # 2) scraper.concurrent_fetch
    # 3) scraper.parallel_hashing
    # 4) scraper.save_file
    # so no real network or file I/O happens.
    mock_excel_links = [
        "http://example.com/attendance_2021.xlsx",
        "http://example.com/graduation_2019.xls"
    ]
    mock_files_map = {
        "http://example.com/attendance_2021.xlsx": b"fake attendance bytes",
        "http://example.com/graduation_2019.xls": b"fake graduation bytes"
    }
    mock_hashes = {
        "http://example.com/attendance_2021.xlsx": "hash1",
        "http://example.com/graduation_2019.xls": "hash2"
    }

    # IMPORTANT: Patch the methods on the actual module path where
    # `NYCInfoHubScraper` is defined and imported by main.py—i.e. "src.excel_scraper"
    with patch("src.excel_scraper.NYCInfoHubScraper.scrape_excel_links", return_value=mock_excel_links), \
        patch("src.excel_scraper.NYCInfoHubScraper.concurrent_fetch", return_value=mock_files_map), \
        patch("src.excel_scraper.NYCInfoHubScraper.parallel_hashing", return_value=mock_hashes), \
        patch("src.excel_scraper.NYCInfoHubScraper.save_file") as mock_save:

        exit_code = await main_entrypoint()

        # ✅ Check main ran successfully
        assert exit_code == 0, "Expected main to return 0 on success"

        # ✅ NEW: Confirm the mock was even called
        assert mock_save.called, "save_file was not called at all"

        # ✅ Check expected calls
        mock_save.assert_any_call(
            "http://example.com/attendance_2021.xlsx",
            b"fake attendance bytes",
            "hash1"
        )
        mock_save.assert_any_call(
            "http://example.com/graduation_2019.xls",
            b"fake graduation bytes",
            "hash2"
        )
        assert mock_save.call_count == 2, "Expected two calls to save_file"

