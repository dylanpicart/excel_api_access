import os
import re
import logging
from selenium import webdriver
from dotenv import load_dotenv
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "https://infohub.nyced.org"
EXCEL_FILE_EXTENSIONS = (".xlsb", ".xlsx")
SUB_PAGE_PATTERN = r".*/reports/(students-and-schools/school-quality|academics/graduation-results)(?:/.*)?"

# Load environment variables
load_dotenv()

def configure_driver():
    """Configures and returns a Selenium WebDriver instance."""
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        # Load path from .env
        chromedriver_path = os.getenv('CHROMEDRIVER_PATH')
        if not chromedriver_path:
            raise ValueError("CHROMEDRIVER_PATH is not set in .env")

        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
        logging.info("WebDriver configured successfully.")
        return driver
    except Exception as e:
        logging.error(f"Failed to configure WebDriver: {e}")
        raise

def scrape_sub_pages(parent_url, driver):
    """Extracts sub-pages matching the defined pattern."""
    driver.get(parent_url)
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
    except Exception as e:
        logging.error(f"Timeout while waiting for links on {parent_url}: {e}")

    links = {a.get_attribute("href") for a in driver.find_elements(By.TAG_NAME, "a") if a.get_attribute("href")}
    return [link for link in links if re.search(SUB_PAGE_PATTERN, link)]

def scrape_excel_links(parent_url, sub_pages, driver):
    """
    Scrapes Excel file links from the parent page and sub-pages.

    Args:
        parent_url (str): The main page where Excel links may be directly available.
        sub_pages (list): List of sub-page URLs.
        driver (webdriver.Chrome): Selenium WebDriver instance.

    Returns:
        list: A list of Excel file URLs.
    """
    all_pages = [parent_url] + sub_pages  # Include parent page for direct links
    excel_links = set()

    for page in all_pages:
        logging.info(f"Scraping page: {page}")
        driver.get(page)

        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
        except Exception as e:
            logging.warning(f"Timeout while waiting for links on {page}: {e}")
            continue  # Skip to the next page

        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            href = link.get_attribute("href")
            if href and href.endswith(EXCEL_FILE_EXTENSIONS):
                excel_links.add(href)

    logging.info(f"Scraped {len(excel_links)} Excel links: {excel_links}")
    return list(excel_links)

