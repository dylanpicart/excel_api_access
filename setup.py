from setuptools import setup, find_packages

setup(
    name="nyc_infohub_scraper",
    version="1.0.0",
    author="Dylan Picart",
    author_email="dpicart@partnershipwithchildren.org",
    description="A Python scraper for downloading Excel datasets from NYC InfoHub.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/dylanpicart/nyc_infohub_scraper",
    packages=find_packages(),
    install_requires=[
        "selenium>=4.10.0",
        "pandas>=1.3.0",
        "requests>=2.26.0",
        "tqdm>=4.62.0",
        "openpyxl>=3.0.9",
        "pyxlsb>=1.0.10",
        "xlrd>=2.0.1",
        "python-dotenv>=1.0.0"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
)