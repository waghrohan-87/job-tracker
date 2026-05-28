"""
Apna.co scraper + Generic scraper for Lever / Workable / custom career pages.
"""

import logging
import time
import random
import re
from urllib.parse import urlencode, urlparse
from .base import BaseScraper

logger = logging.getLogger(__name__)


# ── Apna ──────────────────────────────────────────────────────────────────────

class ApnaScraper(BaseScraper):

    BASE = "https://apna.co"
    SEARCH = "https://apna.co/jobs"

    def search(self, title: str, location: str, max_results: int = 5) -> list:
        jobs = []
        try:
            params = {"search": title, "city": location}
            r = self._get(self.SEARCH, params=params, delay=3)
            if not r:
                return jobs

            soup = self._soup(r.text)
            cards = soup.find_all("div", attrs={"class": lambda c: c and "job-card" in (c or "").lower()}) or \
                    soup.find_all("article")

            for card in cards[:max_results]:
                try:
                    link = card.find("a", href=True)
                    if not link:
                        continue
                    href = link["href"]
                    if not href.startswith("http"):
                        href = self.BASE + href

                    title_el = card.find("h2") or card.find("h3") or \
                               card.find(attrs={"class": lambda c: c and "title" in (c or "").lower()})
                    company_el = card.find(attrs={"class": lambda c: c and "company" in (c or "").lower()})
                    location_el = card.find(attrs={"class": lambda c: c and "location" in (c or "").lower()})

                    jobs.append({
                        "title": self.safe_text(title_el, title),
                        "company": self.safe_text(company_el, "Unknown"),
                        "location": self.safe_text(location_el, location),
                        "job_board": "Apna",
                        "job_url": href,
                        "description": "",
                    })
                    time.sleep(random.uniform(0.5, 1.5))
                except Exception as e:
                    logger.warning(f"Apna card parse error: {e}")

        except Exception as e:
            logger.error(f"Apna scrape error for '{title}': {e}")

        return jobs


# ── Generic Lever / Workable / Custom Career Pages ────────────────────────────

class GenericCareerScraper(BaseScraper):
    """
    Scrapes a company's Lever or Workable jobs board.
    Also handles generic HTML career pages.

    Lever boards:  https://jobs.lever.co/companyname
    Workable boards: https://apply.workable.com/companyname
    """

    def search(self, title: str, location: str, max_results: int = 5) -> list:
        """Not used for generic scraper — use scrape_url() directly."""
        return []

    def scrape_url(self, company_name: str, url: str, active_titles: list, max_results: int = 10) -> list:
        """
        Scrape a specific career page URL and return matching jobs.
        Filters results against active_titles (fuzzy match).
        """
        jobs = []
        parsed = urlparse(url)
        host = parsed.netloc.lower()

        if "lever.co" in host:
            jobs = self._scrape_lever(company_name, url, max_results)
        elif "workable.com" in host:
            jobs = self._scrape_workable(company_name, url, max_results)
        elif "greenhouse.io" in host:
            jobs = self._scrape_greenhouse(company_name, url, max_results)
        else:
            jobs = self._scrape_generic(company_name, url, max_results)

        # Filter to relevant titles only
        matched = []
        for job in jobs:
            for t in active_titles:
                if self._title_matches(job["title"], t):
                    matched.append(job)
                    break

        return matched[:max_results]

    def _title_matches(self, job_title: str, search_title: str) -> bool:
        """Fuzzy title match — check if key words overlap."""
        jt = job_title.lower()
        st = search_title.lower()
        # Direct contains check
        if st in jt or jt in st:
            return True
        # Word overlap — at least 2 significant words match
        jt_words = set(w for w in jt.split() if len(w) > 3)
        st_words = set(w for w in st.split() if len(w) > 3)
        overlap = jt_words & st_words
        return len(overlap) >= 2

    def _scrape_lever(self, company: str, url: str, max_results: int) -> list:
        jobs = []
        try:
            # Lever has a JSON API endpoint
            api_url = url.rstrip("/") + "?format=json"
            r = self._get(api_url, delay=2)
            if r and r.headers.get("content-type", "").startswith("application/json"):
                data = r.json()
                postings = data if isinstance(data, list) else []
                for p in postings[:max_results]:
                    job_url = p.get("hostedUrl") or p.get("applyUrl") or ""
                    jobs.append({
                        "title": p.get("text", ""),
                        "company": company,
                        "location": p.get("categories", {}).get("location", "India"),
                        "job_board": "Lever",
                        "job_url": job_url,
                        "description": p.get("descriptionPlain", "")[:4000],
                    })
            else:
                # HTML fallback
                r = self._get(url, delay=2)
                if not r:
                    return jobs
                soup = self._soup(r.text)
                for posting in soup.find_all("div", {"class": "posting"})[:max_results]:
                    title_el = posting.find("h5")
                    link = posting.find("a", {"class": "posting-title"})
                    location_el = posting.find("span", {"class": "location"})
                    if not title_el or not link:
                        continue
                    href = link.get("href", "")
                    if not href.startswith("http"):
                        href = "https://jobs.lever.co" + href
                    jobs.append({
                        "title": self.safe_text(title_el),
                        "company": company,
                        "location": self.safe_text(location_el, "India"),
                        "job_board": "Lever",
                        "job_url": href,
                        "description": "",
                    })
        except Exception as e:
            logger.error(f"Lever scrape error for {url}: {e}")
        return jobs

    def _scrape_workable(self, company: str, url: str, max_results: int) -> list:
        jobs = []
        try:
            # Workable jobs page
            r = self._get(url, delay=2)
            if not r:
                return jobs
            soup = self._soup(r.text)
            cards = soup.find_all("li", attrs={"data-ui": "job"}) or \
                    soup.find_all("article", attrs={"class": lambda c: c and "job" in (c or "").lower()})
            for card in cards[:max_results]:
                title_el = card.find("h3") or card.find("h2")
                link = card.find("a", href=True)
                loc_el = card.find("span", attrs={"class": lambda c: c and "location" in (c or "").lower()})
                if not link:
                    continue
                href = link["href"]
                if not href.startswith("http"):
                    href = "https://apply.workable.com" + href
                jobs.append({
                    "title": self.safe_text(title_el, ""),
                    "company": company,
                    "location": self.safe_text(loc_el, "India"),
                    "job_board": "Workable",
                    "job_url": href,
                    "description": "",
                })
        except Exception as e:
            logger.error(f"Workable scrape error for {url}: {e}")
        return jobs

    def _scrape_greenhouse(self, company: str, url: str, max_results: int) -> list:
        jobs = []
        try:
            r = self._get(url, delay=2)
            if not r:
                return jobs
            soup = self._soup(r.text)
            for row in soup.find_all("div", {"class": "opening"})[:max_results]:
                link = row.find("a", href=True)
                if not link:
                    continue
                href = link["href"]
                if not href.startswith("http"):
                    href = "https://boards.greenhouse.io" + href
                location_el = row.find("span", {"class": "location"})
                jobs.append({
                    "title": self.safe_text(link),
                    "company": company,
                    "location": self.safe_text(location_el, "India"),
                    "job_board": "Greenhouse",
                    "job_url": href,
                    "description": "",
                })
        except Exception as e:
            logger.error(f"Greenhouse scrape error for {url}: {e}")
        return jobs

    def _scrape_generic(self, company: str, url: str, max_results: int) -> list:
        jobs = []
        try:
            r = self._get(url, delay=2)
            if not r:
                return jobs
            soup = self._soup(r.text)
            # Heuristic: find links that look like job listings
            job_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                if not text or len(text) < 5:
                    continue
                # Keywords that suggest a job link
                if any(kw in href.lower() for kw in ["job", "career", "position", "opening", "vacancy"]):
                    if not href.startswith("http"):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    job_links.append((text, href))

            seen_hrefs = set()
            for text, href in job_links[:max_results * 2]:
                if href in seen_hrefs:
                    continue
                seen_hrefs.add(href)
                jobs.append({
                    "title": text,
                    "company": company,
                    "location": "India",
                    "job_board": "Company Career Page",
                    "job_url": href,
                    "description": "",
                })
                if len(jobs) >= max_results:
                    break
        except Exception as e:
            logger.error(f"Generic career page scrape error for {url}: {e}")
        return jobs
