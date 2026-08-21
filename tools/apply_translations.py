"""Write the German ``msgstr``s into ``locale/de/LC_MESSAGES/django.po``.

Run after ``makemessages``:

    uv run python manage.py makemessages -l de --no-obsolete --no-wrap
    uv run python tools/apply_translations.py
    uv run python manage.py compilemessages -l de --ignore=.venv

**This replaces hand-editing the `.po`, and the repair script that approach
needs.** Two failures made that worth doing rather than continuing to patch
gettext's output after the fact:

* gettext on Windows reliably emits a *wrapped* ``#:`` reference line — a
  continuation beginning with a space instead of a second ``#:``. ``msgfmt``
  then refuses the whole file and writes no ``.mo`` at all, so the app carries
  on serving the previous catalogue and a session's translations look compiled
  and simply are not there.
* A long ``msgstr`` that gettext breaks across continuation lines is valid
  `.po` and is read by the completeness check as *empty*.

Writing the file here means every reference line is emitted as its own ``#:``
and every ``msgstr`` is a single line however long, so neither trap has anywhere
to occur. ``--no-wrap`` on ``makemessages`` is still passed, because this reads
the file gettext produced.

Anything without a translation is reported and left empty rather than guessed:
an empty ``msgstr`` fails ``config/tests.py`` loudly, and a guess ships silently.
"""

import re
import sys
from pathlib import Path


def _say(text):
    """Print without dying on the console's encoding.

    Windows hands this script a cp1252 stdout, and the strings it reports back
    are German — the first ``→`` or ``ß`` in a message raises
    ``UnicodeEncodeError`` and takes the whole run with it. Losing a character
    from a progress line is nothing; losing the run because of one is the tool
    failing at the only job it has.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from tools.translations_de import SINGULAR  # noqa: E402
from tools.translations_de_pages import JAVASCRIPT, PAGES, PLURALS  # noqa: E402
from tools.translations_de_year import JAVASCRIPT_YEAR, YEAR_END  # noqa: E402

CATALOG = BASE_DIR / "locale" / "de" / "LC_MESSAGES" / "django.po"
JS_CATALOG = BASE_DIR / "locale" / "de" / "LC_MESSAGES" / "djangojs.po"


def _merge():
    """One table from the two files, refusing a key that is in both.

    A duplicate is not harmless: the two would usually differ, and which one
    wins would be whichever file was imported second — a translation that
    changes when somebody reorders two imports.
    """
    tables = {"translations_de.SINGULAR": SINGULAR,
              "translations_de_pages.PAGES": PAGES,
              "translations_de_year.YEAR_END": YEAR_END}
    merged = {}
    seen = {}
    for name, table in tables.items():
        clash = set(table) & set(merged)
        if clash:
            raise SystemExit(
                "these msgids are translated in more than one table, which means one "
                "of them is silently ignored — whichever file was imported second "
                f"wins, so the translation would change if somebody reordered two "
                f"imports. In {name} and {seen[sorted(clash)[0]]}: {sorted(clash)}"
            )
        for key in table:
            seen[key] = name
        merged.update(table)
    return merged


def _quote(text):
    """A `.po` string literal, on one line however long."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _unquote(lines):
    """Join a run of `.po` string literals back into the string they encode."""
    out = []
    for line in lines:
        body = line.strip()
        if not body.startswith('"'):
            continue
        out.append(body[1:-1])
    return "".join(out).replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def main():
    """Both catalogues. ``djangojs`` is separate and easy to forget.

    Its strings are the ones the *browser* says for itself — "that is not a
    time this app can read", "this overlaps another stretch" — which are
    exactly the messages somebody sees most often, because they are the ones a
    typo produces.
    """
    failures = _apply(CATALOG, _merge(), PLURALS)
    if JS_CATALOG.exists():
        failures += _apply(JS_CATALOG, {**JAVASCRIPT, **JAVASCRIPT_YEAR}, {})
    return 1 if failures else 0


def _apply(path, table, plurals):
    """Write one catalogue. Returns how many entries were left untranslated."""
    source = path.read_text(encoding="utf-8")
    blocks = source.split("\n\n")
    written = missing = 0
    unused = set(table) | set(plurals)

    # The header, with gettext's own `#, fuzzy` taken off it. Django stamps that
    # on a freshly created catalogue, and it is not decoration: a fuzzy header
    # is a header gettext *ignores*, so the Plural-Forms line — the thing that
    # decides which of msgstr[0] and msgstr[1] is used — never takes effect.
    # config/tests.py refuses a fuzzy entry anywhere for exactly this reason.
    out_blocks = ["\n".join(
        line for line in blocks[0].splitlines() if line.strip() != "#, fuzzy"
    )]
    for block in blocks[1:]:
        if not block.strip():
            continue
        lines = block.splitlines()

        comments, msgid_lines, plural_lines, section = [], [], [], None
        for line in lines:
            if line.startswith("#"):
                # Each reference on its own `#:` line — see the module docstring.
                if line.startswith("#:") or line.startswith("#,") or line.startswith("#."):
                    comments.append(line)
                section = None
            elif line.startswith("msgid_plural "):
                section = "plural"
                plural_lines.append(line[len("msgid_plural "):])
            elif line.startswith("msgid "):
                section = "id"
                msgid_lines.append(line[len("msgid "):])
            elif line.startswith("msgstr"):
                section = "str"
            elif line.startswith('"'):
                if section == "id":
                    msgid_lines.append(line)
                elif section == "plural":
                    plural_lines.append(line)

        msgid = _unquote(msgid_lines)
        if not msgid:
            out_blocks.append(block)
            continue

        # Drop any fuzzy flag: gettext guesses a translation from a similar
        # msgid and marks it so, and a fuzzy entry is *ignored at runtime* —
        # the string comes out in English while the file looks translated.
        comments = [c for c in comments if c != "#, fuzzy"]

        rebuilt = list(comments)
        if plural_lines:
            plural = _unquote(plural_lines)
            pair = plurals.get(msgid)
            rebuilt.append(f"msgid {_quote(msgid)}")
            rebuilt.append(f"msgid_plural {_quote(plural)}")
            if pair:
                rebuilt.append(f"msgstr[0] {_quote(pair[0])}")
                rebuilt.append(f"msgstr[1] {_quote(pair[1])}")
                written += 1
                unused.discard(msgid)
            else:
                rebuilt.append('msgstr[0] ""')
                rebuilt.append('msgstr[1] ""')
                missing += 1
                _say(f"  no plural translation: {msgid[:70]}")
        else:
            rebuilt.append(f"msgid {_quote(msgid)}")
            translation = table.get(msgid)
            if translation is not None:
                rebuilt.append(f"msgstr {_quote(translation)}")
                written += 1
                unused.discard(msgid)
            else:
                rebuilt.append('msgstr ""')
                missing += 1
                _say(f"  no translation: {msgid[:70]}")

        out_blocks.append("\n".join(rebuilt))

    # `path`, never the module-level CATALOG. Writing the constant here sent
    # the *djangojs* pass's seven entries over the top of django.po and threw
    # away six hundred translations — a one-word slip that produced a file that
    # was still valid, still compiled, and simply almost empty.
    path.write_text("\n\n".join(out_blocks) + "\n", encoding="utf-8")

    _say(f"\n{path.name}: {written} translated, {missing} still missing")
    if unused:
        # Not fatal, but worth saying: a stale entry is one whose msgid has
        # changed, which means the string it was written for is now untranslated
        # somewhere else in this run.
        _say(f"{len(unused)} table entries matched nothing in the catalogue:")
        for key in sorted(unused)[:20]:
            _say(f"  {key[:70]}")
    return missing


if __name__ == "__main__":
    raise SystemExit(main())
