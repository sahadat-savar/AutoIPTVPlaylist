"""CI phase 1 — PREPARE.

Downloads sources, parses, dedups by URL, classifies, then splits the unique
URLs into N shard files for parallel checking. Writes:
    work/channels.json   -> all channels (metadata) for finalize
    work/shard_<i>.json  -> [[url, headers], ...] for each check job
    work/shards.txt      -> JSON array of shard indices (for the Actions matrix)
"""
import json
import math
import os
import sys

from . import config as C
from . import pipeline


def main():
    settings = C.load_settings()
    sources = C.load_list("sources.txt")
    if not sources:
        print("[error] config/sources.txt is empty.")
        sys.exit(1)

    os.makedirs(C.WORK, exist_ok=True)
    cat = pipeline.build_categorizer()

    print(f"[prepare] downloading {len(sources)} sources...", flush=True)
    channels = pipeline.collect_channels(sources, cat, settings["user_agent"])
    print(f"[prepare] {len(channels)} unique channels after URL dedup", flush=True)

    with open(os.path.join(C.WORK, "channels.json"), "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False)

    n = max(1, int(settings["shards"]))
    ua = settings["user_agent"]
    urls = [[e["url"], pipeline.extract_headers(e, ua)] for e in channels]

    size = math.ceil(len(urls) / n) if urls else 0
    for i in range(n):
        shard = urls[i * size:(i + 1) * size] if size else []
        with open(os.path.join(C.WORK, f"shard_{i}.json"), "w", encoding="utf-8") as f:
            json.dump(shard, f, ensure_ascii=False)

    with open(os.path.join(C.WORK, "shards.txt"), "w", encoding="utf-8") as f:
        f.write(json.dumps(list(range(n))))

    print(f"[prepare] split into {n} shards (~{size} URLs each)", flush=True)


if __name__ == "__main__":
    main()
