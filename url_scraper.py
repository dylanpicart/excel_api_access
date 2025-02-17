import os
import logging
import hashlib
import asyncio
import httpx
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tqdm import tqdm
import pandas as pd

# Constants
EXCEL_FILE_EXTENSIONS = ('.xls', '.xlsx', '.xlsb')
REPORT_URLS = {
    "graduation": "https://infohub.nyced.org/reports/academics/graduation-results",
    "attendance": "https://infohub.nyced.org/reports/students-and-schools/school-quality/information-and-data-overview/end-of-year-attendance-and-chronic-absenteeism-data",
    "demographics": "https://infohub.nyced.org/reports/students-and-schools/school-quality/information-and-data-overview",
    "other_reports": "https://infohub.nyced.org/reports/students-and-schools/school-quality/information-and-data-overview"
}

# Define the base directory for the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
HASH_DIR = os.path.join(BASE_DIR, "hashes")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Ensure necessary directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(HASH_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


class NYCInfoHubScraper:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    HASH_DIR = os.path.join(BASE_DIR, "hashes")
    LOG_DIR = os.path.join(BASE_DIR, "logs")

    # Define categories for organizing downloaded Excel files
    CATEGORIES = {
        "graduation": ["graduation", "cohort"],
        "attendance": ["attendance", "chronic", "absentee"],
        "demographics": ["demographics", "snapshot"],
        "other_reports": []  # Default category for uncategorized files
    }

    def __init__(self):
        """Initialize scraper with Selenium WebDriver and async HTTP client."""
        os.makedirs(self.DATA_DIR, exist_ok=True)
        os.makedirs(self.HASH_DIR, exist_ok=True)
        os.makedirs(self.LOG_DIR, exist_ok=True)
        self.driver = self.configure_driver()
        self.session = httpx.AsyncClient(limits=httpx.Limits(max_connections=100, max_keepalive_connections=50), timeout=15)

    def configure_driver(self):
        """Configures the Selenium WebDriver."""
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        driver = webdriver.Chrome(options=options)
        logging.info("WebDriver configured successfully.")
        return driver

    async def scrape_page_links(self, url):
        """Asynchronously extracts ONLY Excel file links from a given page."""
        self.driver.get(url)
        
        # Wait for page to load (wait for a link to appear, you can replace this with another element if needed)
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "a"))
            )
        except Exception as e:
            logging.error(f"❌ Error waiting for page load on {url}: {e}")
            return []

        links = {
            a.get_attribute("href") for a in self.driver.find_elements(By.TAG_NAME, "a")
            if a.get_attribute("href") and a.get_attribute("href").endswith(EXCEL_FILE_EXTENSIONS)
        }
        
        # Debugging: log all links found (or at least the first few)
        logging.info(f"🔗 Found {len(links)} links on {url}: {list(links)[:5]}")  # Log first 5 links for debugging

        return list(links)

    async def scrape_excel_links(self):
        """Scrape for Excel links within predefined report pages asynchronously."""
        excel_links = set()
        report_urls = set(REPORT_URLS.values())  # Extract URLs from dictionary

        tasks = [self.scrape_page_links(url) for url in report_urls]
        results = await asyncio.gather(*tasks)

        for links in results:
            excel_links.update({link for link in links if link and link.endswith(EXCEL_FILE_EXTENSIONS)})

        logging.info(f"📊 Scraped {len(excel_links)} total Excel links.")
        return list(excel_links)

    async def download_excel(self, client, url):
        """Downloads an Excel file asynchronously."""
        try:
            response = await client.get(url, timeout=10)
            if response.status_code == 200:
                return url, response.content
        except Exception as e:
            logging.error(f"❌ Failed to download {url}: {e}")
        return url, None

    async def concurrent_fetch(self, urls):
        """Downloads multiple Excel files concurrently."""
        tasks = [self.download_excel(self.session, url) for url in urls]
        # Use tqdm to track download progress
        results = []
        for result in tqdm(await asyncio.gather(*tasks), total=len(urls), desc="📥 Downloading Excel Files"):
            results.append(result)
        return {url: content for url, content in results if content}

    def categorize_file(self, file_name):
        """
        Determines the category of an Excel file based on predefined keywords.
        This helps in organizing files into appropriate subdirectories.
        """
        file_name_lower = file_name.lower()
        for category, keywords in self.CATEGORIES.items():
            if any(keyword in file_name_lower for keyword in keywords):
                return category
        return "other_reports"

    def compute_file_hash(self, content):
        """Compute SHA-256 hash of the given file content."""
        hasher = hashlib.sha256()
        hasher.update(content)
        return hasher.hexdigest()

    def save_file(self, content, url):
        """Save the Excel file only if it has changed."""
        file_name = os.path.basename(url)
        category = self.categorize_file(file_name)

        save_path = os.path.join(self.DATA_DIR, category, file_name)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        hash_path = os.path.join(self.HASH_DIR, category, f"{file_name}.hash")
        os.makedirs(os.path.dirname(hash_path), exist_ok=True)

        new_hash = self.compute_file_hash(content)

        old_hash = None
        if os.path.exists(hash_path):
            with open(hash_path, "r") as f:
                old_hash = f.read().strip()

        if old_hash == new_hash:
            logging.info(f"🔄 No changes detected: {file_name}. Skipping save.")
            return

        with open(save_path, "wb") as f:
            f.write(content)
        logging.info(f"✅ Saved file: {save_path}")

        with open(hash_path, "w") as f:
            f.write(new_hash)
        logging.info(f"🆕 Hash updated: {hash_path}")

    async def close(self):
        """Closes session & WebDriver."""
        self.driver.quit()

        try:
            # Ensure the session is closed asynchronously
            await self.session.aclose()  # Await the async session closure

        except Exception as e:
            logging.error(f"❌ Error closing async session: {e}")
            
    def _on_session_close(self, task):
        """Callback for when async session has been closed."""
        if task.exception():
            logging.error(f"❌ Error during session closure: {task.exception()}")
        else:
            logging.info("✅ Async session closed successfully.")
