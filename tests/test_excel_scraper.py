# test_excel_scraper.py

import pytest
import hashlib
from unittest.mock import patch, MagicMock
from src.excel_scraper.scraper import NYCInfoHubScraper, SecurityManager
import platform

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
    test_url = "https://example.com/testpage"
    discovered = await test_scraper.discover_relevant_subpages(test_url, depth=1)
    assert isinstance(discovered, set)
    # Additional assertions if you had a known test page

@pytest.mark.asyncio
async def test_scrape_page_links(test_scraper):
    """
    Demonstrates how to mock Selenium calls to test scrape_page_links without an actual webpage.
    """
    mock_element_1 = MagicMock()
    mock_element_1.get_attribute.return_value = "http://example.com/data_2021.xlsx"
    
    mock_element_2 = MagicMock()
    mock_element_2.get_attribute.return_value = "http://example.com/file.pdf"
    
    with patch.object(test_scraper.driver, 'get') as mock_get, \
         patch.object(test_scraper.driver, 'find_elements', return_value=[mock_element_1, mock_element_2]) as mock_find:
        
        valid_links = await test_scraper.scrape_page_links("http://example.com")
        
        assert len(valid_links) == 1
        assert valid_links[0] == "http://example.com/data_2021.xlsx"
        mock_get.assert_called_once()
        mock_find.assert_called_once()

@pytest.mark.asyncio
async def test_download_excel_success(test_scraper):
    """
    Test the download_excel method in a happy-path scenario,
    including virus scan "OK" and MIME "Excel" results.
    """
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

    def mock_stream(method, _url, timeout=10):
        return MockResponseContext(200, fake_excel_content)

    with patch.object(test_scraper.session, 'stream', side_effect=mock_stream) as mock_stream_call, \
         patch.object(test_scraper._security_manager, 'scan_for_viruses', return_value=("OK","No malware detected.")) as mock_scan, \
         patch.object(test_scraper._security_manager, 'is_excel_file', return_value=True) as mock_mime:

        returned_url, content = await test_scraper.download_excel(url)
        assert returned_url == url
        assert content == fake_excel_content

        mock_stream_call.assert_called_once()
        mock_scan.assert_called_once_with(fake_excel_content)
        mock_mime.assert_called_once_with(fake_excel_content)
        
def test_skip_windows_scan_true():
    manager = SecurityManager(skip_windows_scan=True)

    # Mock platform.system() to return 'Windows'
    with patch.object(platform, 'system', return_value='Windows'):
        status, message = manager.scan_for_viruses(b"FakeExcelData")
        assert status == "OK"
        assert "Skipping AV check on Windows" in message

def test_skip_windows_scan_false():
    manager = SecurityManager(skip_windows_scan=False)

    # Mock platform.system() to return 'Windows'
    # We confirm it *doesn't* short-circuit and tries to do normal scanning
    # Since there's no real ClamAV, you might see an 'ERROR' or something
    # unless you mock the clamd calls as well. For illustration:
    with patch.object(platform, 'system', return_value='Windows'), \
    patch("pyclamd.ClamdUnixSocket", side_effect=Exception("No daemon")):
        
        status, message = manager.scan_for_viruses(b"FakeExcelData")
        assert status == "ERROR"
        assert "No daemon" in message

@pytest.mark.asyncio
async def test_download_excel_virus_found(test_scraper):
    """
    Test the scenario where ClamAV detects a virus.
    The method should skip returning file content (return None).
    """
    fake_excel_content = b"FakeInfectedData"
    url = "http://example.com/infected.xls"

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

    def mock_stream(method, _url, timeout=10):
        return MockResponseContext(200, fake_excel_content)

    with patch.object(test_scraper.session, 'stream', side_effect=mock_stream), \
         patch.object(test_scraper._security_manager, 'scan_for_viruses', return_value=("FOUND","Eicar-Test-Signature")), \
         patch.object(test_scraper._security_manager, 'is_excel_file', return_value=True):

        returned_url, content = await test_scraper.download_excel(url)
        assert returned_url == url
        assert content is None, "Should skip returning content if virus is found."

@pytest.mark.asyncio
async def test_download_excel_scan_error(test_scraper):
    """
    Test the scenario where virus scanning fails (connection reset, etc.).
    If MIME is valid, content should still be returned (fallback behavior).
    """
    fake_excel_content = b"FakeExcelData"
    url = "http://example.com/scan_error.xls"

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

    def mock_stream(method, _url, timeout=10):
        return MockResponseContext(200, fake_excel_content)

    # "ERROR" means scanning failed, but MIME check passes
    with patch.object(test_scraper.session, 'stream', side_effect=mock_stream), \
         patch.object(test_scraper._security_manager, 'scan_for_viruses', return_value=("ERROR", "Connection reset")), \
         patch.object(test_scraper._security_manager, 'is_excel_file', return_value=True):

        returned_url, content = await test_scraper.download_excel(url)
        assert returned_url == url
        assert content == fake_excel_content  # ✅ New expected behavior


@pytest.mark.asyncio
async def test_download_excel_not_excel(test_scraper):
    """
    Test scenario where virus scan is OK, but MIME check fails.
    """
    fake_excel_content = b"FakeButActuallyNotExcel"
    url = "http://example.com/not_excel.xls"

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

    def mock_stream(method, _url, timeout=10):
        return MockResponseContext(200, fake_excel_content)

    with patch.object(test_scraper.session, 'stream', side_effect=mock_stream), \
         patch.object(test_scraper._security_manager, 'scan_for_viruses', return_value=("OK","No malware detected.")), \
         patch.object(test_scraper._security_manager, 'is_excel_file', return_value=False):

        returned_url, content = await test_scraper.download_excel(url)
        assert returned_url == url
        assert content is None, "Should skip returning content if it's not recognized as Excel."

@pytest.mark.asyncio
async def test_download_excel_failure(test_scraper):
    """
    Existing test - for a 404 or other HTTP error scenario.
    """
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
        assert content is None, "Should return None on 404"

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
        data_dir=str(tmp_path / "data"),
        hash_dir=str(tmp_path / "hashes")
    )

    test_url = "http://example.com/graduation_report_2022.xlsx"
    test_content = b"New report content"
    new_hash = hashlib.sha256(test_content).hexdigest()

    scraper.save_file(test_url, test_content, new_hash)

    expected_file_path = tmp_path / "data" / "graduation" / "graduation_report_2022.xlsx"
    assert expected_file_path.is_file(), "Excel file not saved."

    expected_hash_path = tmp_path / "hashes" / "graduation" / "graduation_report_2022.xlsx.hash"
    assert expected_hash_path.is_file(), "Hash file not created."
    with open(expected_hash_path, "r") as hf:
        saved_hash = hf.read().strip()
    assert saved_hash == new_hash, "Hash file content does not match expected hash."
