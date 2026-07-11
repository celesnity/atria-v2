"""video_resolve.py — resolve a pasted video link / caption to a real dataset POI.

Transcript-first and HONEST: we do NOT fetch or watch the video (the module
sandbox can't reach the network, and guessing would fabricate). We resolve the
*caption text the user pasted* (plus any readable slug in the URL) against the
curated dataset via the same `search.cmd_search` engine every other feature uses.
When nothing matches with confidence we say so plainly rather than inventing a place.

Usage:
  python video_resolve.py --text "quán này ở Quận 1 xịn thật https://tiktok.com/@foo/123"
  echo '{"text": "..."}' | python video_resolve.py     # stdin JSON {text}

Output JSON:
  {ok, matched, poi|null, confidence, source, creator, query, reply_vi, reply_en, note}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _data import fold  # noqa: E402

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_HANDLE_RE = re.compile(r"@([A-Za-z0-9._]{2,30})")
_SOURCES = {
    "tiktok": "TikTok", "douyin": "TikTok", "youtube": "YouTube", "youtu.be": "YouTube",
    "instagram": "Instagram", "facebook": "Facebook", "fb.watch": "Facebook",
}


def _source_of(url: str) -> str:
    u = url.lower()
    for key, label in _SOURCES.items():
        if key in u:
            return label
    return "Video"


def _slug_words(url: str) -> str:
    """Turn a readable URL path slug into words (skip pure ids/hashes)."""
    try:
        path = url.split("//", 1)[-1].split("/", 1)[-1]
    except Exception:
        return ""
    path = re.split(r"[?#]", path)[0]
    parts = re.split(r"[/\-_]+", path)
    words = [p for p in parts if p and not p.isdigit() and not re.fullmatch(r"[0-9a-f]{6,}", p)
             and not p.startswith("@") and len(p) > 2]
    return " ".join(words)


def _confidence(query: str, top: dict, second: dict | None) -> float:
    """Honest heuristic from what the engine returned — never fabricated.
    High when the caption literally contains the matched name; lower when we
    leaned on a category/loose match; damped when the runner-up is close."""
    qf = fold(query)
    name_f = fold(top.get("name", ""))
    conf = 0.55
    if name_f and name_f in qf:
        conf = 0.95                          # caption names the place outright
    elif any(tok in qf for tok in name_f.split() if len(tok) > 3):
        conf = 0.75                          # partial name overlap
    # a near-tie runner-up means we're less sure which one the video showed
    if second is not None:
        conf -= 0.1
    return round(max(0.4, min(conf, 0.98)), 2)


def resolve(text: str) -> dict:
    text = (text or "").strip()
    urls = _URL_RE.findall(text)
    url = urls[0] if urls else ""
    source = _source_of(url) if url else "Video"
    handle = None
    m = _HANDLE_RE.search(url or text)
    if m:
        handle = "@" + m.group(1)

    # searchable text = caption minus the URL, backfilled from the URL slug
    caption = _URL_RE.sub("", text).strip()
    query = caption or _slug_words(url)
    query = query.strip()

    out = {
        "ok": True, "matched": False, "poi": None, "confidence": 0.0,
        "source": source, "creator": handle, "query": query,
        "reply_vi": "", "reply_en": "", "note": "",
    }
    if not query:
        out["note"] = "no_caption"
        out["reply_vi"] = ("Chưa đọc được địa điểm từ link này — hãy dán kèm chú thích "
                           "(caption) có tên quán/địa điểm nhé.")
        out["reply_en"] = ("Couldn't read a place from that link — paste the caption "
                           "with the place name and I'll find it.")
        return out

    from search import cmd_search  # lazy: keep engine-independent
    try:
        res = cmd_search(SimpleNamespace(query=query, limit=5, city=None,
                                         category=None, prior=None))
    except Exception as exc:  # engine failure -> honest miss, never a guess
        out["note"] = f"engine_error:{str(exc)[:80]}"
        out["reply_vi"] = "Không tra cứu được lúc này — thử lại sau nhé."
        out["reply_en"] = "Couldn't look that up right now — try again shortly."
        return out

    results = res.get("results") or []
    if not results:
        out["note"] = "no_match"
        out["reply_vi"] = (f"Mình chưa khớp được “{query}” với địa điểm nào trong dữ "
                           "liệu — có thể quán chưa có trong bản đồ.")
        out["reply_en"] = (f"I couldn't match “{query}” to a place in the dataset — "
                           "it may not be on the map yet.")
        return out

    top = results[0]
    conf = _confidence(query, top, results[1] if len(results) > 1 else None)
    out.update({
        "matched": True, "poi": top, "confidence": conf,
        "reply_vi": (f"Địa điểm trong video: {top['name']}"
                     + (f" ({source}" + (f" · {handle}" if handle else "") + ")" if url else "")
                     + f" — khớp {int(conf * 100)}%."),
        "reply_en": (f"Location from the video: {top['name']} — {int(conf * 100)}% match."),
    })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default=None)
    args = ap.parse_args()
    text = args.text
    if text is None:
        raw = sys.stdin.read()
        try:
            text = (json.loads(raw) or {}).get("text", "") if raw.strip() else ""
        except Exception:
            text = raw
    print(json.dumps(resolve(text or ""), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
