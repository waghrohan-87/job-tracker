"""
Scraper orchestrator.
Runs all scrapers in sequence, deduplicates, returns new jobs only.
"""

import logging
import os
import hashlib
from .naukri import NaukriScraper
from .indeed import IndeedScraper
from .linkedin import LinkedInScraper
from .wellfound import WellfoundScraper
from .foundit import FounditScraper
from .custom_careers import ApnaScraper, GenericCareerScraper

logger = logging.getLogger(__name__)

MAX_PER_TITLE = int(os.environ.get("MAX_JOBS_PER_TITLE_PER_BOARD", "5"))
LOCATION = os.environ.get("SEARCH_LOCATION", "India")


def _hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def scrape_all_boards(titles: list, seen_hashes: set) -> list:
    """
    Scrape all job boards for all active titles.
    Returns list of new (unseen) job dicts.
    """
    scrapers = [
        NaukriScraper(),
        IndeedScraper(),
        LinkedInScraper(),
        WellfoundScraper(),
        FounditScraper(),
        ApnaScraper(),
    ]

    all_jobs = []
    seen_in_run = set()  # within-run dedup

    for scraper in scrapers:
        board_name = scraper.__class__.__name__.replace("Scraper", "")
        for title in titles:
            try:
                logger.info(f"Scraping {board_name} for: {title}")
                jobs = scraper.search(title, LOCATION, max_results=MAX_PER_TITLE)
                for job in jobs:
                    url = job.get("job_url", "")
                    if not url:
                        continue
                    h = _hash(url)
                    if h in seen_hashes or h in seen_in_run:
                        continue
                    seen_in_run.add(h)
                    job["_hash"] = h
                    all_jobs.append(job)
            except Exception as e:
                logger.error(f"{board_name} error for '{title}': {e}")

    logger.info(f"Total new jobs found from boards: {len(all_jobs)}")
    return all_jobs


def scrape_custom_urls(company_url_records: list, active_titles: list, seen_hashes: set) -> list:
    """
    Scrape user-defined company career pages.
    Returns list of new (unseen) job dicts.
    """
    scraper = GenericCareerScraper()
    all_jobs = []
    seen_in_run = set()

    for record in company_url_records:
        url = record["url"]
        company_name = record["company_name"]
        try:
            logger.info(f"Scraping custom URL: {url}")
            jobs = scraper.scrape_url(company_name, url, active_titles, max_results=10)
            for job in jobs:
                u = job.get("job_url", "")
                if not u:
                    continue
                h = _hash(u)
                if h in seen_hashes or h in seen_in_run:
                    continue
                seen_in_run.add(h)
                job["_hash"] = h
                job["_company_url_record_id"] = record.get("record_id")
                all_jobs.append(job)
        except Exception as e:
            logger.error(f"Custom URL scrape error for {url}: {e}")

    logger.info(f"Total new jobs from custom URLs: {len(all_jobs)}")
    return all_jobs
