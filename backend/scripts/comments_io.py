"""Extract the FRENCH comments and docstrings of Python files, then feed their
translations back in.

Rewriting whole files to translate their comments pays, every single time, for all
the code around them. Over several hundred files that cost is what makes the job
untractable, not the translating. These three commands move comments only:

    python scripts/comments_io.py count app
    python scripts/comments_io.py extract app/services/payment_service.py [...]
    python scripts/comments_io.py apply plan.json

`extract` writes a JSON `{file: [text, ...]}`; `apply` reads a JSON
`{file: [[before, after], ...]}` and replaces on an EXACT match. A match that cannot
be found is reported and NOTHING is written for that file: applying half a
translation leaves a file half English, half French, that nobody spots afterwards.

The net remains `scripts/check_comments_only.py`, which compares ASTs: here we
replace strings, and a comment's text can, with bad luck, appear somewhere else.

Counterpart of the frontend tool `frontend/scripts/comments_io.mjs`, which does the
same job on TypeScript with the TS parser.
"""

import json
import re
import sys
import tokenize
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Two hints that a comment is French: the accents, and a density of function words an
# English comment never reaches. Neither alone is enough (an English comment quoting a
# French UI label has accents; a two-word French comment has no function words).
_FR = re.compile(
    r"\b(le|la|les|des|une|un|qui|que|pour|dans|est|sont|avec|sur|par|pas|plus|donc"
    r"|ainsi|chaque|aucun|cette|ce|son|sa|ses|nous|au|aux|du|de|sans|mais|leur|elle|il)\b",
    re.IGNORECASE,
)


def _is_french(text: str) -> bool:
    return len(_FR.findall(text)) >= 3


def _read(path: Path) -> str:
    return open(path, encoding="utf-8", newline="").read()


def blocks(path: Path) -> list[str]:
    """Comments and docstrings of the file, in order.

    Consecutive `#` lines at the same indentation form ONE block: they are a
    paragraph, and translating them line by line produces sentences that no longer
    join up. Docstrings are taken whole, quotes included, so that `apply` replaces
    an unambiguous string.
    """
    source = _read(path).replace("\r\n", "\n")
    found: list[str] = []
    courant: list[str] = []
    indent = None
    ligne_precedente = -2

    with open(path, "rb") as flux:
        try:
            jetons = list(tokenize.tokenize(flux.readline))
        except (tokenize.TokenError, SyntaxError):
            return []

    def _vider() -> None:
        nonlocal courant, indent
        if courant:
            found.append("\n".join(courant))
            courant = []
            indent = None

    lignes = source.split("\n")
    for jeton in jetons:
        if jeton.type == tokenize.COMMENT:
            debut = jeton.start[0]
            marge = jeton.start[1]
            code_avant = lignes[debut - 1][:marge].strip()
            if code_avant:  # trailing comment: on its own, never merged
                _vider()
                found.append(jeton.string)
                ligne_precedente = -2
                continue
            if debut != ligne_precedente + 1 or marge != indent:
                _vider()
                indent = marge
            courant.append(" " * marge + jeton.string if not courant else jeton.string)
            # The first line of a block keeps its indentation so that `apply` matches
            # the file; the following ones are re-indented the same way below.
            if len(courant) > 1:
                courant[-1] = " " * marge + jeton.string
            ligne_precedente = debut
        elif jeton.type == tokenize.STRING and jeton.line.strip().startswith(
            ('"""', "'''", 'r"""', "f'''")
        ):
            _vider()
            found.append(jeton.string)
            ligne_precedente = -2
        elif jeton.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            _vider()
            ligne_precedente = -2
    _vider()
    return [b for b in found if _is_french(b)]


def _fichiers(cibles: list[str]) -> list[Path]:
    out: list[Path] = []
    for cible in cibles:
        chemin = Path(cible)
        if chemin.is_dir():
            out += [
                p
                for p in sorted(chemin.rglob("*.py"))
                if "__pycache__" not in p.parts and ".venv" not in p.parts
            ]
        elif chemin.suffix == ".py":
            out.append(chemin)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    commande, args = argv[1], argv[2:]

    if commande == "count":
        lignes_total = 0
        rangs = []
        for chemin in _fichiers(args or ["app"]):
            trouves = blocks(chemin)
            if not trouves:
                continue
            n = sum(b.count("\n") + 1 for b in trouves)
            rangs.append((n, chemin.as_posix()))
            lignes_total += n
        rangs.sort(reverse=True)
        print(f"{len(rangs)} fichier(s), {lignes_total} ligne(s) de commentaires francais")
        for n, chemin in rangs[:20]:
            print(f"{n:5} {chemin}")
        return 0

    if commande == "extract":
        sortie = {}
        for chemin in _fichiers(args):
            trouves = blocks(chemin)
            if trouves:
                sortie[chemin.as_posix()] = trouves
        print(json.dumps(sortie, ensure_ascii=False, indent=1))
        return 0

    if commande == "apply":
        plan = json.loads(open(args[0], encoding="utf-8").read())
        appliques = 0
        manques = []
        for chemin_str, paires in plan.items():
            chemin = Path(chemin_str)
            source = _read(chemin)
            sep = "\r\n" if "\r\n" in source else "\n"
            modifie = source
            locaux = []
            for avant, apres in paires:
                a = avant.replace("\n", sep)
                b = apres.replace("\n", sep)
                if a not in modifie:
                    locaux.append(avant.split("\n")[0][:70])
                    continue
                modifie = modifie.replace(a, b, 1)
                appliques += 1
            if locaux:
                manques.append((chemin_str, locaux))
                continue  # nothing written: never half a translation
            if modifie != source:
                open(chemin, "w", encoding="utf-8", newline="").write(modifie)
        for chemin_str, locaux in manques:
            print(f"INTROUVABLE dans {chemin_str} :")
            for texte in locaux:
                print(f"    {texte}")
        print(f"{appliques} bloc(s) traduit(s).")
        return 1 if manques else 0

    print(f"Commande inconnue : {commande}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
