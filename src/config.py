"""Shared paths, config loaders, constants."""
import os
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config")
OUT = os.path.join(ROOT, "output")
WORK = os.path.join(ROOT, "work")           # intermediate artifacts (gitignored)
STATE_DIR = os.path.join(ROOT, "state")
STATE_FILE = os.path.join(STATE_DIR, "state.json")

CATEGORY_LABEL = {1: "Selected", 2: "Bangladesh", 3: "Indian Bangla",
                  4: "Popular", 5: "Others"}

_DEFAULTS = {
    "concurrency": 250,
    "timeout_total": 8,
    "timeout_connect": 5,
    "retries": 1,               # extra attempts on timeout/connection errors
    "check_dead_links": True,
    "hls_verify": True,
    "set_group_by_category": False,   # keep each channel's ORIGINAL group-title
    "sort_within_category": True,
    "max_others": 40000,
    "max_per_category": 0,
    "user_agent": "VLC/3.0.20 (Linux; VLC 3.0.20)",
    # sharding / stability
    "shards": 10,               # parallel check jobs in GitHub Actions
    "fail_threshold": 3,        # drop a channel only after N consecutive fails
    "min_keep_ratio": 0.5,      # abort commit if kept < ratio * previous total
}


def load_list(name):
    path = os.path.join(CFG, name)
    items = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    items.append(line)
    return items


def load_settings():
    d = {}
    p = os.path.join(CFG, "settings.yaml")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
    for k, v in _DEFAULTS.items():
        d.setdefault(k, v)
    return d
