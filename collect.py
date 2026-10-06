#!/usr/bin/env python3
"""dumwiki collector.

Reads the feeds in feeds.json, groups headlines about the same event,
scores each event by how many outlets covered it, and merges the result
into events.json (which the wiki page reads). Standard library only.

Usage:  python3 collect.py            (uses feeds.json, writes events.json)
        python3 collect.py FEEDS OUT  (custom files, used by the tests)
"""
import hashlib, json, re, sys, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).parent
WINDOW = timedelta(hours=48)   # headlines further apart than this are never the same event
SIMILAR = 0.45                 # how alike two headlines must be (0-1) to count as one event
STOP = set("the a an and or of to in on for with as at by from is are was were be has have its it this that "
           "after over amid says say new will could may why how what crypto".split())


# Topic tags: an event gets a tag when its headline or summary contains one of the words.
TAGS = {
    "bitcoin": ["bitcoin", "btc"], "ethereum": ["ethereum", "ether", "eth"], "solana": ["solana", "sol"],
    "stablecoins": ["stablecoin", "usdt", "usdc", "tether", "circle"],
    "defi": ["defi", "dex", "lending", "liquidity", "yield", "staking"],
    "exchanges": ["exchange", "binance", "coinbase", "kraken", "okx", "bybit"],
    "security": ["hack", "hacked", "exploit", "breach", "drained", "stolen", "phishing", "attack"],
    "regulation": ["sec", "cftc", "regulator", "regulation", "bill", "congress", "law", "ban", "mica"],
    "legal": ["lawsuit", "court", "sued", "charged", "sentenced", "settlement", "fraud", "trial"],
    "etfs": ["etf", "etfs"], "memecoins": ["memecoin", "meme", "doge", "dogecoin", "pepe"],
    "funding": ["raises", "raised", "funding", "acquires", "acquisition", "ipo", "valuation"],
    "markets": ["price", "rally", "plunge", "crash", "surge", "liquidation", "liquidations", "all-time"],
    "ai": ["ai", "agent", "agents"], "nfts": ["nft", "nfts"],
    "macro": ["fed", "inflation", "rates", "tariff", "tariffs", "treasury"],
}


def tags_for(text):
    words = set(re.findall(r"[a-z0-9\-]+", text.lower()))
    return sorted(t for t, keys in TAGS.items() if words & set(keys))


def clean(html, limit=280):
    """Plain-text excerpt from a feed description."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = " ".join(text.replace("&nbsp;", " ").replace("&amp;", "&").split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


def fetch(url):
    if url.startswith("file:"):
        return Path(url[5:]).read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": "dumwiki/0.2"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def parse_date(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)
    except Exception:
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def parse_feed(data, source):
    """Return [{source,title,url,date}] from RSS or Atom."""
    items = []
    for node in ET.fromstring(data).iter():
        if local(node.tag) not in ("item", "entry"):
            continue
        f = {"title": "", "url": "", "date": None, "summary": ""}
        for c in node:
            name = local(c.tag)
            if name == "title":
                f["title"] = " ".join((c.text or "").split())
            elif name == "link":
                f["url"] = f["url"] or (c.text or "").strip() or c.attrib.get("href", "")
            elif name in ("pubdate", "published", "updated", "date"):
                f["date"] = f["date"] or parse_date(c.text)
            elif name in ("description", "summary"):
                f["summary"] = f["summary"] or clean(c.text)
        if f["title"] and f["url"].startswith("http") and f["date"]:
            items.append({"source": source, "title": f["title"], "url": f["url"], "date": f["date"], "summary": f["summary"]})
    return items


def tokens(title):
    return {w for w in re.findall(r"[a-z0-9$]+", title.lower()) if len(w) > 2 and w not in STOP}


def alike(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def score(ev):
    """Relevance: 10 points per distinct outlet covering it, plus 1 per extra mention.
    When impressions data is added (X, Reddit), add it here."""
    outlets = {m["source"] for m in ev["mentions"]}
    return 10 * len(outlets) + (len(ev["mentions"]) - len(outlets))


def run(feeds_path, out_path):
    feeds = json.loads(Path(feeds_path).read_text())
    out_path = Path(out_path)
    events = []
    if out_path.exists():
        for ev in json.loads(out_path.read_text()).get("events", []):
            for m in ev["mentions"]:
                m["date"] = parse_date(m["date"])
            ev["date"] = parse_date(ev["date"])
            ev["_tok"] = tokens(ev["title"])
            events.append(ev)
    seen = {m["url"] for ev in events for m in ev["mentions"]}

    new, failed = [], []
    for f in feeds:
        try:
            new += parse_feed(fetch(f["url"]), f["source"])
        except Exception as e:  # one broken feed must not stop the rest
            failed.append(f"{f['source']}: {e}")
    added = 0
    for it in sorted(new, key=lambda x: x["date"]):
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        added += 1
        tok = tokens(it["title"])
        best, best_s = None, 0.0
        for ev in events:
            if abs(ev["date"] - it["date"]) <= WINDOW:
                s = alike(tok, ev["_tok"])
                if s > best_s:
                    best, best_s = ev, s
        if best and best_s >= SIMILAR:
            best["mentions"].append(it)
        else:
            eid = hashlib.sha1((it["title"] + it["date"].isoformat()).encode()).hexdigest()[:10]
            events.append({"id": eid, "title": it["title"], "date": it["date"], "mentions": [it], "_tok": tok})

    for ev in events:
        ev.pop("_tok", None)
        ev["score"] = score(ev)
        ev["mentions"].sort(key=lambda m: m["date"])
        ev["first_seen"] = ev["mentions"][0]["date"].isoformat()
        ev["last_seen"] = ev["mentions"][-1]["date"].isoformat()
        ev["summary"] = max((m.get("summary", "") for m in ev["mentions"]), key=len)
        ev["tags"] = tags_for(" ".join(m["title"] + " " + m.get("summary", "") for m in ev["mentions"]))
        for m in ev["mentions"]:
            m["date"] = m["date"].isoformat()
        ev["date"] = ev["date"].isoformat()
    events.sort(key=lambda e: e["date"], reverse=True)
    out_path.write_text(json.dumps(
        {"updated": datetime.now(timezone.utc).isoformat(), "events": events}, indent=1))
    print(f"{added} new headlines, {len(events)} events total, {len(failed)} feeds failed")
    for f in failed:
        print("  failed:", f)
    return events


if __name__ == "__main__":
    a = sys.argv[1:]
    run(a[0] if a else ROOT / "feeds.json", a[1] if len(a) > 1 else ROOT / "events.json")
