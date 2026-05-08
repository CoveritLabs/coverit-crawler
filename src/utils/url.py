from urllib.parse import urlparse

def is_http_url(url: str) -> bool:
    normalized = (url or "").strip().lower()

    return (
        normalized.startswith("http://")
        or normalized.startswith("https://")
    )

def is_non_http_href(href: str) -> bool:
    normalized = (href or "").strip().lower()

    if not normalized:
        return False

    return not (
        normalized.startswith("http://")
        or normalized.startswith("https://")
        or normalized.startswith("/")
    )

def is_same_domain(url1: str, url2: str) -> bool:
    return urlparse(url1).netloc == urlparse(url2).netloc

def normalize_url(url: str) -> str:
    u = str(url or "")
    if u.endswith("?"):
        u = u[:-1]
    u = u.split("#", 1)[0]
    return u


def normalize_checkpoint_url(url: str) -> str:
    u = str(url or "")
    if u.endswith("?"):
        u = u[:-1]
    return u