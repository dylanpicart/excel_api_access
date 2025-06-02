import os
import logging
import hashlib
import asyncio
import httpx
import re
import concurrent.futures
from dotenv import load_dotenv
from urllib.parse import urlparse
from datetime import datetime
from zoneinfo import ZoneInfo
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from abc import ABC, abstractmethod
from tenacity import retry, stop_after_attempt, wait_fixed
from tqdm import tqdm
import pyclamd
import magic
import platform

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
        
# -------------------- SecurityManager -------------------
class SecurityManager:
    """
    Encapsulates file validation logic, including virus scanning
    (ClamAV via python-clamd) and MIME-type checks (python-magic).
    Skips ClamAV scan on Windows by default.
    """

    def __init__(self, clam_socket="/var/run/clamav/clamd.ctl", skip_windows_scan=True):
        """
        Pass the path to the ClamAV Unix socket file.
        By default, it's often /var/run/clamav/clamd.ctl on Debian/Ubuntu.
        If using Windows, automatically skips ClamAV scan.
        """
        self._clam_socket = clam_socket
        self._skip_windows_scan = skip_windows_scan


    def scan_for_viruses(self, file_bytes: bytes, retry_once=True) -> tuple:
        """
        Returns (status, message)
        - "OK": Clean or skipped
        - "FOUND": Virus detected
        - "ERROR": ClamAV not available or failed
        """
        if self._skip_windows_scan and platform.system().lower() == "windows":
            logging.info("Skipping virus scan on Windows.")
            return "OK", "Skipping AV check on Windows"

        # Internal method to handle the ClamAV scan that allows retries in the event of a connection reset
        def _try_scan():
            cd = pyclamd.ClamdUnixSocket(filename=self._clam_socket)
            return cd.scan_stream(file_bytes)

        try:
            result = _try_scan()

            if not result:
                return "OK", "No malware detected."

            status, virus_name = result.get('stream', ('', ''))
            if status == "FOUND":
                return "FOUND", virus_name
            else:
                return "ERROR", f"Unexpected scan result: {result}"

        except ConnectionResetError as e:
            if retry_once:
                logging.warning("ClamAV connection reset. Retrying once...")
                return self.scan_for_viruses(file_bytes, retry_once=False)
            logging.error(f"❌ Virus scan connection reset (Errno 104): {e}")
            return "ERROR", f"Connection reset: {e}"

        except Exception as e:
            logging.error(f"❌ Virus scan error: {e}")
            return "ERROR", str(e)



    def is_excel_file(self, file_bytes: bytes) -> bool:
        """
        Checks if the file's MIME type is recognized as Excel.
        Possible values:
          - 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          - 'application/vnd.ms-excel'
          - 'application/vnd.ms-excel.sheet.binary.macroEnabled.12'
        """
        try:
            mime_type = magic.from_buffer(file_bytes, mime=True)
            # Partial matching in case of minor variations
            if any(token in mime_type for token in ["ms-excel", "spreadsheetml.sheet"]):
                logging.debug(f"✅ MIME check passed: recognized Excel format ({mime_type}).")
                return True
            else:
                logging.error(f"❌ MIME check failed: {mime_type} not recognized as Excel.")
                return False
        except Exception as e:
            logging.error(f"❌ MIME check error: {e}")
            return False


    def log_quarantine(self, url: str, reason: str, file_size: int = None, mime_type: str = None, log_path="logs/quarantine.log"):
        """
        Log a quarantined file with NYC timestamp, reason, size, and MIME type.
        Format: <timestamp> <tab> <url> <tab> <reason> <tab> <size_bytes> <tab> <mime_type>
        """
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        timestamp = datetime.now(ZoneInfo("America/New_York")).isoformat()
        with open(log_path, "a") as f:
            f.write(f"{timestamp}\t{url}\t{reason}\t{file_size or 'N/A'}\t{mime_type or 'N/A'}\n")




# -------------------- BaseScraper (Abstract) --------------------
class BaseScraper(ABC):
    """
    Abstract base class providing essential web-scraping functionality:
    - Selenium WebDriver config
    - Async httpx session
    - Concurrency, file hashing
    - (Optional) Security checks delegated to SecurityManager
    """

    def __init__(self, security_manager=None):
        """
        Optionally pass in a custom SecurityManager. If not provided,
        we'll create a default instance (which does ClamAV + python-magic checks).
        """
        self._driver = self.configure_driver()
        self._session = httpx.AsyncClient(
            http2=True,
            limits=httpx.Limits(max_connections=80, max_keepalive_connections=40),
            timeout=5
        )
        # Attach a security manager (virus + MIME checks)
        self._security_manager = security_manager or SecurityManager()
        self._mime_only_approvals = 0


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
                if resp.status_code != 200:
                    logging.error(f"❌ Download failed {resp.status_code}: {url}")
                    return url, None

                chunks = []
                async for chunk in resp.aiter_bytes(chunk_size=CHUNK_SIZE):
                    chunks.append(chunk)
                content = b"".join(chunks)
                size_bytes = len(content)

                # 🔒 1. Virus scan
                scan_status, message = self._security_manager.scan_for_viruses(content)
                if scan_status == "FOUND":
                    logging.error(f"❌ Virus/malware found in {url}: {message}")
                    self._security_manager.log_quarantine(url, f"Virus: {message}", size_bytes)
                    return url, None

                elif scan_status == "ERROR":
                    # 🧪 Fallback: MIME only if scan fails
                    mime_pass = self._security_manager.is_excel_file(content)
                    mime_type = "unknown"
                    try:
                        import magic
                        mime_type = magic.from_buffer(content, mime=True)
                    except Exception as e:
                        logging.warning(f"Could not determine MIME type: {e}")

                    if mime_pass:
                         logging.warning(f"⚠️ Scan failed but MIME is valid for {url}. Proceeding with caution.")
                         self._mime_only_approvals += 1  # ✅ Track it
                         self._security_manager.log_quarantine(url, "ScanError, allowed via MIME", size_bytes, mime_type)
                         return url, content
                    else:
                        logging.error(f"❌ MIME also failed for {url}. Skipping.")
                        self._security_manager.log_quarantine(url, "ScanError + Bad MIME", size_bytes, mime_type)
                        return url, None

                # 🔍 2. MIME-type check
                mime_type = "unknown"
                try:
                    import magic
                    mime_type = magic.from_buffer(content, mime=True)
                except Exception as e:
                    logging.warning(f"Could not determine MIME type: {e}")

                if not self._security_manager.is_excel_file(content):
                    logging.error(f"❌ File not recognized as Excel: {url}")
                    self._security_manager.log_quarantine(url, "Unrecognized MIME", size_bytes, mime_type)
                    return url, None

                return url, content

        except Exception as e:
            logging.error(f"❌ Error downloading {url}: {type(e).__name__} - {e}", exc_info=True)
            self._security_manager.log_quarantine(url, f"DownloadError: {e}")
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

    def __init__(self, base_dir=None, data_dir=None, hash_dir=None, log_dir=None, skip_win_scan=True):
        super().__init__(security_manager=SecurityManager("/var/run/clamav/clamd.ctl", skip_windows_scan=skip_win_scan))
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

        # ✅ MIME fallback summary
        if hasattr(self, "_mime_only_approvals") and self._mime_only_approvals > 0:
            logging.warning(
                f"⚠️ {self._mime_only_approvals} files were allowed based only on MIME check (virus scan failed). "
                f"Review logs/quarantine.log for details."
        )

                
                
def run_scraper():
    import asyncio
    from main import main
    asyncio.run(main())
