import os
import logging
import hashlib
import asyncio
import httpx
import re
import concurrent.futures
from dotenv import load_dotenv
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tenacity import retry, stop_after_attempt, wait_fixed
from tqdm import tqdm
import pandas as pd

# Load environment variables from .env
load_dotenv()
logging.info(f"CHROMEDRIVER_PATH: {os.environ.get('CHROMEDRIVER_PATH')}")

# Constants
EXCEL_FILE_EXTENSIONS = ('.xls', '.xlsx', '.xlsb')
SUB_PAGE_PATTERN = re.compile(r'.*/reports/(students-and-schools/school-quality|academics/graduation-results|test-results)(?:/.*)?', re.IGNORECASE)
CHUNK_SIZE = 65536  # 64 KB
YEAR_PATTERN = re.compile(r'20\d{2}', re.IGNORECASE)

REPORT_URLS = {
    "graduation": "https://infohub.nyced.org/reports/academics/graduation-results",
    "attendance": "https://infohub.nyced.org/reports/students-and-schools/school-quality/"
                  "information-and-data-overview/end-of-year-attendance-and-chronic-absenteeism-data",
    "demographics": "https://infohub.nyced.org/reports/students-and-schools/school-quality/"
                    "information-and-data-overview",
    "test_results": "https://infohub.nyced.org/reports/academics/test-results",
    "other_reports": "https://infohub.nyced.org/reports/students-and-schools/school-quality/"
                     "information-and-data-overview"
}

EXCLUDED_PATTERNS = ["quality-review", "nyc-school-survey", "signout", "signin", "login", "logout"]


# -------------------- NYCInfoHubScraper Class --------------------
class NYCInfoHubScraper:
    # Define categories for organizing downloaded Excel files
    CATEGORIES = {
        "graduation": ["graduation", "cohort"],
        "attendance": ["attendance", "chronic", "absentee"],
        "demographics": ["demographics", "snapshot"],
        "test_results": ["test", "results", "regents", "ela", "english language arts", "math", "mathematics"],
        "other_reports": [] # Default category  
    }

    def __init__(self, base_dir=None, data_dir=None, hash_dir=None, log_dir=None):
        # Initialize directories
        self.base_dir = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.data_dir = data_dir or os.path.join(self.base_dir, "data")
        self.hash_dir = hash_dir or os.path.join(self.base_dir, "hashes")
        self.log_dir = log_dir or os.path.join(self.base_dir, "logs")

        # Re-create directories if needed
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.hash_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        # Configure Selenium driver
        self.driver = self.configure_driver()

        # Create an async HTTP client with concurrency limits
        self.session = httpx.AsyncClient(
            http2=True, limits=httpx.Limits(max_connections=80, max_keepalive_connections=40),
            timeout=5
        )

    def configure_driver(self):
        """Configure Selenium WebDriver (Chrome)."""
        logging.info("Starting WebDriver configuration...")
        
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins-discovery")
        logging.info("Chrome options set (headless, etc.).")

        # Check if CHROME_DRIVER_PATH is set
        chrome_path = os.getenv("CHROME_DRIVER_PATH", "")
        if chrome_path:
            logging.info(f"Using custom ChromeDriver path: {chrome_path}")
            driver = webdriver.Chrome(executable_path=chrome_path, options=options)
        else:
            logging.info("Using system ChromeDriver from PATH.")
            driver = webdriver.Chrome(options=options)

        # Optionally set a page load timeout so we don't get stuck too long
        driver.set_page_load_timeout(60)
        logging.info("Page load timeout set to 60 seconds.")

        logging.info("WebDriver configured successfully.")
        return driver

    
    def should_skip_link(self, href: str) -> bool:
        """
        Returns True if href should be skipped based on anchor fragments
        or the EXCLUDED_PATTERNS list.
        """
        if not href:
            return True

        parsed = urlparse(href)

        # Skip anchor fragment links
        if parsed.fragment:
            return True

        # Check for excluded substrings (case-insensitive)
        href_lower = href.lower()
        for pattern in EXCLUDED_PATTERNS:
            if pattern in href_lower:
                return True

        # If none of the skip conditions were met, return False => don't skip
        return False

    async def discover_relevant_subpages(self, url, depth=1, visited=None):
        """
        Loads page in Selenium, finds <a> tags that match SUB_PAGE_PATTERN.
        Recursively discover up to 'depth' levels.
        """
        if visited is None:
            visited = set()
        if url in visited:
            return set()
        visited.add(url)

        discovered_links = set()
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "a"))
            )
        except Exception as e:
            logging.error(f"❌ Error loading {url}: {e}")
            return discovered_links

        anchors = self.driver.find_elements(By.TAG_NAME, "a")
        for a in anchors:
            href = a.get_attribute("href")
            # Uses skip check to avoid unnecessary processing and quickly verify which links to skip
            if self.should_skip_link(href):
                logging.debug(f"Skipping link: {href}")
                continue

            # If pass all skip checks and matches subpage pattern, add to discovered set
            if SUB_PAGE_PATTERN.match(href):
                discovered_links.add(href)

        # Recurse if depth > 1
        if depth > 1:
            for link in list(discovered_links):
                sub_links = await self.discover_relevant_subpages(link, depth - 1, visited)
                discovered_links.update(sub_links)

        return discovered_links

    async def scrape_page_links(self, url, visited=None):
        """
        Extract ONLY Excel file links from a single page, using:
        1) visited set to skip duplicates
        2) quick pre-filter (endswith Excel extension)
        3) year check (keep if any year >= 2018 or no year found)
        """
        if visited is None:
            visited = set()  # if not passed, we'll have a page-level visited set

        valid_links = []
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "a"))
            )
        except Exception as e:
            logging.error(f"❌ Error waiting for page load on {url}: {e}")
            return valid_links  # return empty if the page failed

        anchors = self.driver.find_elements(By.TAG_NAME, "a")
        for a in anchors:
            href = a.get_attribute("href")
            # Skip if already visited
            if not href or href in visited:
                continue
            visited.add(href)
            # Pre-filter: If the link doesn't end with .xls, .xlsx, or .xlsb, skip quickly
            if not href.lower().endswith(EXCEL_FILE_EXTENSIONS):
                continue
            # Year-based filter using regex - find all '20xx' occurrences in the link
            found_years = YEAR_PATTERN.findall(href)
            if found_years:
                # parse them as integers
                parsed_years = [int(y) for y in found_years]
                # if none are >= 2018, skip
                if not any(y >= 2018 for y in parsed_years):
                    logging.debug(f"Skipping link; all years < 2018: {href}")
                    continue
            else:
                logging.debug(f"Skipping link; no recognized year: {href}")
                continue

            valid_links.append(href)

        logging.info(f"🔗 Found {len(valid_links)} valid Excel links on {url} after filtering.")
        return valid_links

    async def scrape_excel_links(self):
        """
        Hybrid approach:
         1) Start with known pages in REPORT_URLS
         2) Discover sub-pages matching SUB_PAGE_PATTERN
         3) Collect Excel links from each discovered sub-page
        """
        discovered_pages = set()
        base_urls = set(REPORT_URLS.values())

        for base_url in base_urls:
            subpages = await self.discover_relevant_subpages(base_url, depth=1)
            subpages.add(base_url)
            discovered_pages.update(subpages)

        excel_links = set()
        tasks = [self.scrape_page_links(url) for url in discovered_pages]
        results = await asyncio.gather(*tasks)

        for link_list in results:
            excel_links.update(link_list)

        logging.info(f"📊 Total unique Excel links found: {len(excel_links)}")
        return list(excel_links)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def download_excel(self, url):
        """
        Downloads an Excel file asynchronously using stream mode.
        Streams in chunks to avoid loading very large files entirely in memory.
        Returns (url, content) if successful, or (url, None) otherwise.
        """
        try:
            async with self.session.stream("GET", url, timeout=10) as resp:
                if resp.status_code == 200:
                    # Accumulate chunks in memory (still better than reading all at once)
                    chunks = []
                    async for chunk in resp.aiter_bytes(chunk_size=CHUNK_SIZE):
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    
                    return url, content
                else:
                    logging.error(f"❌ Download failed {resp.status_code}: {url}")
                    return url, None
        except Exception as e:
            logging.error(f"❌ Error streaming {url}: {type(e).__name__} - {e}", exc_info=True)
        return url, None

    async def concurrent_fetch(self, urls):
        """
        Download Excel files concurrently (async + httpx).
        Returns dict {url: content} for successful downloads.
        """
        tasks = [self.download_excel(u) for u in urls]
        results = {}
        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="📥 Downloading Excel Files"):
            url, content = await coro
            if content:
                results[url] = content
        return results

    @staticmethod
    def compute_file_hash(content):
        """Compute SHA-256 hash of file content (CPU-bound)."""
        hasher = hashlib.sha256()
        hasher.update(content)
        return hasher.hexdigest()
    
    def parallel_hashing(self, files_map):
        """
        Use ProcessPoolExecutor to hash all file contents in parallel (one per CPU core).
        Returns a dict: {url: hash_value}.
        """
        results = {}
        with concurrent.futures.ProcessPoolExecutor() as executor:
            future_to_url = {
                executor.submit(self.compute_file_hash, content): url
                for url, content in files_map.items()
            }

            for future in tqdm(concurrent.futures.as_completed(future_to_url),
                               total=len(future_to_url), desc="🔑 Computing Hashes"):
                url = future_to_url[future]
                try:
                    hash_value = future.result()
                    results[url] = hash_value
                except Exception as e:
                    logging.error(f"❌ Error hashing {url}: {e}")
        return results

    def categorize_file(self, file_name):
        """Determine the category for the file name."""
        name_lower = file_name.lower()
        for category, keywords in self.CATEGORIES.items():
            if any(k in name_lower for k in keywords):
                return category
        return "other_reports"

    def save_file(self, url, content, new_hash):
        """
        Save the file to disk only if it differs from the existing hash.
        """
        file_name = os.path.basename(url)
        category = self.categorize_file(file_name)

        save_path = os.path.join(self.data_dir, category, file_name)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        hash_path = os.path.join(self.hash_dir, category, f"{file_name}.hash")
        os.makedirs(os.path.dirname(hash_path), exist_ok=True)

        old_hash = None
        if os.path.exists(hash_path):
            with open(hash_path, "r") as hf:
                old_hash = hf.read().strip()

        if old_hash == new_hash:
            logging.info(f"🔄 No changes detected: {file_name}. Skipping save.")
            return

        with open(save_path, "wb") as f:
            f.write(content)
        logging.info(f"✅ Saved file: {save_path}")

        with open(hash_path, "w") as hf:
            hf.write(new_hash)
        logging.info(f"🆕 Hash updated: {hash_path}")

    async def close(self):
        """Close Selenium and the async httpx session."""
        # Close the WebDriver
        if self.driver:
            self.driver.quit()
            self.driver = None
            logging.info("WebDriver closed.")

        # Close the HTTPX session
        try:
            await self.session.aclose()
        except Exception as e:
            logging.error(f"❌ Error closing session: {e}")
        finally:
            logging.info("✅ Scraping complete")

