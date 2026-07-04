"""Local all-in-one runner (no sharding) — for testing on your machine.

    pip install -r requirements.txt
    python -m src.collector

GitHub Actions uses the faster sharded path (prepare/check_shard/finalize),
but this single-file run does the same work end-to-end for local checks.
"""
import asyncio
import sys

from . import config as C
from . import pipeline
from . import checker


def main():
    settings = C.load_settings()
    sources = C.load_list("sources.txt")
    if not sources:
        print("[error] config/sources.txt is empty. Add playlist URLs first.")
        sys.exit(1)

    cat = pipeline.build_categorizer()
    print(f"[info] downloading {len(sources)} sources...", flush=True)
    channels = pipeline.collect_channels(sources, cat, settings["user_agent"])
    print(f"[info] {len(channels)} unique channels after URL dedup", flush=True)

    state = pipeline.load_state()
    prev_total = state.get("last_run", {}).get("total", 0)
    dropped = 0
    new_fail = state.get("fail", {})

    if settings["check_dead_links"] and channels:
        url_headers = {e["url"]: pipeline.extract_headers(e, settings["user_agent"])
                       for e in channels}
        print(f"[info] checking {len(url_headers)} URLs...", flush=True)
        results = asyncio.run(checker.run_checks(
            url_headers, settings["concurrency"],
            settings["timeout_total"], settings["timeout_connect"],
            settings["hls_verify"], settings["retries"],
        ))
        alive = {e["url"]: results.get(e["url"], False) for e in channels}
        channels, new_fail, dropped = pipeline.apply_flapping(
            channels, alive, state, settings["fail_threshold"]
        )
        print(f"[info] {len(channels)} kept, {dropped} dropped as dead", flush=True)

    channels = pipeline.sort_channels(channels, settings)
    channels = pipeline.apply_caps(channels, settings)

    ok, msg = pipeline.guard_ok(len(channels), prev_total, settings["min_keep_ratio"])
    if not ok:
        print(f"[guard] ABORT: {msg} — output left unchanged.")
        return

    selected = pipeline.write_playlists(channels, settings)
    if settings["check_dead_links"]:
        state["fail"] = new_fail
        state["last_run"] = {"total": len(channels), "timestamp": pipeline.now_iso()}
        pipeline.save_state(state)

    print(f"[done] All={len(channels)} Selected={selected} dropped={dropped}", flush=True)


if __name__ == "__main__":
    main()
