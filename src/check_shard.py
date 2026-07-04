"""CI phase 2 — CHECK one shard (runs in parallel via the Actions matrix).

Usage: python -m src.check_shard <shard_index>
Reads work/shard_<i>.json, checks URLs, writes work/result_<i>.json = {url: bool}.
"""
import asyncio
import json
import os
import sys

from . import config as C
from . import checker


def main():
    if len(sys.argv) < 2:
        print("[error] shard index required")
        sys.exit(1)
    idx = int(sys.argv[1])
    settings = C.load_settings()

    shard_path = os.path.join(C.WORK, f"shard_{idx}.json")
    items = []
    if os.path.exists(shard_path):
        with open(shard_path, encoding="utf-8") as f:
            items = json.load(f)

    url_headers = {u: h for u, h in items}
    if url_headers:
        results = asyncio.run(checker.run_checks(
            url_headers, settings["concurrency"],
            settings["timeout_total"], settings["timeout_connect"],
            settings["hls_verify"], settings["retries"],
        ))
    else:
        results = {}

    out = os.path.join(C.WORK, f"result_{idx}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)

    alive = sum(1 for v in results.values() if v)
    print(f"[shard {idx}] checked {len(url_headers)} -> alive {alive}", flush=True)


if __name__ == "__main__":
    main()
