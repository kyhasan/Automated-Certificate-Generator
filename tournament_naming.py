"""Shared helpers for concise tournament titles and deployment names."""

import html
import re

MAX_SITE_NAME_LENGTH = 63


def format_tournament_title(name_or_title, category=None):
    """Return a readable tournament title without redundant category metadata."""
    if not category:
        detected_category = re.search(
            r'\b(?:under\s*-?\s*|u\s*-?\s*)(\d{1,2})',
            name_or_title,
            re.IGNORECASE
        )
        if detected_category:
            category = f"U{detected_category.group(1)}"

    cleaned = html.unescape(re.sub(r'<[^>]+>', '', name_or_title))
    cleaned = re.sub(r'\bcategory\b.*$', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b\d{6,}\b', ' ', cleaned)
    cleaned = re.sub(
        r'\b(?:under\s*-?\s*|u\s*-?\s*)\d{1,2}'
        r'(?:\s*(?:/|&|,|and|-)\s*(?:(?:under\s*-?\s*|u\s*-?\s*)?\d{1,2}))*',
        ' ',
        cleaned,
        flags=re.IGNORECASE
    )
    cleaned = re.sub(r'\bchildren(?:[\'’]s|-s)?\b', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r'\b(?:boys?\s*(?:&|and)\s*girls?|girls?\s*(?:&|and)\s*boys?)\b',
        ' ',
        cleaned,
        flags=re.IGNORECASE
    )
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' -/&')

    if category:
        category_text = re.sub(r'\s+', '', str(category)).strip()
        age_category = re.fullmatch(r'(?:u|under)-?(\d{1,2})', category_text, re.IGNORECASE)
        if age_category:
            category_text = f"U{age_category.group(1)}"
        elif category_text.isalpha():
            category_text = category_text.capitalize()
        if category_text:
            cleaned = f"{cleaned} {category_text}".strip()

    return cleaned or "Chess Tournament"


def slugify_site_name(name_or_title, category=None):
    """Create a concise, category-suffixed slug for a tournament site."""
    cleaned = format_tournament_title(name_or_title, category)
    cleaned = re.sub(r'(?i)\bchess\b', ' ', cleaned)
    if category:
        category_text = re.sub(r'\s+', '', str(category)).strip()
        age_category = re.fullmatch(r'(?:u|under)-?(\d{1,2})', category_text, re.IGNORECASE)
        suffix = (
            f"u{age_category.group(1)}"
            if age_category
            else re.sub(r'[^a-zA-Z0-9]+', '', category_text).lower()
        )
        suffix = _truncate_site_name(suffix, MAX_SITE_NAME_LENGTH)
        cleaned = re.sub(r'[^a-zA-Z0-9]+', '-', cleaned).strip('-').lower()
        if suffix and cleaned.endswith(f"-{suffix}"):
            cleaned = cleaned[:-(len(suffix) + 1)].rstrip('-')
        available_prefix_length = MAX_SITE_NAME_LENGTH - len(suffix) - (1 if cleaned else 0)
        prefix = _truncate_site_name(cleaned, max(0, available_prefix_length))
        return f"{prefix}-{suffix}" if prefix and suffix else (prefix or suffix)

    cleaned = re.sub(r'[^a-zA-Z0-9]+', '-', cleaned).strip('-').lower()
    return _truncate_site_name(cleaned, MAX_SITE_NAME_LENGTH)


def _truncate_site_name(name, max_length):
    """Truncate a slug at a word boundary where possible."""
    if len(name) <= max_length:
        return name

    truncated = name[:max_length].rstrip('-')
    if '-' in truncated:
        truncated = truncated.rsplit('-', 1)[0]
    return truncated
