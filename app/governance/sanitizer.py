"""Sanitize scraped content before AI processing."""

import re

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"disregard\s+(the\s+)?(system|above)",
    r"you\s+are\s+now",
    r"<\s*script",
    r"javascript:",
]


def sanitize_text(text: str, *, max_length: int = 120_000) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"<script[^>]*>.*?</script>", "", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    for pattern in INJECTION_PATTERNS:
        cleaned = re.sub(pattern, "[filtered]", cleaned, flags=re.I)

    return cleaned[:max_length]
