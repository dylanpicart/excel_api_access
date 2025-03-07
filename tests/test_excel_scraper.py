# test_excel_scraper.py

import pytest
import hashlib
from unittest.mock import patch, MagicMock
from src.excel_scraper import NYCInfoHubScraper


def test_compute_file_hash():
    """
    Test the compute_file_hash static method with known data.
    """
    test_data = b"hello"
    expected_hash = hashlib.sha256(test_data).hexdigest()
    actual_hash = NYCInfoHubScraper.compute_file_hash(test_data)
    assert actual_hash == expected_hash, "Hash does not match expected SHA-256"


def test_categorize_file():
    """
    Test that categorize_file puts files with certain keywords
    into the expected category subfolder.
    """
    scraper = NYCInfoHubScraper()
    assert scraper.categorize_file("my_graduation_report_2024.xlsx") == "graduation"
    assert scraper.categorize_file("snapshot_demographics_2023.xlsb") == "demographics"
    assert scraper.categorize_file("random_file.xls") == "other_reports"


@pytest.mark.asyncio
async def test_discover_relevant_subpages(test_scraper):
    """
    Example integration-ish test to verify discover_relevant_subpages.
    In real usage, you might mock the driver's behavior 
    or use a local test page with known links.
    """
    # If you have a test page with known sub-links that match the SUB_PAGE_PATTERN:
    test_url = "https://example.com/testpage"
    
    # This call will likely return an empty set (since example.com is not guaranteed to have matches).
    # In real usage, you’d use a mock or local test server.
    discovered = await test_scraper.discover_relevant_subpages(test_url, depth=1)
    
    assert isinstance(discovered, set)
    # Optionally check something about the discovered set, if you had a controlled test page:
    # assert "https://example.com/testpage/reports/students-and-schools/school-quality" in discovered


@pytest.mark.asyncio
async def test_scrape_page_links(test_scraper):
    """
    Demonstrates how to mock Selenium calls to test scrape_page_links without an actual webpage.
    """
    # Mock the find_elements call to return a list of anchor-like mocks
    mock_element_1 = MagicMock()
    mock_element_1.get_attribute.return_value = "http://example.com/data_2021.xlsx"
    
    mock_element_2 = MagicMock()
    mock_element_2.get_attribute.return_value = "http://example.com/file.pdf"
    
    with patch.object(test_scraper.driver, 'get') as mock_get, \
         patch.object(test_scraper.driver, 'find_elements', return_value=[mock_element_1, mock_element_2]) as mock_find:
        
        # Because the second link ends with .pdf, it should be filtered out
        # The first link is .xlsx with a year >= 2018
        valid_links = await test_scraper.scrape_page_links("http://example.com")
        
        assert len(valid_links) == 1
        assert valid_links[0] == "http://example.com/data_2021.xlsx"
        mock_get.assert_called_once()
        mock_find.assert_called_once()


@pytest.mark.asyncio
async def test_download_excel_success(test_scraper):
    fake_excel_content = b"FakeExcelData"
    url = "http://example.com/test.xls"

    class MockResponseContext:
        def __init__(self, status_code, content):
            self.status_code = status_code
            self._content = content

        async def aiter_bytes(self, chunk_size=65536):
            yield self._content

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    # This is a *regular* function, not async, returning an async context manager
    def mock_stream(method, url, timeout=10):
        # You could pass 'method', 'url', 'timeout' to the constructor if needed
        return MockResponseContext(200, fake_excel_content)

    # Patch session.stream so that calling it returns our context manager object
    with patch.object(test_scraper.session, 'stream', side_effect=mock_stream):
        returned_url, content = await test_scraper.download_excel(url)
        assert returned_url == url
        assert content == fake_excel_content


@pytest.mark.asyncio
async def test_download_excel_failure(test_scraper):
    def mock_stream_failure(method, url, timeout=10):
        class MockResponse:
            status_code = 404
            async def aiter_bytes(self, chunk_size=65536):
                yield b""
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        return MockResponse()


    with patch.object(test_scraper.session, 'stream', side_effect=mock_stream_failure):
        returned_url, content = await test_scraper.download_excel("http://example.com/broken.xls")
        assert returned_url == "http://example.com/broken.xls"
        # For a 404, your code might return content=None, so verify behavior:
        assert content is None


def test_parallel_hashing():
    """
    Simple test for parallel_hashing. We supply some in-memory byte strings
    to check if the output dict has correct SHA-256 hashes.
    """
    scraper = NYCInfoHubScraper()
    sample_files_map = {
        "file1.xlsx": b"Data1",
        "file2.xlsx": b"Data2",
    }
    results = scraper.parallel_hashing(sample_files_map)
    assert len(results) == 2
    expected_hash_file1 = hashlib.sha256(b"Data1").hexdigest()
    expected_hash_file2 = hashlib.sha256(b"Data2").hexdigest()
    assert results["file1.xlsx"] == expected_hash_file1
    assert results["file2.xlsx"] == expected_hash_file2


def test_save_file(tmp_path):
    """
    Test the save_file method to ensure it writes new content
    and updates hash if different from the old one.
    """
    scraper = NYCInfoHubScraper(
    # Override the data and hash directories for the test
    data_dir=str(tmp_path / "data"),
    hash_dir=str(tmp_path / "hashes")
    )

    # We can do it by monkeypatching or just dynamically passing a path, 
    # but here we just call it as is if the code references DATA_DIR/HASH_DIR as class constants.

    test_url = "http://example.com/graduation_report_2022.xlsx"
    test_content = b"New report content"
    new_hash = hashlib.sha256(test_content).hexdigest()

    # Call method
    scraper.save_file(test_url, test_content, new_hash)

    # Check that file is actually saved
    expected_file_path = tmp_path / "data" / "graduation" / "graduation_report_2022.xlsx"
    assert expected_file_path.is_file(), "Excel file not saved."

    # Check that the hash file is created and contains the correct hash
    expected_hash_path = tmp_path / "hashes" / "graduation" / "graduation_report_2022.xlsx.hash"
    assert expected_hash_path.is_file(), "Hash file not created."
    with open(expected_hash_path, "r") as hf:
        saved_hash = hf.read().strip()
    assert saved_hash == new_hash, "Hash file content does not match expected hash."
