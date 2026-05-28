"""
LinkedIn Jobs scraper.
Uses LinkedIn's public job search endpoint — no login required.
If this gets blocked, swap to the Apify LinkedIn scraper actor.
"""

import logging
import time
import random
from urllib.parse import urlencode
from .base import BaseScraper

logger = logging.getLogger(__name__)


class LinkedInScraper(BaseScraper):

    SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    JOB_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

    def search(self, title: str, location: str, max_results: int = 5) -> list:
        jobs = []
        try:
            params = {
                "keywords": title,
                "location": location,
                "f_TPR": "r86400",  # posted in last 24 hours
                "sortBy": "DD",
                "start": 0,
            }
            url = f"{self.SEARCH_URL}?{urlencode(params)}"
            r = self._get(url, delay=3)
            if not r:
                return jobs

            soup = self._soup(r.text)
            cards = soup.find_all("div", {"class": "base-card"}) or \
                    soup.find_all("li", attrs={"class": lambda c: c and "result-card" in (c or "")})

            for card in cards[:max_results]:
                try:
                    # Extract job ID
                    data_id = card.get("data-entity-urn", "")
                    job_id = data_id.split(":")[-1] if data_id else ""

                    title_el = card.find("h3", {"class": "base-search-card__title"})
                    company_el = card.find("h4", {"class": "base-search-card__subtitle"})
                    location_el = card.find("span", {"class": "job-search-card__location"})
                    link = card.find("a", {"class": "base-card__full-link"})

                    job_url = link["href"].split("?")[0] if link else ""
                    if not job_url:
                        continue

                    description = ""
                    if job_id:
                        description = self._fetch_description(job_id)

                    jobs.append({
                        "title": self.safe_text(title_el, title),
                        "company": self.safe_text(company_el, "Unknown"),
                        "location": self.safe_text(location_el, location),
                        "job_board": "LinkedIn",
                        "job_url": job_url,
                        "description": description,
                    })
                    time.sleep(random.uniform(2, 4))
                except Exception as e:
                    logger.warning(f"LinkedIn card parse error: {e}")

        except Exception as e:
            logger.error(f"LinkedIn scrape error for '{title}': {e}")

        return jobs

    def _fetch_description(self, job_id: str) -> str:
        try:
            url = self.JOB_URL.format(job_id=job_id)
            time.sleep(random.uniform(1, 3))
            r = self._get(url, delay=1)
            if not r:
                return ""
            soup = self._soup(r.text)
            desc = soup.find("div", {"class": "show-more-less-html__markup"}) \
                 or soup.find("section", {"class": "description"})
            if desc:
                return desc.get_text(separator="\n", strip=True)[:4000]
        except Exception as e:
            logger.warning(f"LinkedIn description fetch error: {e}")
        return ""
