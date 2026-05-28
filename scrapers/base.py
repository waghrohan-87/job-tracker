"""
Base scraper class.
All board-specific scrapers inherit from this.
"""

import time
import random
import logging
import hashlib
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)
ua = UserAgent()


class BaseScraper(ABC):
    """
    Each scraper must implement search(title, location) and return
    a list of job dicts with these keys:
        title, company, location, job_board, job_url, description
    """

    def __init__(self):
        self.session = requests.Session()
        self._rotate_ua()

    def _rotate_ua(self):
        self.session.headers.update({
            "User-Agent": ua.random,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def _get(self, url, params=None, retries=3, delay=2):
        for attempt in range(retries):
            try:
                self._rotate_ua()
                time.sleep(random.uniform(delay, delay + 2))
                r = self.session.get(url, params=params, timeout=20)
                if r.status_code == 429:
                    logger.warning(f"Rate limited on {url}, waiting 30s")
                    time.sleep(30)
                    continue
                if r.status_code == 200:
                    return r
                logger.warning(f"HTTP {r.status_code} on {url}")
            except Exception as e:
                logger.warning(f"Request error attempt {attempt+1}: {e}")
                time.sleep(5)
        return None

    def _soup(self, html):
        return BeautifulSoup(html, "lxml")

    def job_hash(self, url):
        return hashlib.md5(url.encode()).hexdigest()

    @abstractmethod
    def search(self, title: str, location: str, max_results: int = 5) -> list:
        """Return list of job dicts."""
        pass

    def safe_text(self, element, default=""):
        if element is None:
            return default
        return element.get_text(separator=" ", strip=True)
