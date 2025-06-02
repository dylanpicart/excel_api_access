# Excel API Web Scraper

## Description

**Excel API Web Scraper** is a Python-based project/package that automates the process of web scraping, downloading, and storing Excel files from NYC InfoHub. It features a modular, object-oriented design with built-in **security checks** (virus scanning and MIME-type validation) for downloaded Excel files, **with an option to skip antivirus scans on Windows** if ClamAV isn’t readily available.

### Highlights

- **Asynchronous HTTP/2 downloads** via `httpx.AsyncClient`  
- **Recursive subpage discovery** with Selenium  
- **Parallel CPU-bound hashing** with `ProcessPoolExecutor`  
- **Detailed logging** with a rotating file handler  
- **Progress tracking** via `tqdm`  
- **SecurityManager** for optional virus scanning (ClamAV) and file-type checks  
- **Skips ClamAV scanning on Windows** by default, avoiding setup complexities while still functioning seamlessly

---

## Features

1. **Web Scraping with Selenium**  
   - Automates loading InfoHub pages (and sub-pages) in a headless Chrome browser to discover Excel file links.

2. **Retries for Slow Connections**  
   - Uses `tenacity` to retry downloads when timeouts or transient errors occur.

3. **Sub-Page Recursion**  
   - Follows a regex-based pattern to find and crawl subpages (e.g., graduation results, attendance data).

4. **HTTP/2 Async Downloads**  
   - Downloads Excel files using `httpx` in **streaming mode**, allowing concurrent I/O while efficiently handling large files.

5. **Year Filtering**  
   - Only keeps Excel files that have at least one year >= 2018 in the link (skips older or irrelevant data).

6. **Parallel Hashing**  
   - Uses `ProcessPoolExecutor` to compute SHA-256 hashes in parallel, fully utilizing multi-core CPUs without blocking the async loop.

7. **Security Checks**  
   - In-memory **virus scanning** with ClamAV (via `pyclamd` or `clamd`)  
   - **MIME-type validation** with `python-magic`, ensuring files are truly Excel  
   - **Skip scanning on Windows** by default (see below)

8. **Prevents Redundant Downloads**  
   - Compares new file hashes with stored hashes; downloads only if the file has changed.

9. **Progress & Logging**  
   - `tqdm` for progress bars during downloads and hashing.  
   - Detailed logs in `logs/excel_fetch.log` (rotated at 5MB, up to 2 backups).

---

## Windows Antivirus Skipping

By default, **ClamAV scanning** is not performed on **Windows** to avoid environment complexities—ClamAV is primarily a Linux/UNIX daemon. The `SecurityManager` class checks `platform.system()`, and if it’s `Windows`, it **short-circuits** scanning and returns a **clean** status. This behavior can be **overridden** by setting:

```python
security_manager = SecurityManager(skip_windows_scan=False)
```

…in which case the code will attempt a normal ClamAV call. To make this work on Windows, you’d typically need:

- **WSL or Docker** to run the ClamAV daemon, or
- Another setup that exposes a ClamAV socket/port for Python to connect to.

---

## Package

[![PyPI version](https://badge.fury.io/py/nyc_infohub_excel_api_access.svg)](https://pypi.org/project/nyc_infohub_excel_api_access/)

**Version: 1.0.8**

A Python package for scraping and downloading Excel datasets from NYC InfoHub using Selenium, httpx, asyncio, and virus/MIME validation is available.

---

## 📦 Installation

```bash
pip install nyc_infohub_excel_api_access
```

---

## 🚀 Usage

Run from the command line:
```bash
nyc-infohub-scraper
```

Installing this package gives you access to the CLI tool nyc-infohub-scraper, which launches the scraper pipeline from the terminal with a single command.

---

## Requirements

### System Requirements

- **Python 3.8 or higher**  
- **ChromeDriver** (installed and in your PATH for Selenium)  
- **ClamAV daemon** (optional but recommended for virus scanning):
  - On Linux/WSL, install via `sudo apt-get install clamav clamav-daemon`.
  - On Windows, you may run ClamAV in WSL or a Docker container, or skip virus scanning.

### Python Dependencies

Install required packages:

```bash
pip install -r requirements.txt
```

**Dependencies**:

- `httpx[http2]`: For performing asynchronous HTTP requests and HTTP/2 support
- `tenacity`: For retying
- `selenium`: For web scraping
- `pandas`: For processing Excel files (optional)
- `tqdm`: To display download progress
- `concurrent.futures`: For multithreading
- `openpyxl`, `pyxlsb`, `xlrd`: For handling different Excel file types
- `pytest`, `pytest-asyncio`, `pytest-cov`: For module testing
- `clamd` or `pyclamd`: For ClamAV virus scanning (if enabled)
- `python-magic`: For MIME-type checks

---

## Scheduling the Scraper

This project supports **two** primary scheduling methods:

1. **WSL / Linux Cron Jobs**  
2. **Windows Task Scheduler**

Depending on where you prefer to run the scraper, you can pick one or both. Each method automates running the script on a specified interval (e.g., daily, weekly, monthly).

---

### 1. WSL (or Linux) Cron Jobs

- **Why Use Cron**: If you’re working in a Linux-like environment (including WSL), cron allows you to schedule commands at fixed times, dates, or intervals without any additional GUIs.

- **Setup**:
  1. **Create a WSL-based virtual environment** (e.g., `venv_wsl`) and install project dependencies (including `selenium`, `httpx`, etc.).
  2. **Edit** your cron table:

     ```bash
     crontab -e
     ```

  3. **Add** a line for your desired schedule, for example, to run every Sunday at 2:30 AM:

     ```bash
     30 2 * * 0 /path/to/project/venv_wsl/bin/python /path/to/project/src/main.py >> /path/to/logs/cron_crawl.log 2>&1
     ```

  4. **Confirm** that WSL remains active or open; if WSL is shut down, cron will not run.

- **Advantages**:
  - Well-known, lightweight system utility.  
  - Great if you’re primarily in Linux/WSL and comfortable with Bash.

- **Caveats**:
  - WSL suspends when no console is running—so if you close WSL entirely, cron won’t run.  
  - If you need a 24/7 environment, consider a real Linux server or keep WSL open.

---

### 2. Windows Task Scheduler

- **Why Use Task Scheduler**: On a Windows system, Task Scheduler is the built-in service for scheduling tasks when the machine is on, without needing WSL open.

- **Setup**:
  1. **Create a Windows-based virtual environment** (e.g., `venv_win`) in your project folder:

     ```powershell
     cd C:\path\to\project
     python -m venv venv_win
     .\venv_win\Scripts\activate
     pip install -r requirements.txt
     ```

  2. **Open** Task Scheduler (`taskschd.msc` from Run or Start).
  3. **Create** a Basic Task:
     - Name: e.g. “NYC InfoHub Scraper (Weekly).”
     - Trigger: Weekly (pick day/time).
     - Action: “Start a program.”
       - **Program/Script**: `C:\path\to\project\venv_win\Scripts\python.exe`
       - **Arguments**: `C:\path\to\project\src\main.py`
     - Finish & test by right-clicking the task → “Run.”

- **Advantages**:
  - Runs natively in Windows, even if WSL is closed.
  - Easy to configure via a GUI.

- **Caveats**:
  - If your environment or script references Linux paths, adapt them to Windows.
  - For storing logs, you can rely on Python’s rotating file handler or redirect output to a custom file (e.g., `task_crawl.log`).

---

## Directory Structure

```text

project_root/
│
├── .github                 # Workflow CI/CD integration
├── .gitignore              # Ignore logs, venv, data, and cache files
├── .env                    # Environment variables (excluded from version control)
├── README.md               # Project documentation
├── requirements.txt        # Project dependencies
├── setup.py                # Project packaging file
├── pyproject.toml          # Specify build system requirements
├── LICENSE                 # License file
│
├── venv_wsl/               # WSL Virtual Environment (ignored by version control)
├── venv_win/               # Windows Virtual Environment (ignored by version control)
│
├── src/
│   ├── __init__.py         # Package initializer
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
│   ├── test_results/
│   └── other_reports/
│
└── hashes/                 # Directory for storing file hashes

```

The structure is well-organized for both manual execution and packaging as a Python module.

---

## **Usage**

### **Running the Scraper Manually**

1. **Run the script to scrape and fetch new datasets:**

   ```bash
   python -m src.main
   ```

This treats src as a package and executes main.py accordingly (avoiding relative import errors).

2. **View logs for download status and debugging:**

   ```bash
   tail -f logs/excel_fetch.log
   ```

---

### What Happens Under the Hood

1. Subpage Discovery

- The scraper uses a regex (SUB_PAGE_PATTERN) to find subpages like graduation-results, school-quality, etc.

2. Filtered Excel Links

- Each subpage is loaded in Selenium; `<a>` tags ending with .xls/.xlsx/.xlsb are collected, then further filtered if they do not contain a relevant year (≥ 2018).

3. Async Streaming Download

- Downloads use httpx.AsyncClient(http2=True) to fetch files in parallel. A progress bar (tqdm) shows how many files are in flight.

4. Security Checks

- In-memory virus scanning (ClamAV) via SecurityManager.scan_for_viruses.
- MIME-type validation (ensure .xls/.xlsx is truly an Excel file).

5. Parallel Hashing

- Each downloaded file’s hash is computed using a ProcessPoolExecutor so multiple CPU cores can do the work simultaneously.

6. Save if Changed

- If the file’s new hash differs from the previously stored one, the file is saved and the .hash file updated.

7. Logs

- The rotating log captures successes, skips, errors, etc.

---

## **Virus Scanning (Optional)**

- By default, if ClamAV is installed and `SecurityManager` is configured, files are scanned in memory before saving.
- If you run on Windows without ClamAV, you can disable scanning by returning `"OK"` or `True` in `scan_for_viruses` or using a stub.
- Make sure `StreamMaxLength` and other ClamAV config values (in `/etc/clamav/clamd.conf`) are large enough to handle your file sizes.

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

- **Connection Pooling**: Addressed by a persistent `httpx.AsyncClient`.
- **Redundant Downloads**: Prevented by storing file hashes and only updating on changes.
- **Virus Scan Overhead**: In-memory scanning might add overhead, but ensures security.
- **Virus Scan Failures**: If ClamAV is unavailable or fails (e.g., due to socket errors or size limits), the scraper falls back to MIME-type validation for Excel files instead of discarding them.
- **Fallback Traceability**: All skipped or MIME-only approved files are logged in `quarantine.log` with timestamp, reason, MIME type, and file size for audit and debugging.
- **Size Limit Errors**: If you see “INSTREAM: Size limit reached” warnings, increase `StreamMaxLength` in `clamd.conf`.
- **Windows Skipping**: If you can’t run ClamAV natively, the skip mechanism means the scraper still works without throwing errors.

---

## **Current Limitations**

1. **HTTP/2 Support**: If the server lacks HTTP/2, it falls back to HTTP/1.1 automatically.
2. **Depth Control**: Subpage recursion is limited (by default depth=1). Extend if deeper crawling is needed.
3. **Year Parsing**: Skips links that don’t contain a straightforward 4-digit year (≥ 2018). Update the regex for more complex date formats.
4. **ClamAV on Windows**: Typically requires WSL, Docker, or disabling the scanning code.
5. **Custom Retry Logic**: For advanced back-off patterns, modify the `tenacity` settings or override in your subclass.

---

## **Other Potential Improvements**

- **Email Notifications**: Notify users when a new dataset is fetched.
- **Database Integration**: Store metadata in a database for better tracking.
- **More Robust Exception Handling**: Log specific error types or integrate external alerting.
- **Integrating BeautifulSoup**: Incorporate `BeautifulSoup` as opposed to Selenium for a faster setup for raw Web Scraping.

---

## **License**

This project is licensed under the MIT License. See the LICENSE file for details.

---

## **Author**

Developed by **Dylan Picart at Partnership With Children**.

For questions or contributions, contact: [dpicart@partnershipwithchildren.org](mailto:dpicart@partnershipwithchildren.org).
