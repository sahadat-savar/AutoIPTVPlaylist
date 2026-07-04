"""CI phase 3 — FINALIZE.

Merges all shard results, applies flapping tolerance + safety guard, sorts,
writes playlists, updates state, and writes the run summary.
"""
import json
import os
import sys

from . import config as C
from . import pipeline


def _load_channels():
    with open(os.path.join(C.WORK, "channels.json"), encoding="utf-8") as f:
        return json.load(f)


def _merge_results():
    alive = {}
    if os.path.isdir(C.WORK):
        for fn in os.listdir(C.WORK):
            if fn.startswith("result_") and fn.endswith(".json"):
                with open(os.path.join(C.WORK, fn), encoding="utf-8") as f:
                    alive.update(json.load(f))
    return alive


def main():
    settings = C.load_settings()
    channels = _load_channels()
    results = _merge_results()

    # Missing result (e.g. a failed shard) -> treat as alive, never nuke silently.
    alive = {e["url"]: results.get(e["url"], True) for e in channels}

    state = pipeline.load_state()
    prev_total = state.get("last_run", {}).get("total", 0)

    kept, new_fail, dropped = pipeline.apply_flapping(
        channels, alive, state, settings["fail_threshold"]
    )
    kept = pipeline.sort_channels(kept, settings)
    kept = pipeline.apply_caps(kept, settings)

    ok, msg = pipeline.guard_ok(len(kept), prev_total, settings["min_keep_ratio"])
    if not ok:
        pipeline.write_summary([
            "## ⚠️ IPTV update ABORTED by safety guard",
            "",
            f"- Reason: {msg}",
            "- A source is probably down. Previous playlists were kept unchanged.",
            f"- Time: {pipeline.now_iso()}",
        ])
        print(f"[guard] ABORT: {msg}")
        # No write, no state update -> previous good output survives.
        sys.exit(0)

    selected = pipeline.write_playlists(kept, settings)

    state["fail"] = new_fail
    state["last_run"] = {"total": len(kept), "timestamp": pipeline.now_iso()}
    pipeline.save_state(state)

    checked = sum(1 for v in results.values())
    still_alive = sum(1 for v in results.values() if v)
    pipeline.write_summary(
        ["## ✅ IPTV playlists updated", "",
         f"- Total in AllPlaylist: **{len(kept)}**",
         f"- Selected (BanglaPlaylist): **{selected}**",
         f"- URLs checked: {checked} (alive {still_alive})",
         f"- Dropped as dead (after {settings['fail_threshold']}x fail): {dropped}",
         f"- Time: {pipeline.now_iso()}", ""]
        + pipeline.dist_table(kept)
    )


if __name__ == "__main__":
    main()
