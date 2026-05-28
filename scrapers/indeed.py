"""Indeed India scraper."""

import logging
import time
import random
from urllib.parse import urlencode, quote_plus
from .base import BaseScraper

logger = logging.getLogger(__name__)


class IndeedScraper(BaseScraper):

    BASE = "https://in.indeed.com"

    def search(self, title: str, location: str, max_results: int = 5) -> list:
        jobs = []
        try:
            params = {
                "q": title,
                "l": location,
                "sort": "date",
                "fromage": "1",  # posted in last 1 day
                "limit": max_results,
            }
            url = f"{self.BASE}/jobs?{urlencode(params)}"
            r = self._get(url)
            if not r:
                return jobs

            soup = self._soup(r.text)
            cards = soup.find_all("div", {"class": "job_seen_beacon"}) or \
                    soup.find_all("div", attrs={"data-testid": "slider_container"})

            for card in cards[:max_results]:
                try:
                    title_el = card.find("h2", {"class": lambda c: c and "jobTitle" in (c or "")}) \
                              or card.find("a", {"data-jk": True})
                    company_el = card.find("span", {"data-testid": "company-name"}) \
                               or card.find("span", {"class": "companyName"})
                    location_el = card.find("div", {"data-testid": "text-location"}) \
                                or card.find("div", {"class": "companyLocation"})

                    link = card.find("a", href=True)
                    if not link:
                        continue
                    href = link["href"]
                    if not href.startswith("http"):
                        href = self.BASE + href

                    description = self._fetch_description(href)

                    jobs.append({
                        "title": self.safe_text(title_el, title),
                        "company": self.safe_text(company_el, "Unknown"),
                        "location": self.safe_text(location_el, location),
                        "job_board": "Indeed India",
                        "job_url": href,
                        "description": description,
                    })
                    time.sleep(random.uniform(1, 2))
                except Exception as e:
                    logger.warning(f"Indeed card parse error: {e}")

        except Exception as e:
            logger.error(f"Indeed scrape error for '{title}': {e}")

        return jobs

    def _fetch_description(self, url: str) -> str:
        try:
            r = self._get(url, delay=1)
            if not r:
                return ""
            soup = self._soup(r.text)
            desc = soup.find("div", {"id": "jobDescriptionText"}) \
                 or soup.find("div", attrs={"class": lambda c: c and "jobsearch-jobDescriptionText" in (c or "")})
            if desc:
                return desc.get_text(separator="\n", strip=True)[:4000]
        except Exception as e:
            logger.warning(f"Indeed description fetch error: {e}")
        return ""
