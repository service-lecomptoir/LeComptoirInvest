"""Turn translations into a plan `comments_io.py apply` can really apply.

    python scripts/comments_plan.py extracted.json translations.json plan.json

`extracted.json` is what `comments_io.py extract` wrote: `{file: [text, ...]}`.
`translations.json` holds the English, in the SAME order: `{file: [text, ...]}`.
The plan pairs them up: `{file: [[before, after], ...]}`.

🔴 WHY THIS EXISTS RATHER THAN A HAND-WRITTEN PLAN. `apply` replaces on an EXACT match
and, when one block of a file is not found, writes NOTHING for that file -- rightly, a
half-translated file is worse than an untouched one. But the extractor can hand back a
block whose line endings are not the file's (a `\\r\\n` where the file holds `\\n`), and the
pair then never matches. A plan written by hand fails the same way, silently, on a file
somebody believed was translated. So each « before » is CHECKED against the file here, in
both endings, and the « after » is given the endings that matched.

It also refuses a translation that still reads as French, and one that drops a `« »`
quote the original carried: those are the two mistakes a bulk pass makes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_FRENCH = re.compile(
    r"\b(le|la|les|des|une|un|qui|que|pour|dans|est|sont|avec|sur|par|pas|plus|donc"
    r"|ainsi|chaque|aucun|cette|ce|son|sa|ses|nous|aux|du|sans|mais|leur|elle|il)\b",
    re.IGNORECASE,
)


def _still_french(text: str) -> bool:
    """Three function words outside any « » quote: still a French sentence."""
    outside = re.sub(r"«[^»]*»", " ", text)
    return len(_FRENCH.findall(outside)) >= 3


def build(extracted: dict, translations: dict, root: Path) -> dict:
    plan: dict[str, list[list[str]]] = {}
    problems: list[str] = []
    for path, befores in extracted.items():
        afters = translations.get(path)
        if afters is None:
            continue
        if len(afters) != len(befores):
            problems.append(f"{path}: {len(befores)} block(s) extracted, {len(afters)} translated")
            continue
        source = (root / path).read_text(encoding="utf-8")
        pairs = []
        for index, (before, after) in enumerate(zip(befores, afters, strict=True)):
            candidates = [before, before.replace("\r\n", "\n"), before.replace("\n", "\r\n")]
            found = next((c for c in candidates if c in source), None)
            if found is None:
                problems.append(f"{path}[{index}]: this block is not in the file as extracted")
                continue
            if "\r\n" in found:
                after = after.replace("\r\n", "\n").replace("\n", "\r\n")
            else:
                after = after.replace("\r\n", "\n")
            if _still_french(after):
                problems.append(f"{path}[{index}]: the translation still reads as French")
                continue
            quoted = len(re.findall(r"«[^»]*»", before))
            if quoted and len(re.findall(r"«[^»]*»", after)) < quoted:
                problems.append(f"{path}[{index}]: a « » quote of the original is missing")
                continue
            pairs.append([found, after])
        if len(pairs) != len(befores):
            # `apply` would write nothing for this file anyway: say so here, once.
            problems.append(f"{path}: NOT PLANNED, {len(befores) - len(pairs)} block(s) refused")
            continue
        plan[path] = pairs
    return {"plan": plan, "problems": problems}


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    # The extractor's keys are relative to `backend/`, where it is run from.
    root = Path(__file__).resolve().parents[1]
    extracted = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    translations = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    built = build(extracted, translations, root)
    Path(sys.argv[3]).write_text(
        json.dumps(built["plan"], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    blocks = sum(len(v) for v in built["plan"].values())
    print(f"{len(built['plan'])} file(s), {blocks} block(s) planned")
    for problem in built["problems"]:
        print("  REFUSED:", problem)
    return 1 if built["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
