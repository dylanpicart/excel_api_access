import os
import hashlib
import requests
import pandas as pd
import logging
from logging.handlers import RotatingFileHandler
import time
from tqdm import tqdm
from requests.exceptions import HTTPError, ConnectionError
from concurrent.futures import ThreadPoolExecutor, as_completed
from url_scraper import scrape_sub_pages, scrape_excel_links, configure_driver

# Define the base directory for the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_URLS_FILE = os.path.join(BASE_DIR, "data", "last_checked_urls.txt")
DATA_FOLDER = os.path.join(BASE_DIR, "data")
HASH_FOLDER = os.path.join(BASE_DIR, "hashes")
BASE_URL = "https://infohub.nyced.org"
LOG_FILE_PATH = os.path.join(BASE_DIR, "logs", "excel_fetch.log")

# Set up a rotating log handler
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

rotating_handler = RotatingFileHandler(
    LOG_FILE_PATH, maxBytes=5 * 1024 * 1024, backupCount=2 # 5 MB log files, keep 2 backups
)
rotating_handler.setFormatter(log_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[rotating_handler]
)

# Ensure necessary directories exist
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(HASH_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)


# Define categories for organizing downloaded Excel files
CATEGORIES = {
    "graduation": ["graduation", "cohort"],
    "attendance": ["attendance", "chronic", "absentee"],
    "demographics": ["demographics", "snapshot"],
    "other_reports": []  # Default category for uncategorized files
}

def categorize_file(file_name):
    """
    Determines the category of an Excel file based on predefined keywords.
    This helps in organizing files into appropriate subdirectories.
    """
    file_name_lower = file_name.lower()
    for category, keywords in CATEGORIES.items():
        if any(keyword in file_name_lower for keyword in keywords):
            return category
    return "other_reports"

def compute_file_hash(content):
    """
    Computes the SHA-256 hash of the file content for change detection.
    This ensures we only download new or modified files.
    """
    return hashlib.sha256(content).hexdigest()

def fetch_excel_file(url, max_retries=3):
    """
    Downloads the Excel file content from a given URL with retry logic.
    Handles connection errors and logs failures.

    Args:
        url (str): The URL of the Excel file.
        max_retries (int): Number of retry attempts before failing.

    Returns:
        bytes: The content of the Excel file if successful, otherwise None.
    """
    for attempt in range(max_retries):
        try:
            logging.info(f"Fetching file from {url} (Attempt {attempt + 1}/{max_retries})...")
            response = requests.get(url, timeout=10)  # Timeout prevents hanging
            response.raise_for_status()
            return response.content
        except (HTTPError, ConnectionError) as err:
            logging.error(f"Error fetching {url}: {err}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retrying
            else:
                logging.error(f"Max retries reached for {url}. Skipping...")
                return None

def save_file(content, file_path):
    """
    Saves the downloaded file content to a specified path.
    Creates the necessary directories if they do not exist.
    Logs when a file is successfully saved.
    """
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'wb') as f:
        f.write(content)
    logging.info(f"File saved: {file_path}")

def fetch_and_store_excel(url, file_path):
    """
    Downloads and saves an Excel file only if its content has changed.
    Uses hashing to check for modifications and prevents redundant downloads.
    Logs all key steps in the process, including detecting unchanged files.
    """
    content = fetch_excel_file(url)
    if not content:
        return None  # Skip processing if download fails

    current_hash = compute_file_hash(content)
    file_name = os.path.basename(file_path)
    category = categorize_file(file_name)
    categorized_path = os.path.join(DATA_FOLDER, category, file_name)
    os.makedirs(os.path.dirname(categorized_path), exist_ok=True)

    # Load previous hash to check if the file has changed
    hash_file = os.path.join(HASH_FOLDER, category, f"{file_name}.hash")
    previous_hash = ""
    if os.path.exists(hash_file):
        with open(hash_file, 'r') as f:
            previous_hash = f.read().strip()

    if current_hash == previous_hash:
        logging.info(f"No changes detected: {categorized_path}. Skipping save.")
        return None

    # Save new file and update hash
    save_file(content, categorized_path)
    os.makedirs(os.path.dirname(hash_file), exist_ok=True)  # Ensure hash directory exists
    with open(hash_file, 'w') as f:
        f.write(current_hash)
    logging.info(f"File hash updated: {hash_file}")

    # Determine the correct Excel engine
    file_extension = file_name.split(".")[-1].lower()
    engine = None
    if file_extension == "xlsb":
        engine = "pyxlsb"
    elif file_extension == "xls":
        engine = "xlrd"
    else:
        engine = "openpyxl"  # Default for .xlsx files

    try:
        dataframe = pd.read_excel(categorized_path, engine=engine)
        logging.info(f"Successfully loaded {file_name} using engine: {engine}")
        return dataframe
    except Exception as e:
        logging.error(f"Error loading {file_name}: {e}")
        return None


def run_scraper():
    """
    Executes the web scraper to extract and download Excel files.
    Uses ThreadPoolExecutor to download files concurrently.
    """
    logging.info("Starting scraper...")
    driver = configure_driver()
    try:
        parent_url = "https://infohub.nyced.org/reports/students-and-schools/school-quality/information-and-data-overview"
        sub_pages = scrape_sub_pages(parent_url, driver)
        excel_links = scrape_excel_links(parent_url, sub_pages, driver)

        with open(LAST_URLS_FILE, "w") as f:
            f.write("\n".join(excel_links))
        logging.info(f"Total Excel files found: {len(excel_links)}")

        # Set max workers for concurrent downloading
        max_workers = min(5, len(excel_links))  # Use up to 5 threads, or fewer if needed

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all download tasks to executor
            future_to_url = {executor.submit(process_excel_download, url): url for url in excel_links}

            # Use tqdm to monitor progress
            for future in tqdm(as_completed(future_to_url), total=len(excel_links), desc="Downloading Excel Files"):
                url = future_to_url[future]
                try:
                    future.result()  # Retrieve results (handle exceptions)
                except Exception as e:
                    logging.error(f"Error processing {url}: {e}")

    finally:
        driver.quit()
        logging.info("Scraper execution completed.")

def process_excel_download(url):
    """Helper function to categorize and download a file in parallel."""
    file_name = os.path.basename(url)
    category = categorize_file(file_name)
    categorized_path = os.path.join(DATA_FOLDER, category, file_name)
    fetch_and_store_excel(url, categorized_path)

def main():
    """
    Initiates the manual execution of the scraper.
    Calls `run_scraper()` to fetch and store Excel files.
    Logs execution details for debugging.
    """
    logging.info("Starting manual scraper execution...")
    try:
        run_scraper()
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    logging.info("Manual execution finished.")

if __name__ == "__main__":
    main()
