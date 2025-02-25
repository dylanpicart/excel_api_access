# Excel API Web Scraper

## Description

**Excel API Web Scraper** is a Python-based project that automates the process of web scraping, downloading, and storing Excel files from the NYC InfoHub website. The scraper dynamically discovers subpages, detects relevant Excel links (filtered by year), downloads them asynchronously, and ensures that only new or changed files are saved.

This version features:
- **Asynchronous HTTP/2 downloads** via `httpx.AsyncClient`
- **Recursive subpage discovery** with Selenium
- **Parallel CPU-bound hashing** with `ProcessPoolExecutor`
- **Detailed logging** with a rotating file handler
- **Progress tracking** via `tqdm`

---

## Features

- **Web Scraping with Selenium**  
  Automatically loads InfoHub pages (and sub-pages) in a headless Chrome browser to discover Excel file links.  

- **Sub-Page Recursion**  
  Uses a regex-based pattern to find and crawl subpages (e.g., graduation results, attendance data).  

- **HTTP/2 Async Downloads**  
  Downloads Excel files using `httpx` in **streaming mode**, allowing concurrent IO while efficiently handling large files.  

- **Year Filtering**  
  Only keeps Excel files that have at least one year >= 2018 in the link (skips older or irrelevant data).  

- **Parallel Hashing**  
  Uses `ProcessPoolExecutor` to compute SHA-256 hashes in parallel, fully utilizing multi-core CPUs without blocking the async loop.  

- **Prevents Redundant Downloads**  
  Compares new file hashes with stored hashes; downloads only if the file has changed.  

- **Progress & Logging**  
  Progress bars via `tqdm` for both downloads and hashing. Detailed logs to `logs/excel_fetch.log` (rotated at 5MB, up to 2 backups).  

---

## Requirements

### **System Requirements**

- **Python 3.8 or higher**  
- **ChromeDriver** (installed and in your PATH for Selenium)

### **Python Dependencies**

To install required packages:

```bash
pip install -r requirements.txt


Dependencies:
- `httpx[http2]`: For performing asynchronous HTTP requests and HTTP/2 support
- `selenium`: For web scraping
- `pandas`: For processing Excel files
- `tqdm`: To display download progress
- `concurrent.futures`: For multithreading
- `openpyxl`, `pyxlsb`, `xlrd`: For handling different Excel file types
- `pytest`, `pytest-asyncio`, `pytest-cov`: For module testing 
```

---

## Directory Structure

```
project_root/
│
├── __init__.py             # Package initializer
├── .github                 # Workflow CI/CD integration
├── .gitignore              # Ignore logs, venv, data, and cache files
├── .env                    # Environment variables (excluded from version control)
├── README.md               # Project documentation
├── requirements.txt        # Project dependencies
├── setup.py                # Project packaging file
├── pyproject.toml          # Specify build system requirements
├── LICENSE                 # License file
│
├── venv/                   # Virtual environment (ignored by version control)
│   
├── src/
│   ├── main.py             # Main scraper script
│   └── excel_scraper.py    # Web scraping module
│
├── logs/                   # Directory for log files
│
├── tests/                  # Directory for unit, integration, and end-to-end testing   
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
   python main.py
   ```
2. **View logs for download status and debugging:**
   ```bash
   tail -f logs/excel_fetch.log
   ```

---

### What Happens Under the Hood
1. Subpage Discovery
- The scraper uses a regex (SUB_PAGE_PATTERN) to find subpages like graduation-results, school-quality, etc.

2. Filtered Excel Links
- Each subpage is loaded in Selenium; <a> tags ending with .xls/.xlsx/.xlsb are collected, then further filtered if they do not contain a relevant year (≥ 2018).

3. Async Streaming Download
- Downloads use httpx.AsyncClient(http2=True) to fetch files in parallel. A progress bar (tqdm) shows how many files are in flight.

4. Parallel Hashing
- Each downloaded file’s hash is computed using a ProcessPoolExecutor so multiple CPU cores can do the work simultaneously.

5. Save if Changed
- If the file’s new hash differs from the previously stored one, the file is saved and the .hash file updated.

6. Logs
- The rotating log captures successes, skips, errors, etc.

---

## **Logging & Monitoring**
- Includes:
   - Log file: logs/excel_fetch.log
   - Rotating File Handler: Rolls over at 5 MB, retains 2 backups.
   - Console Output: Also mirrors log messages for convenience.
   - Progress Bars: tqdm for both downloading and hashing steps.
   
---

## Testing

We use **Pytest** for our test suite, located in the `tests/` folder.

1. **Install dev/test dependencies** (either in your `setup.py` or via `pip install -r requirements.txt` if you listed them there).

2. **Run tests**:
```bash
python -m pytest tests/
```

3. **View Coverage** (if you have `pytest-cov`):
```bash
python -m pytest tests/ --cov=src
```

---

## CI/CD Pipeline

A GitHub Actions workflow is set up in `.github/workflows/ci-cd.yml`. It:

1. **Builds and tests** the project on push or pull request to the `main` branch.
2. If tests pass and you push a **tagged release**, it **builds a distribution** and can **upload** to PyPI using **Twine**.
3. Check the **Actions** tab on your repo to see logs and statuses of each workflow run.

---

## **Previous Limitations and Solutions**
***Bottlenecks***:

- Connection Pooling: In earlier versions, there were issues with connection pooling causing redundant connection opening/closing. This has been fixed with persistent sessions using httpx.AsyncClient.
- Async Event Loop Issues: Earlier issues with closing async sessions were fixed by proper handling of event loops using asyncio.get_event_loop() and asyncio.run().
- Redundant Downloads: Prevented redundant downloads by utilizing SHA-256 hashes for file comparison, ensuring that unchanged files are not downloaded.

***Solutions***:

1. Optimized Downloading: Parallel downloads using asyncio and ThreadPoolExecutor allow multiple downloads to happen concurrently, improving speed.
2. Persistent HTTP Sessions: Using httpx.AsyncClient ensures that HTTP connections are reused, reducing overhead.
3. Efficient Hashing: Files are saved only if they have changed, determined by a computed hash. This ensures no unnecessary downloads.
4. Excluded older datasets by added `re` filtering logic to scrape only the latest available data.

---

## **Current Limitations**
- HTTP/2 Support: Requires `httpx[http2]` installed; if the server doesn’t support HTTP/2, it falls back to HTTP/1.1.
- Depth Control: Currently only recurses subpages one level deep. If more thorough or deeper crawling is needed, logic can be extended.
- Year Parsing: If year formats differ (e.g., “19-20” instead of “2019-2020”), the regex must be adjusted.
- Retries: The current code logs but doesn’t implement an automatic retry strategy. That can be added if downloads frequently fail.

---

## **Other Potential Improvements**
- **Add NYSed Website**: Scrape data from NYSed.
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
