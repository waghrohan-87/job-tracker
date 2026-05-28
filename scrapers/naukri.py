"""Naukri.com scraper."""

import logging
import time
import random
from .base import BaseScraper

logger = logging.getLogger(__name__)

NAUKRI_SEARCH = "https://www.naukri.com/jobapi/v3/search"


class NaukriScraper(BaseScraper):

    def search(self, title: str, location: str, max_results: int = 5) -> list:
        jobs = []
        try:
            params = {
                "noOfResults": max_results,
                "urlType": "search_by_keyword",
                "searchType": "adv",
                "keyword": title,
                "location": location,
                "pageNo": 1,
                "src": "jobsearchDesk",
                "functionAreaIdGte": "",
                "sort": "1",  # sort by date
            }
            headers_extra = {
                "appid": "109",
                "systemid": "109",
                "Accept": "application/json",
                "Referer": "https://www.naukri.com/",
            }
            self._rotate_ua()
            self.session.headers.update(headers_extra)
            time.sleep(random.uniform(2, 4))
            r = self.session.get(NAUKRI_SEARCH, params=params, timeout=20)

            if r.status_code != 200:
                logger.warning(f"Naukri returned {r.status_code} for '{title}'")
                return jobs

            data = r.json()
            job_details = data.get("jobDetails", [])

            for j in job_details[:max_results]:
                job_url = j.get("jdURL", "")
                if not job_url:
                    continue
                if not job_url.startswith("http"):
                    job_url = "https://www.naukri.com" + job_url

                description = self._fetch_description(job_url)

                jobs.append({
                    "title": j.get("title", title),
                    "company": j.get("companyName", "Unknown"),
                    "location": j.get("placeholders", [{}])[0].get("label", location)
                              if j.get("placeholders") else location,
                    "job_board": "Naukri",
                    "job_url": job_url,
                    "description": description,
                })

        except Exception as e:
            logger.error(f"Naukri scrape error for '{title}': {e}")

        return jobs

    def _fetch_description(self, url: str) -> str:
        try:
            time.sleep(random.uniform(1, 2))
            r = self._get(url)
            if not r:
                return ""
            soup = self._soup(r.text)
            desc_div = soup.find("div", {"class": "styles_job-desc-container__txpYf"}) \
                     or soup.find("div", attrs={"class": lambda c: c and "job-desc" in c}) \
                     or soup.find("section", {"id": "job_description"})
            if desc_div:
                return desc_div.get_text(separator="\n", strip=True)[:4000]
        except Exception as e:
            logger.warning(f"Could not fetch Naukri description: {e}")
        return ""
