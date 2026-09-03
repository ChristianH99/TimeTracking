"""Rejoin a ``#:`` reference line that gettext wrapped onto a continuation.

Run **between** ``makemessages`` and ``apply_translations``:

    uv run python manage.py makemessages -l de --no-obsolete --no-wrap
    uv run python tools/unwrap_references.py
    uv run python tools/apply_translations.py

``tools/apply_translations.py`` says that writing the catalogue programmatically
leaves the wrap trap nowhere to occur, and for the file it writes that is true.
It is not true one step earlier, and that gap is why this exists.

``xgettext`` wraps a long list of source references at a fixed width whatever
``--no-wrap`` says — that option governs ``msgstr``, not the comment lines — and
the continuation begins with a space instead of a second ``#:``. The next tool
in the chain is ``msgattrib``, which ``makemessages`` itself runs to honour
``--no-obsolete``, and it refuses the file:

    django.po:2180: keyword "roster" unknown
    msgattrib: found 5 fatal errors

At that point the merge has already been written, so nothing is lost — but the
run has failed, the message points at a template name rather than at the real
fault, and ``apply_translations`` afterwards reports every new string as
"matched nothing in the catalogue". It cost an hour once; it costs a line of
the workflow now.

The repair is that gettext accepts any number of ``#:`` lines for one entry, so
a continuation only needs the prefix it was written without.
"""

import io
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CATALOGS = [
    BASE_DIR / "locale" / "de" / "LC_MESSAGES" / "django.po",
    BASE_DIR / "locale" / "de" / "LC_MESSAGES" / "djangojs.po",
]


def _is_wrapped_reference(line):
    """A continuation of a ``#:`` list, rather than an indented anything else.

    Deliberately narrow: it must begin with a space and then a relative path —
    ``./`` on a POSIX box, ``.\\`` on Windows, which is what gettext writes
    here. A ``msgstr`` continuation begins with a quote and a comment with a
    hash, so neither can be caught by this.
    """
    return line[:2] == " ." and (line[2:3] in ("/", "\\"))


def repair(path):
    """Returns how many lines were repaired. Leaves the file's newlines alone."""
    if not path.exists():
        return 0
    raw = io.open(path, encoding="utf-8", newline="").read()
    newline = "\r\n" if "\r\n" in raw else "\n"
    out, fixed = [], 0
    for line in raw.split(newline):
        if _is_wrapped_reference(line):
            out.append("#:" + line)
            fixed += 1
        else:
            out.append(line)
    if fixed:
        io.open(path, "w", encoding="utf-8", newline="").write(newline.join(out))
    return fixed


def main():
    total = 0
    for path in CATALOGS:
        fixed = repair(path)
        total += fixed
        print(f"{path.name}: {fixed} wrapped reference line(s) rejoined")
    return 0 if total >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
