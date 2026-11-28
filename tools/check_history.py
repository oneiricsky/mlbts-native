"""Run check_content on every file of every commit given, not just the newest tree.

    python -I tools/check_history.py REV-LIST-ARGUMENTS
    python -I tools/check_history.py b9c607e..main
    python -I tools/check_history.py --no-walk COMMIT [COMMIT ...]

A file added in one commit and removed in a later one is still published with the history, so each tree is checked.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_content  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def git(*args, stdin=None):
    return subprocess.run(['git', '-C', str(ROOT), *args], input=stdin, capture_output=True, check=True).stdout


def blobs(shas):
    out = git('cat-file', '--batch', stdin=''.join(s + '\n' for s in shas).encode())
    pos = 0
    for sha in shas:
        end = out.index(b'\n', pos)
        size = int(out[pos:end].split()[2])
        yield sha, out[end + 1:end + 1 + size]
        pos = end + size + 2


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    commits = git('rev-list', *sys.argv[1:]).decode().split()
    seen = {}  # (path, blob) -> first commit listed that holds it
    for commit in commits:
        for entry in filter(None, git('ls-tree', '-r', '-z', '--full-tree', commit).split(b'\0')):
            meta, path = entry.split(b'\t', 1)
            _, kind, sha = meta.decode().split()
            if kind == 'blob':
                seen.setdefault((path.decode(), sha), commit)
    data = dict(blobs(sorted({sha for _, sha in seen})))
    bad = []
    for (path, sha), commit in seen.items():
        bad += ['%s %s: %s' % (commit[:7], path, p) for p in check_content.problems(path, data[sha])]
    for commit in commits:
        message = git('log', '-1', '--format=%B', commit)
        if check_content.KEY_LINE.search(message) or any(m.encode() in message for m in check_content.MARKERS):
            bad.append('%s commit message: key line or generated-code marker' % commit[:7])
    for line in bad:
        print('FAIL', line)
    print('%d commits, %d file versions, %d problems: %s'
          % (len(commits), len(seen), len(bad), 'FAIL' if bad else 'PASS'))
    return 1 if bad or not commits else 0


if __name__ == '__main__':
    sys.exit(main())
