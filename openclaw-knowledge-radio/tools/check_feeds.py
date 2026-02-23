#!/usr/bin/env python3

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
import requests
import feedparser


def load_cfg() -> Dict[str, Any]:
    cfg_path = Path("config.yaml")
    if not cfg_path.exists():
        raise FileNotFoundError("config.yaml not found in current directory")
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def fetch(url: str, timeout: int = 25) -> Tuple[int, str, str]:
    """
    Returns (status_code, final_url, text_prefix)
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, /;q=0.7",
        "Accept-Language": "en-GB,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    txt = r.text or ""
    return r.status_code, str(r.url), txt[:4000]


def is_probably_xml(text_prefix: str) -> bool:
    t = text_prefix.lstrip().lower()
    return t.startswith("<?xml") or t.startswith("<rss") or t.startswith("<feed") or t.startswith("<rdf")


def main() -> None:
    cfg = load_cfg()
    feeds: List[Dict[str, Any]] = cfg.get("rss_sources", []) or cfg.get("feeds", []) or []
    if not feeds:
        print("No feeds found: expected cfg['rss_sources'] (or cfg['feeds']).")
        return

    out_dir = Path("output") / "feed_health"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = []
    ok_count = 0

    print(f"Checking {len(feeds)} feeds...\n")

    for i, f in enumerate(feeds, start=1):
        name = f.get("name", f"feed_{i}")
        url = f.get("url")
        if not url:
            report.append({"name": name, "url": None, "ok": False, "error": "missing url"})
            continue

        row: Dict[str, Any] = {"name": name, "url": url}
        t0 = time.time()
        try:
            status, final_url, prefix = fetch(url)
            row["status"] = status
            row["final_url"] = final_url
            row["looks_xml"] = is_probably_xml(prefix)

            parsed = feedparser.parse(prefix if row["looks_xml"] else prefix)
            entries = parsed.entries or []
            row["n_entries_in_payload"] = len(entries)

            # take a few titles
            sample = []
            for e in entries[:3]:
                title = (e.get("title") or "").strip()
                link = (e.get("link") or "").strip()
                if title or link:
                    sample.append({"title": title[:120], "link": link[:200]})
            row["sample"] = sample

            if status == 200 and len(entries) > 0 and row["looks_xml"]:
                row["ok"] = True
                ok_count += 1
            else:
                row["ok"] = False
                # helpful hint
                if status in (401, 403):
                    row["hint"] = "blocked (401/403). likely WAF/Cloudflare. consider alternate feed or a fetch service."
                elif status in (301, 302, 307, 308):
                    row["hint"] = "redirect. check final_url and whether it is actually XML."
                elif status == 200 and not row["looks_xml"]:
                    row["hint"] = "returned HTML not XML. RSS link may be wrong or blocked."
                elif status == 200 and row["looks_xml"] and len(entries) == 0:
                    row["hint"] = "XML but zero entries in sampled payload. could be truncated preview; try fetching full body."
                else:
                    row["hint"] = "unknown; inspect saved prefix for clues."

            # save prefix for debugging
            safe_name = "".join(c if c.isalnum() else "_" for c in name)[:60]
            (out_dir / f"{i:02d}_{safe_name}.head.txt").write_text(prefix, encoding="utf-8", errors="ignore")

        except Exception as e:
            row["ok"] = False
            row["error"] = repr(e)

        row["elapsed_s"] = round(time.time() - t0, 3)
        report.append(row)

        status_str = row.get("status", "ERR")
        ok_str = "OK" if row["ok"] else "FAIL"
        print(f"{i:02d}. {ok_str} [{status_str}] {name} -> {row.get('final_url', url)}")

    out_path = out_dir / "report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK feeds: {ok_count}/{len(feeds)}")
    print(f"Report written: {out_path}")
    print(f"Head samples saved under: {out_dir}")


if __name__ == "__main__":
    main()
