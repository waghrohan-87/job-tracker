"""Foundit.in (formerly Monster India) scraper."""

import logging
import time
import random
import json
from urllib.parse import urlencode, quote
from .base import BaseScraper

logger = logging.getLogger(__name__)


class FounditScraper(BaseScraper):

    SEARCH_URL = "https://www.foundit.in/srp/results"
    API_URL = "https://www.foundit.in/middleware/jobsearch/v2/search"

    def search(self, title: str, location: str, max_results: int = 5) -> list:
        jobs = []
        try:
            params = {
                "query": title,
                "locationPreferences": location,
                "experienceRanges": "0~20",
                "sort": "1",
                "limit": max_results,
                "start": 0,
            }
            self.session.headers.update({
                "Referer": "https://www.foundit.in/",
                "Accept": "application/json",
                "x-requested-with": "XMLHttpRequest",
            })
            time.sleep(random.uniform(2, 4))
            r = self.session.get(self.API_URL, params=params, timeout=20)

            if r.status_code != 200:
                # Fallback to HTML scrape
                return self._html_search(title, location, max_results)

            data = r.json()
            job_list = data.get("jobSearchResponse", {}).get("data", []) or \
                       data.get("data", []) or []

            for j in job_list[:max_results]:
                job_url = j.get("applyUrl") or j.get("jobUrl") or ""
                if not job_url:
                    job_id = j.get("jobId") or j.get("id") or ""
                    job_url = f"https://www.foundit.in/job/{job_id}" if job_id else ""
                if not job_url:
                    continue

                jobs.append({
                    "title": j.get("jobTitle", title),
                    "company": j.get("companyName", "Unknown"),
                    "location": j.get("location") or j.get("city") or location,
                    "job_board": "Foundit",
                    "job_url": job_url,
                    "description": j.get("jobDescription", "")[:4000],
                })

        except Exception as e:
            logger.error(f"Foundit scrape error for '{title}': {e}")

        return jobs

    def _html_search(self, title: str, location: str, max_results: int) -> list:
        """HTML fallback if API fails."""
        jobs = []
        try:
            params = {"query": title, "locationPreferences": location, "sort": "1"}
            r = self._get(self.SEARCH_URL, params=params)
            if not r:
                return jobs
            soup = self._soup(r.text)
            cards = soup.find_all("div", attrs={"class": lambda c: c and "cardContainer" in (c or "")})
            for card in cards[:max_results]:
                link = card.find("a", href=True)
                if not link:
                    continue
                href = link["href"]
                if not href.startswith("http"):
                    href = "https://www.foundit.in" + href
                title_el = card.find("h3") or card.find("a", attrs={"class": lambda c: c and "jobTitle" in (c or "")})
                company_el = card.find("span", attrs={"class": lambda c: c and "company" in (c or "").lower()})
                jobs.append({
                    "title": self.safe_text(title_el, title),
                    "company": self.safe_text(company_el, "Unknown"),
                    "location": location,
                    "job_board": "Foundit",
                    "job_url": href,
                    "description": "",
                })
        except Exception as e:
            logger.warning(f"Foundit HTML fallback error: {e}")
        return jobs
