"""Classify each channel into a priority bucket + compute selected order rank.

Priority:
    1 = Selected (your curated list)   -> ordered by selected.txt line order
    2 = Bangladeshi
    3 = Indian Bangla
    4 = Popular
    5 = Others
"""
import re

QUALITY_RE = re.compile(
    r'\b(4k|uhd|fhd|hd|sd|hevc|h ?265|h ?264|1080p?|720p?|576p?|480p?|360p?)\b', re.I
)
PREFIX_RE = re.compile(r'^\s*[A-Za-z]{2,4}\s*[:|\-]\s*')
NONWORD_RE = re.compile(r'[^\w\u0980-\u09FF]+')  # keep ASCII + Bengali block


def normalize(name: str) -> str:
    s = (name or "").lower()
    s = PREFIX_RE.sub(' ', s)
    s = QUALITY_RE.sub(' ', s)
    s = NONWORD_RE.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def _tokenize(s):
    return normalize(s).split()


def _phrase(hay_tokens, needle_tokens):
    """True if needle appears as a run of WHOLE words in hay_tokens."""
    n = len(needle_tokens)
    if n == 0:
        return False
    for i in range(len(hay_tokens) - n + 1):
        if hay_tokens[i:i + n] == needle_tokens:
            return True
    return False


class Categorizer:
    def __init__(self, selected, bangladesh, indian_bangla, popular, exclude=None):
        self.selected = [_tokenize(x) for x in selected if x.strip()]
        self.bd = [_tokenize(x) for x in bangladesh if x.strip()]
        self.inbn = [_tokenize(x) for x in indian_bangla if x.strip()]
        self.popular = [_tokenize(x) for x in popular if x.strip()]
        self.exclude = [_tokenize(x) for x in (exclude or []) if x.strip()]

    def _hay(self, entry):
        name = entry.get("name", "")
        grp = entry.get("attrs", {}).get("group-title", "")
        return _tokenize(f"{name} {grp}")

    @staticmethod
    def _any(hay, needles):
        return any(_phrase(hay, nd) for nd in needles)

    def classify(self, entry) -> int:
        hay = self._hay(entry)
        tvg_id = entry.get("attrs", {}).get("tvg-id", "").lower()

        if not self._any(hay, self.exclude) and self._any(hay, self.selected):
            return 1
        if tvg_id.endswith(".bd") or self._any(hay, self.bd):
            return 2
        if self._any(hay, self.inbn):
            return 3
        if self._any(hay, self.popular):
            return 4
        return 5

    def selected_rank(self, entry) -> int:
        """Index of the first matching line in selected.txt (for ordering)."""
        hay = self._hay(entry)
        for i, nd in enumerate(self.selected):
            if _phrase(hay, nd):
                return i
        return 10 ** 9
