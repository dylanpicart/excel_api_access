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
from abc import ABC, abstractmethod
from tenacity import retry, stop_after_attempt, wait_fixed
from tqdm import tqdm

load_dotenv()
logging.info(f"CHROMEDRIVER_PATH: {os.environ.get('CHROMEDRIVER_PATH')}")

EXCEL_FILE_EXTENSIONS = ('.xls', '.xlsx', '.xlsb')
CHUNK_SIZE = 65536
YEAR_PATTERN = re.compile(r'20\d{2}', re.IGNORECASE)
SUB_PAGE_PATTERN = re.compile(
    r'.*/reports/(students-and-schools/school-quality|academics/graduation-results|test-results)(?:/.*)?',
    re.IGNORECASE
)
EXCLUDED_PATTERNS = ["quality-review", "nyc-school-survey", "signout", "signin", "login", "logout"]

REPORT_URLS = {
    "graduation": "https://infohub.nyced.org/reports/academics/graduation-results",
    "attendance": (
        "https://infohub.nyced.org/reports/students-and-schools/school-quality/"
        "information-and-data-overview/end-of-year-attendance-and-chronic-absenteeism-data"
    ),
    "demographics": (
        "https://infohub.nyced.org/reports/students-and-schools/school-quality/"
        "information-and-data-overview"
    ),
    "test_results": "https://infohub.nyced.org/reports/academics/test-results",
    "other_reports": (
        "https://infohub.nyced.org/reports/students-and-schools/school-quality/"
        "information-and-data-overview"
    )
}


# -------------------- FileManager --------------------
class FileManager:
    def __init__(self, data_dir, hash_dir):
        self._data_dir = data_dir
        self._hash_dir = hash_dir
        os.makedirs(self._data_dir, exist_ok=True)
        os.makedirs(self._hash_dir, exist_ok=True)

    def categorize_file(self, file_name: str, categories: dict) -> str:
        name_lower = file_name.lower()
        for category, keywords in categories.items():
            if any(k in name_lower for k in keywords):
                return category
        return "other_reports"

    def get_save_path(self, category: str, file_name: str) -> str:
        category_dir = os.path.join(self._data_dir, category)
        os.makedirs(category_dir, exist_ok=True)
        return os.path.join(category_dir, file_name)

    def get_hash_path(self, category: str, file_name: str) -> str:
        category_hash_dir = os.path.join(self._hash_dir, category)
        os.makedirs(category_hash_dir, exist_ok=True)
        return os.path.join(category_hash_dir, f"{file_name}.hash")

    def file_has_changed(self, hash_path: str, new_hash: str) -> bool:
        if not os.path.exists(hash_path):
            return True
        with open(hash_path, "r") as hf:
            old_hash = hf.read().strip()
        return old_hash != new_hash

    def save_file(self, save_path: str, content: bytes):
        with open(save_path, "wb") as f:
            f.write(content)
        logging.info(f"✅ Saved file: {save_path}")

    def save_hash(self, hash_path: str, hash_value: str):
        with open(hash_path, "w") as hf:
            hf.write(hash_value)
        logging.info(f"🆕 Hash updated: {hash_path}")


# -------------------- BaseScraper (Abstract) --------------------
class BaseScraper(ABC):
    def __init__(self):
        self._driver = self.configure_driver()
        self._session = httpx.AsyncClient(
            http2=True,
            limits=httpx.Limits(max_connections=80, max_keepalive_connections=40),
            timeout=5
        )

    @property
    def driver(self):
        """
        Expose the private `_driver` so tests that do
        patching can still access it as test_scraper.driver.
        """
        return self._driver

    @property
    def session(self):
        """
        Same for `_session`: exposing publicly for test patching.
        """
        return self._session

    def configure_driver(self):
        logging.info("Starting WebDriver configuration...")
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins-discovery")

        chrome_path = os.getenv("CHROME_DRIVER_PATH", "")
        if chrome_path:
            logging.info(f"Using custom ChromeDriver path: {chrome_path}")
            driver = webdriver.Chrome(executable_path=chrome_path, options=options)
        else:
            logging.info("Using system ChromeDriver from PATH.")
            driver = webdriver.Chrome(options=options)

        driver.set_page_load_timeout(60)
        logging.info("WebDriver configured successfully.")
        return driver

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def download_excel(self, url: str):
        try:
            async with self._session.stream("GET", url, timeout=10) as resp:
                if resp.status_code == 200:
                    chunks = []
                    async for chunk in resp.aiter_bytes(chunk_size=CHUNK_SIZE):
                        chunks.append(chunk)
                    return url, b"".join(chunks)
                else:
                    logging.error(f"❌ Download failed {resp.status_code}: {url}")
                    return url, None
        except Exception as e:
            logging.error(f"❌ Error streaming {url}: {type(e).__name__} - {e}", exc_info=True)
            return url, None

    async def concurrent_fetch(self, urls):
        tasks = [self.download_excel(u) for u in urls]
        results = {}
        for coro in tqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="📥 Downloading Excel Files"
        ):
            url, content = await coro
            if content:
                results[url] = content
        return results

    @staticmethod
    def compute_file_hash(content: bytes) -> str:
        hasher = hashlib.sha256()
        hasher.update(content)
        return hasher.hexdigest()

    def parallel_hashing(self, files_map: dict) -> dict:
        results = {}
        with concurrent.futures.ProcessPoolExecutor() as executor:
            future_to_url = {
                executor.submit(self.compute_file_hash, content): url
                for url, content in files_map.items()
            }
            for future in tqdm(
                concurrent.futures.as_completed(future_to_url),
                total=len(future_to_url),
                desc="🔑 Computing Hashes"
            ):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                except Exception as e:
                    logging.error(f"❌ Error hashing {url}: {e}")
        return results

    @abstractmethod
    async def scrape_data(self):
        pass

    async def close(self):
        if self._driver:
            self._driver.quit()
            self._driver = None
            logging.info("WebDriver closed.")
        try:
            await self._session.aclose()
        except Exception as e:
            logging.error(f"❌ Error closing session: {e}")
        finally:
            logging.info("✅ Scraping complete")


# -------------------- NYCInfoHubScraper --------------------
class NYCInfoHubScraper(BaseScraper):
    CATEGORIES = {
        "graduation": ["graduation", "cohort"],
        "attendance": ["attendance", "chronic", "absentee"],
        "demographics": ["demographics", "snapshot"],
        "test_results": ["test", "results", "regents", "ela", "english language arts", "math", "mathematics"],
        "other_reports": []
    }

    def __init__(self, base_dir=None, data_dir=None, hash_dir=None, log_dir=None):
        super().__init__()
        script_dir = os.path.abspath(os.path.dirname(__file__)) if "__file__" in globals() else os.getcwd()
        self._base_dir = base_dir or os.path.join(script_dir, "..")
        self._data_dir = data_dir or os.path.join(self._base_dir, "data")
        self._hash_dir = hash_dir or os.path.join(self._base_dir, "hashes")
        self._log_dir = log_dir or os.path.join(self._base_dir, "logs")

        os.makedirs(self._log_dir, exist_ok=True)
        self._file_manager = FileManager(self._data_dir, self._hash_dir)

        logging.info(f"Data directory: {self._data_dir}")
        logging.info(f"Hash directory: {self._hash_dir}")
        logging.info(f"Log directory: {self._log_dir}")

    # Expose a categorize_file() method so your test_categorize_file passes:
    def categorize_file(self, file_name: str) -> str:
        return self._file_manager.categorize_file(file_name, self.CATEGORIES)

    def should_skip_link(self, href: str) -> bool:
        if not href:
            return True
        parsed = urlparse(href)
        if parsed.fragment:
            return True
        lower_href = href.lower()
        return any(pattern in lower_href for pattern in EXCLUDED_PATTERNS)

    async def discover_relevant_subpages(self, url, depth=1, visited=None):
        if visited is None:
            visited = set()
        if url in visited:
            return set()

        visited.add(url)
        discovered_links = set()
        try:
            self._driver.get(url)
            WebDriverWait(self._driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
        except Exception as e:
            logging.error(f"❌ Error loading {url}: {e}")
            return discovered_links

        anchors = self._driver.find_elements(By.TAG_NAME, "a")
        for a in anchors:
            href = a.get_attribute("href")
            if self.should_skip_link(href):
                continue
            if SUB_PAGE_PATTERN.match(href):
                discovered_links.add(href)

        if depth > 1:
            for link in list(discovered_links):
                sub_links = await self.discover_relevant_subpages(link, depth - 1, visited)
                discovered_links.update(sub_links)

        return discovered_links

    async def scrape_page_links(self, url, visited=None):
        if visited is None:
            visited = set()

        valid_links = []
        try:
            self._driver.get(url)
            WebDriverWait(self._driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
        except Exception as e:
            logging.error(f"❌ Error waiting for page load on {url}: {e}")
            return valid_links

        anchors = self._driver.find_elements(By.TAG_NAME, "a")
        for a in anchors:
            href = a.get_attribute("href")
            if not href or href in visited:
                continue

            visited.add(href)

            if not href.lower().endswith(EXCEL_FILE_EXTENSIONS):
                continue

            found_years = YEAR_PATTERN.findall(href)
            if found_years:
                years = [int(y) for y in found_years]
                if not any(y >= 2018 for y in years):
                    continue
            else:
                continue

            valid_links.append(href)

        logging.info(f"🔗 Found {len(valid_links)} valid Excel links on {url}.")
        return valid_links

    async def scrape_excel_links(self):
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

    def save_file(self, url: str, content: bytes, new_hash: str):
        file_name = os.path.basename(url)
        category = self._file_manager.categorize_file(file_name, self.CATEGORIES)

        save_path = self._file_manager.get_save_path(category, file_name)
        hash_path = self._file_manager.get_hash_path(category, file_name)

        if not self._file_manager.file_has_changed(hash_path, new_hash):
            logging.info(f"🔄 No changes detected: {file_name}. Skipping save.")
            return

        self._file_manager.save_file(save_path, content)
        self._file_manager.save_hash(hash_path, new_hash)

    async def scrape_data(self):
        excel_links = await self.scrape_excel_links()
        if not excel_links:
            logging.info("No Excel links found.")
            return

        files_map = await self.concurrent_fetch(excel_links)
        if not files_map:
            logging.info("No files downloaded.")
            return

        hash_results = self.parallel_hashing(files_map)
        for url, content in files_map.items():
            new_hash = hash_results.get(url)
            if new_hash:
                self.save_file(url, content, new_hash)
