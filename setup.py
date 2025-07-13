from setuptools import setup, find_packages

setup(
    name="nyc_infohub_excel_api_access",
    version="1.0.14",
    author="Dylan Picart",
    author_email="dylanpicart@mail.adelphi.edu",
    description="A Python scraper for downloading Excel datasets from NYC InfoHub.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/dylanpicart/excel_api_access",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "httpx[http2]>=0.28.1",
        "tenacity>=8.0.1",
        "pyclamd",
        "clamd", 
        "python-magic",
        "selenium>=4.10.0",
        "pandas>=1.3.0",
        "tqdm>=4.62.0",
        "openpyxl>=3.0.9",
        "pyxlsb>=1.0.10",
        "xlrd>=2.0.1",
        "python-dotenv>=1.0.0",
        "pytest>=7.0, <8.0",
        "pytest-asyncio",
        "pytest-cov"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    entry_points={'console_scripts': ['nyc-infohub-scraper = excel_scraper:run_scraper']}
)