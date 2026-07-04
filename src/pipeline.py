"""Shared pipeline steps used by both the local runner and the CI phases."""
import asyncio
import json
import os
import time

import aiohttp

from . import config as C
from . import checker
from .parser import parse_m3u
from .categorizer import Categorizer, normalize


# ---------------------------------------------------------------- collect
def build_categorizer():
    return Categorizer(
        C.load_list("selected.txt"),
        C.load_list("bangladesh.txt"),
        C.load_list("indian_bangla.txt"),
        C.load_list("popular.txt"),
        C.load_list("exclude.txt"),
    )


async def _fetch(session, url):
    try:
        if url.startswith(("http://", "https://")):
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=90)) as r:
                r.raise_for_status()
                return await r.text(errors="ignore")
        with open(url, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        print(f"[warn] source failed: {url} -> {e}", flush=True)
        return ""


async def _download_all(sources, ua):
    conn = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(connector=conn, headers={"User-Agent": ua}) as s:
        return await asyncio.gather(*[_fetch(s, u) for u in sources])


def _keep_patterns():
    return [x.strip().lower() for x in C.load_list("always_keep.txt") if x.strip()]


def _is_keep(entry, pats):
    if not pats:
        return False
    url = entry.get("url", "").lower()
    name = normalize(entry.get("name", ""))
    return any(p and (p in url or p in name) for p in pats)


def collect_channels(sources, cat, ua):
    """Download + parse + URL-dedup + classify -> list of channel dicts."""
    texts = asyncio.run(_download_all(sources, ua))
    keep_pats = _keep_patterns()
    seen = set()
    channels = []
    for src, txt in zip(sources, texts):
        for e in parse_m3u(txt, src):
            u = e.get("url")
            if not u or u in seen:
                continue
            seen.add(u)
            e["_cat"] = cat.classify(e)
            e["_rank"] = cat.selected_rank(e) if e["_cat"] == 1 else 10 ** 9
            e["_keep"] = _is_keep(e, keep_pats)
            channels.append(e)
    return channels


def extract_headers(entry, default_ua):
    h = {"User-Agent": default_ua}
    for ex in entry.get("extras", []):
        if "=" not in ex:
            continue
        low = ex.lower()
        val = ex.split("=", 1)[1].strip().strip('"')
        if not val:
            continue
        if "user-agent" in low:
            h["User-Agent"] = val
        elif "referrer" in low or "referer" in low:
            h["Referer"] = val
    return h


# ---------------------------------------------------------------- state
def load_state():
    if os.path.exists(C.STATE_FILE):
        try:
            with open(C.STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"fail": {}, "last_run": {}}


def save_state(state):
    os.makedirs(C.STATE_DIR, exist_ok=True)
    with open(C.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


# ---------------------------------------------------------------- flapping
def apply_flapping(channels, alive, prev_state, threshold):
    """Keep a channel through transient failures.

    - alive now            -> keep, reset fail count to 0
    - dead, never seen     -> drop immediately (fresh dead link)
    - dead, was seen       -> keep during grace, until `threshold` consecutive
                              fails, then drop
    Returns (kept_channels, new_fail_map, dropped_count).
    """
    prev_fail = prev_state.get("fail", {})
    new_fail = {}
    kept = []
    dropped = 0
    for e in channels:
        u = e["url"]
        if e.get("_keep") or alive.get(u):
            new_fail[u] = 0
            kept.append(e)
        else:
            prev = prev_fail.get(u)
            if prev is None:
                dropped += 1
                continue
            f = prev + 1
            if f >= threshold:
                dropped += 1
            else:
                new_fail[u] = f
                kept.append(e)
    return kept, new_fail, dropped


# ---------------------------------------------------------------- shape output
def sort_channels(channels, settings):
    if settings["sort_within_category"]:
        channels.sort(key=lambda e: (e["_cat"], e.get("_rank", 10 ** 9),
                                     normalize(e.get("name", ""))))
    else:
        channels.sort(key=lambda e: (e["_cat"], e.get("_rank", 10 ** 9)))
    return channels


def apply_caps(channels, settings):
    out = []
    counts = {}
    for e in channels:
        c = e["_cat"]
        counts[c] = counts.get(c, 0) + 1
        if e.get("_keep"):
            out.append(e)
            continue
        if c == 5 and settings["max_others"] and counts[5] > settings["max_others"]:
            continue
        if settings["max_per_category"] and counts[c] > settings["max_per_category"]:
            continue
        out.append(e)
    return out


def guard_ok(new_total, prev_total, ratio):
    if not prev_total:
        return True, ""
    floor = int(prev_total * ratio)
    if new_total < floor:
        return (False,
                f"kept {new_total} < floor {floor} "
                f"({int(ratio * 100)}% of previous {prev_total})")
    return True, ""


# ---------------------------------------------------------------- write
def _build_extinf(entry, settings):
    attrs = dict(entry.get("attrs", {}))
    if settings["set_group_by_category"]:
        attrs["group-title"] = C.CATEGORY_LABEL[entry["_cat"]]
    parts = ["#EXTINF:-1"] + [f'{k}="{v}"' for k, v in attrs.items()]
    return f'{" ".join(parts)},{entry.get("name", "")}'


def _write_playlist(path, entries, settings):
    with open(path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for e in entries:
            f.write(_build_extinf(e, settings) + "\n")
            for ex in e.get("extras", []):
                f.write(ex + "\n")
            f.write(e["url"] + "\n")


def write_playlists(channels, settings):
    os.makedirs(C.OUT, exist_ok=True)
    _write_playlist(os.path.join(C.OUT, "AllPlaylist.m3u"), channels, settings)
    selected = [e for e in channels if e["_cat"] == 1]
    _write_playlist(os.path.join(C.OUT, "BanglaPlaylist.m3u"), selected, settings)
    return len(selected)


# ---------------------------------------------------------------- summary
def write_summary(lines):
    text = "\n".join(lines) + "\n"
    print(text, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


def dist_table(channels):
    counts = {}
    for e in channels:
        counts[e["_cat"]] = counts.get(e["_cat"], 0) + 1
    rows = ["| Category | Channels |", "|---|---|"]
    for k in sorted(counts):
        rows.append(f"| {C.CATEGORY_LABEL[k]} | {counts[k]} |")
    rows.append(f"| **Total** | **{len(channels)}** |")
    return rows


def now_iso():
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
