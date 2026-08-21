"""Check that the committed `.mo` files really are what the `.po` files say.

The `.mo` files are committed because nothing at runtime compiles a `.po` — so a
`.po` edited without recompiling changes nothing at all, and the page keeps
showing the previous translation while the file that was edited looks perfectly
correct. That failure is silent in both directions and has already happened once
in this family of apps.

`config/tests.py` catches it by comparing modification times, which works on a
developer's machine and is meaningless in CI: a fresh clone gives every file the
same timestamp. This compares the *contents* instead — recompile each `.po` into
a temporary file and compare the two catalogs.

Compared as **catalogs, not as bytes**. Two `msgfmt` versions can produce
different `.mo` bytes for the same input (hash table sizing, string ordering),
so a byte comparison would fail on Ubuntu for files compiled correctly with the
gettext that ships with Git for Windows — and a red build saying "your
translations are stale" when they are not is worse than no check at all, because
the fix people reach for is deleting the check.

There is deliberately no repair script beside this one. The German catalog is
*generated* from `tools/translations_de*.py` by `tools/apply_translations.py`,
which writes every reference on its own `#:` line and every `msgstr` on one line
however long — so the two gettext-on-Windows traps that would need repairing (a
wrapped `#:` line that makes `msgfmt` refuse the whole file, and a wrapped
`msgstr` that the completeness check reads as empty) have nowhere to occur. The
remedy printed at the bottom is to regenerate, not to patch.

Needs `msgfmt` on PATH. On Windows it ships with Git:
    $env:PATH = "C:\\Program Files\\Git\\usr\\bin;$env:PATH"
"""

import gettext
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def catalog(path):
    with open(path, "rb") as handle:
        # GNUTranslations parses the .mo the same way gettext does at runtime,
        # which is exactly the question being asked: what will the app see?
        return gettext.GNUTranslations(handle)._catalog


def main():
    catalogs = sorted((ROOT / "locale").rglob("*.po"))
    if not catalogs:
        print("no catalogs found — is this the right directory?")
        return 1

    stale = 0
    for source in catalogs:
        name = source.relative_to(ROOT)
        committed = source.with_suffix(".mo")
        if not committed.exists():
            print(f"{name}: has never been compiled to {committed.name}")
            stale += 1
            continue

        with tempfile.TemporaryDirectory() as tmp:
            fresh = pathlib.Path(tmp) / "fresh.mo"
            result = subprocess.run(
                ["msgfmt", "--check", "--output-file", str(fresh), str(source)],
                capture_output=True, text=True,
            )
            if result.returncode:
                print(f"{name}: msgfmt refuses this file:\n{result.stderr.strip()}")
                stale += 1
                continue
            if catalog(committed) != catalog(fresh):
                print(f"{name}: {committed.name} is not what {source.name} compiles to")
                stale += 1
                continue

        print(f"{name}: up to date")

    if stale:
        print(f"\n{stale} catalog(s) out of date. Run:")
        print("  uv run python manage.py makemessages -l de --no-obsolete --no-wrap")
        print("  uv run python manage.py makemessages -d djangojs -l de --no-obsolete --no-wrap")
        print("  uv run python tools/apply_translations.py")
        print("  uv run python manage.py compilemessages -l de --ignore=.venv")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
