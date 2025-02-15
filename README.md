# NYC InfoHub Excel Data Scraper

## Description

**NYC InfoHub Excel Data Scraper** is a Python-based script that automates the process of web scraping, downloading, and storing Excel files from the NYC InfoHub website. The script dynamically detects new datasets, extracts Excel links, and ensures that only the most recent files are downloaded.

This version includes **multithreading with `ThreadPoolExecutor`**, **progress tracking via `tqdm`**, and **robust error handling with retry logic** for failed downloads.

---

## Features

- **Web Scraping with Selenium**: Automatically detects and extracts dataset links.
- **Scrapes Both Parent & Sub-Pages**: Ensures all necessary files, including demographics, attendance, and graduation rates, are detected.
- **Multithreading for Faster Downloads**: Uses `ThreadPoolExecutor` to process multiple downloads concurrently.
- **Prevents Redundant Downloads**: Uses SHA-256 hashing to check if files have changed before downloading.
- **Organized File Storage**: Saves files into categorized subdirectories inside `data/`.
- **Logging & Monitoring**: Tracks all activities in a log file (`logs/excel_fetch.log`).
- **Retry Logic for Robust Downloads**: Automatically retries failed downloads up to 3 times.
- **Progress Tracking**: Uses `tqdm` to visually represent download progress.

---

## Requirements

### **System Requirements**
- **Python 3.8 or higher**
- **ChromeDriver** (Ensure it's installed and in `PATH` for Selenium)

### **Python Dependencies**
Install required packages using:
```bash
pip install -r requirements.txt
```

Dependencies:
- `selenium`: For web scraping
- `pandas`: For processing Excel files
- `requests`: For downloading files
- `tqdm`: To display download progress
- `concurrent.futures`: For multithreading
- `openpyxl`, `pyxlsb`, `xlrd`: For handling different Excel file types

---

## Directory Structure

```
project_root/
│
├── __init__.py             # Package initializer
├── .gitignore              # Ignore logs, venv, data, and cache files
├── .env                    # Environment variables (excluded from version control)
├── README.md               # Project documentation
├── requirements.txt        # Project dependencies
├── setup.py                # Project packaging file
├── LICENSE                 # License file
│
├── venv/                   # Virtual environment (ignored by version control)
│
├── nyc_infohub.py          # Main scraper script
├── url_scraper.py          # Web scraping module
│
├── logs/                   # Directory for log files
│   └── excel_fetch.log
│
├── data/                   # Directory for downloaded Excel files
│   ├── graduation/
│   ├── attendance/
│   ├── demographics/
│   └── other_reports/
│
└── hashes/                 # Directory for storing file hashes
```

This structure ensures that the project is well-organized for both manual execution and packaging as a Python module.

---

## **Usage**

### **Running the Scraper Manually**
1. **Run the script to scrape and fetch new datasets:**
   ```bash
   python nyc_infohub.py
   ```
2. **View logs for download status and debugging:**
   ```bash
   tail -f logs/excel_fetch.log
   ```

---

## **Logging & Monitoring**
All activities (scraping, downloads, errors) are logged in:
- `logs/excel_fetch.log`
- Includes:
  - **Successful downloads**
  - **Skipped downloads** (if no changes detected)
  - **Errors (network issues, file write errors, etc.)**

---

## **Potential Improvements**
- **Exclude older datasets**: Add filtering logic to scrape only the latest available data.
- **Email Notifications**: Notify users when a new dataset is fetched.
- **Database Integration**: Store metadata in a database for better tracking.
- **Better Exception Handling**: Improve error logging for specific failures.

---

## **License**
This project is licensed under the MIT License. See the LICENSE file for details.

---

## **Author**
Developed by **Dylan Picart at Partnership With Children**.

For questions or contributions, contact: [dpicart@partnershipwithchildren.org](mailto:dpicart@partnershipwithchildren.org).
