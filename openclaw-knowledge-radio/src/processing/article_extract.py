from __future__ import annotations

from newspaper import Article
import requests
from bs4 import BeautifulSoup


def _extract_with_newspaper(url: str) -> str:
    article = Article(url)
    article.download()
    article.parse()
    return (article.text or "").strip()


def _extract_with_bs4(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
    }
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Remove noisy tags
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()

    # Prefer article/main content when available
    candidates = []
    article_tag = soup.find("article")
    main_tag = soup.find("main")
    if article_tag:
        candidates.append(article_tag.get_text("\n", strip=True))
    if main_tag:
        candidates.append(main_tag.get_text("\n", strip=True))

    # ArXiv abstract fallback
    if "arxiv.org" in url:
        abs_block = soup.find("blockquote", class_="abstract")
        if abs_block:
            candidates.append(abs_block.get_text(" ", strip=True).replace("Abstract:", "").strip())

    # Global fallback
    candidates.append(soup.get_text("\n", strip=True))

    # Return the longest reasonably clean candidate
    best = max((c for c in candidates if c), key=len, default="")
    return best.strip()


def extract_article_text(url: str) -> str:
    # 1) newspaper first (often cleaner)
    try:
        txt = _extract_with_newspaper(url)
        if len(txt) >= 800:
            return txt
    except Exception:
        pass

    # 2) bs4 fallback for paywall-ish / structured pages
    try:
        txt = _extract_with_bs4(url)
        return txt
    except Exception:
        return ""
