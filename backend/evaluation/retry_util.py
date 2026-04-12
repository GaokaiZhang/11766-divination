"""Shared retry logic for OpenAI API calls during evaluation."""
import time
import logging

from openai import RateLimitError

logger = logging.getLogger(__name__)


def retry_on_rate_limit(func, *args, max_retries=8, base_delay=3.0, **kwargs):
    """Call func(*args, **kwargs) with exponential backoff on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning("Rate limit hit (attempt %d/%d), waiting %.1fs...",
                           attempt + 1, max_retries, delay)
            print(f"    [rate limit, waiting {delay:.0f}s...]")
            time.sleep(delay)
