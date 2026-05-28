"""Wellfound (AngelList) scraper — India jobs."""

import logging
import time
import random
from urllib.parse import urlencode
from .base import BaseScraper

logger = logging.getLogger(__name__)


class WellfoundScraper(BaseScraper):

    BASE = "https://wellfound.com"

    def search(self, title: str, location: str, max_results: int = 5) -> list:
        jobs = []
        try:
            # Wellfound uses a slug format for job search
            slug = title.lower().replace(" ", "-").replace("(", "").replace(")", "")
            url = f"{self.BASE}/role/{slug}"

            r = self._get(url, delay=3)
            if not r:
                return jobs

            soup = self._soup(r.text)

            # Job cards on Wellfound
            cards = soup.find_all("div", attrs={"data-test": "JobListing"}) or \
                    soup.find_all("div", attrs={"class": lambda c: c and "styles_component" in (c or "")})

            for card in cards[:max_results]:
                try:
                    title_el = card.find("a", attrs={"data-test": "job-title"}) \
                              or card.find("h2")
                    company_el = card.find("a", attrs={"data-test": "company-link"}) \
                               or card.find("span", attrs={"class": lambda c: c and "company" in (c or "").lower()})
                    location_el = card.find("span", attrs={"data-test": "job-location"}) \
                                or card.find("span", attrs={"class": lambda c: c and "location" in (c or "").lower()})

                    link = title_el if title_el and title_el.name == "a" else card.find("a", href=True)
                    if not link:
                        continue
                    href = link.get("href", "")
                    if not href.startswith("http"):
                        href = self.BASE + href

                    # Filter for India jobs
                    loc_text = self.safe_text(location_el, "")
                    if location.lower() not in loc_text.lower() and "india" not in loc_text.lower() and "remote" not in loc_text.lower():
                        continue

                    jobs.append({
                        "title": self.safe_text(title_el, title),
                        "company": self.safe_text(company_el, "Unknown"),
                        "location": loc_text or location,
                        "job_board": "Wellfound",
                        "job_url": href,
                        "description": "",  # Wellfound descriptions need JS render — left blank, Claude still scores on title+company
                    })
                    time.sleep(random.uniform(1, 2))
                except Exception as e:
                    logger.warning(f"Wellfound card parse error: {e}")

        except Exception as e:
            logger.error(f"Wellfound scrape error for '{title}': {e}")

        return jobs
