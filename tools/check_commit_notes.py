"""Check that docs/reports/2026-11-27-commit-notes.md holds every old commit body.

Needs the old history. Run: python -I tools/check_commit_notes.py OLD_REF [notes.md]
for example: python -I tools/check_commit_notes.py backup/pre-squash-20261127
"""
import difflib
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
UPSTREAM = "b9c607e"  # upstream's last merged commit; its hashes never change
NOTES = ROOT / "docs/reports/2026-11-27-commit-notes.md"
HASH = re.compile(r"(?<![0-9A-Za-z_])[0-9a-f]{7,40}(?![0-9A-Za-z_])")


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def old_commits(ref):
    raw = git("log", "--reverse", "--topo-order", "--date=short", "--format=%x01%ad %s%x02%b", UPSTREAM + ".." + ref)
    for record in raw.split("\x01")[1:]:
        title, body = record.split("\x02", 1)
        lines = [l for l in body.splitlines() if not l.startswith("Co-Authored-By")]
        yield title, "\n".join(lines).strip()


def sections(text):
    return re.findall(r"^## (.+?)\n\n~~~text\n(.*?)\n~~~$", text, re.M | re.S)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ref = sys.argv[1]
    path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else NOTES
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    known = git("rev-list", ref).split()
    upstream = set(git("rev-list", UPSTREAM).split())
    commits = list(old_commits(ref))
    with_body = [c for c in commits if c[1]]
    found = sections(text)
    errors = []
    if len(found) != len(with_body):
        errors.append("sections %d, commits with a body %d" % (len(found), len(with_body)))

    old_words = new_words = replaced = 0
    for (title, body), (head, kept) in zip(with_body, found):
        if title != head:
            errors.append("title differs: %r / %r" % (title, head))
            continue
        a, b = body.split(), kept.split()
        old_words += len(a)
        new_words += len(b)
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if op == "equal":
                continue
            # The only allowed change: a hash gained a date and subject. The owner's hashes go; upstream's stay.
            hashes = [h for w in a[i1:i2] for h in HASH.findall(w)
                      if any(k.startswith(h) for k in known)]
            new = " ".join(b[j1:j2])
            wrong = [h for h in hashes if (h in new) != any(c.startswith(h) and c in upstream for c in known)]
            if op != "replace" or len(hashes) < i2 - i1 or wrong:
                errors.append("%s: %s %r -> %r" % (title, op, a[i1:i2], b[j1:j2]))
            else:
                replaced += len(hashes)

    lines = set(text.splitlines())
    listed = [t for t, body in commits if not body and "- " + t in lines]
    for title, body in commits:
        if not body and title not in listed:
            errors.append("subject missing: %s" % title)

    total = len(text.split())
    print("old commits            %d" % len(commits))
    print("  without a body       %d" % (len(commits) - len(with_body)))
    print("  with a body          %d" % len(with_body))
    print("sections in the file   %d" % len(found))
    print("bodyless subjects listed %d" % len(listed))
    print("words in the old bodies          %d" % old_words)
    print("added around %2d hashes            %d" % (replaced, new_words - old_words))
    print("words in the file's bodies       %d" % new_words)
    print("everything else in the file      %d" % (total - new_words))
    print("words in the whole file          %d" % total)
    for e in errors:
        print("FAIL", e)
    print("FAIL" if errors else "PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
