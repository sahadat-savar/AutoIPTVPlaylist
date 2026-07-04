"""Minimal, fast M3U/M3U8 parser.

Returns a list of channel dicts:
    {
      "name": str,
      "url": str,
      "attrs": {tvg-id, tvg-name, tvg-logo, group-title, ...},
      "extras": [raw #EXTVLCOPT / #KODIPROP lines to preserve headers],
      "source": str,
    }
"""
import re

ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def parse_m3u(text, source=""):
    entries = []
    pending = None

    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue

        if s.startswith("#EXTINF"):
            attrs = dict(ATTR_RE.findall(s))
            name = s.split(",", 1)[1].strip() if "," in s else ""
            pending = {"attrs": attrs, "name": name, "extras": []}

        elif s.startswith("#EXTGRP"):
            grp = s.split(":", 1)[1].strip() if ":" in s else ""
            if pending is not None:
                pending["extras"].append(s)
                if grp:
                    pending["attrs"].setdefault("group-title", grp)

        elif s.startswith(("#EXTVLCOPT", "#KODIPROP", "#EXTHTTP", "#EXT-X")):
            # Stream headers (user-agent / referer / drm) — keep them.
            if pending is not None:
                pending["extras"].append(s)

        elif s.startswith("#"):
            # #EXTM3U and other comments -> ignore
            continue

        else:
            # URL line
            if pending is None:
                pending = {"attrs": {}, "name": s, "extras": []}
            pending["url"] = s
            pending["source"] = source
            entries.append(pending)
            pending = None

    return entries
