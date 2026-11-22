"""Updating the port from the launcher, in its own folder: the newest setup on GitHub Releases replaces this one.

The launcher asks GitHub's API for the latest release of the project (one small request, no data about the player sent;
nothing is checked in --selftest). When its version is newer than this setup's, the launcher offers the update:
download() fetches Fastball-<version>-windows.zip, checks it against the SHA-256 GitHub lists for the file, and
unpacks it into <setup folder>/.update/Fastball-<version>/. start_apply() then starts that release's own Python on
apply() and the launcher quits: apply() waits for it to end, moves the new release's files over the old ones (the old
ones go to .update/old-<time>/, and come back if anything fails), and starts the new Fastball.exe with --update
<install folder>, which rebuilds mlb.exe. The game files, saves, settings, logs and launcher.json are never touched:
apply() moves only what a release holds (layout.RELEASE_ENTRIES). The next window removes .update/.

So the port stays in one folder (portable). Setups up to 0.1.5 unpacked each update beside the old setup folder, or
into %LOCALAPPDATA%; they still do that when they update to this one, which then works from the new folder.

Releases are named Fastball-<version>-windows.zip (the launcher Fastball.exe) from 0.2.0; up to 0.1.5 they were
MLBTS-Setup-<version>-windows.zip (MLBTS-Setup.exe), and the updaters of those setups look only for that name and start
only MLBTS-Setup.exe. So a release also carries MLBTS-Setup-<version>-windows.zip, the same folder plus a copy of the
launcher as MLBTS-Setup.exe (tools/make_release.py); the window removes that copy once it runs (gui.py). This updater
takes either name, Fastball's first.

    python -m installer.update --apply NEW --root ROOT [--wait PID] [--dest DIR]
"""
import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import traceback
import urllib.request
import zipfile
from pathlib import Path

from . import layout as layouts

REPO = 'sam110411/fastball'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
ASSET = re.compile(r'^(Fastball|MLBTS-Setup)-(\d+(?:\.\d+)*)-windows\.zip$')   # MLBTS-Setup: up to 0.1.5
HEADERS = {'User-Agent': 'Fastball', 'Accept': 'application/vnd.github+json'}
LAUNCHERS = ('Fastball.exe', 'MLBTS-Setup.exe')   # a setup folder's launcher: this one's, an older one's


class Cancelled(Exception):
    pass


def version_key(v):
    """'0.1.10' -> (0, 1, 10); '-dev' and other suffixes ignored; None when there is no number."""
    m = re.match(r'v?(\d+(?:\.\d+)*)', (v or '').strip())
    return tuple(int(x) for x in m.group(1).split('.')) if m else None


def newer(a, b):
    """Version a is newer than version b (unknown versions are never newer)."""
    ka, kb = version_key(a), version_key(b)
    return ka is not None and kb is not None and ka > kb


def latest(timeout=10):
    """The latest release's setup zip: {version, url, size, sha256 (or None), page}; None when there is none."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        rel = json.load(r)
    assets = [(a, ASSET.match(a.get('name') or '')) for a in rel.get('assets') or []]
    assets.sort(key=lambda am: not (am[1] and am[1].group(1) == 'Fastball'))   # Fastball's zip first
    for a, m in assets:
        if m and a.get('browser_download_url'):
            digest = a.get('digest') or ''
            return {'version': m.group(2), 'url': a['browser_download_url'], 'size': int(a.get('size') or 0),
                    'sha256': digest[7:].lower() if digest.startswith('sha256:') else None,
                    'page': rel.get('html_url') or f'https://github.com/{REPO}/releases'}
    return None


def ready(folder, version):
    """folder holds an unpacked setup of that version (its VERSION is '<version>+<commit>')."""
    try:
        return any((folder / x).is_file() for x in LAUNCHERS) and (folder / 'python' / 'pythonw.exe').is_file() and \
            version_key((folder / 'VERSION').read_text(encoding='utf-8')) == version_key(version)
    except OSError:
        return False


def download(info, setup_root, progress=None, cancel=None):
    """Download, check and unpack info's setup; returns the new setup folder. progress(text, done, total) is called
    as it goes; cancel() returning true stops it (Cancelled). Raises OSError / ValueError on failure."""
    parent = Path(setup_root).resolve() / layouts.UPDATE_DIR
    folder = parent / f'Fastball-{info["version"]}'
    if ready(folder, info['version']):
        return folder
    parent.mkdir(parents=True, exist_ok=True)
    zpath = parent / f'Fastball-{info["version"]}-windows.zip'
    part = zpath.with_name(zpath.name + '.part')
    h = hashlib.sha256()
    req = urllib.request.Request(info['url'], headers={'User-Agent': HEADERS['User-Agent']})
    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as r, \
                open(part, 'wb') as f:
            total = int(r.headers.get('Content-Length') or info.get('size') or 0)
            done = 0
            while True:
                if cancel and cancel():
                    raise Cancelled()
                block = r.read(1 << 20)
                if not block:
                    break
                f.write(block)
                h.update(block)
                done += len(block)
                if progress:
                    progress(f'Downloading version {info["version"]}: {done >> 20} of {total >> 20} MB', done, total)
        if total and done != total:
            raise OSError(f'the download stopped early ({done} of {total} bytes)')
        if info.get('sha256') and h.hexdigest() != info['sha256']:
            raise ValueError('the download is damaged (its checksum does not match GitHub\'s)')
        part.replace(zpath)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    stage = parent / f'.Fastball-{info["version"]}-unpacking'
    shutil.rmtree(stage, ignore_errors=True)
    try:
        with zipfile.ZipFile(zpath) as z:
            names = z.infolist()
            top = {n.filename.split('/', 1)[0] for n in names}
            for n in names:   # never outside the staging folder
                p = Path(n.filename)
                if p.is_absolute() or '..' in p.parts or ':' in n.filename:
                    raise ValueError(f'unexpected path in the download: {n.filename}')
            for i, n in enumerate(names):
                if cancel and cancel():
                    raise Cancelled()
                z.extract(n, stage)
                if progress and i % 64 == 0:
                    progress(f'Unpacking version {info["version"]}', i, len(names))
        src = stage / top.pop() if len(top) == 1 else stage
        if not ready(src, info['version']):
            raise ValueError('the download is not a setup of that version')
        shutil.rmtree(folder, ignore_errors=True)
        src.replace(folder)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    zpath.unlink(missing_ok=True)
    return folder


# ---- the swap ---------------------------------------------------------------------------------------------------------

NO_WINDOW = 0x08000000      # CREATE_NO_WINDOW
DETACHED = 0x00000008       # DETACHED_PROCESS


def start_apply(new, root, dest=None):
    """Starts apply() in the new release's own Python (its code does the swap), waiting for this process to end. The
    caller quits at once: until it has, its Python and the files it holds cannot be replaced."""
    cmd = [str(Path(new) / 'python' / 'pythonw.exe'), '-I', '-m', 'installer.update', '--apply', str(new),
           '--root', str(root), '--wait', str(os.getpid())]
    if dest:
        cmd += ['--dest', str(dest)]
    subprocess.Popen(cmd, cwd=str(new), creationflags=DETACHED | NO_WINDOW, close_fds=True)


def wait_for(pid, timeout_ms=60000):
    if os.name != 'nt' or not pid:
        return
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x00100000, False, int(pid))   # SYNCHRONIZE
    if h:
        k.WaitForSingleObject(h, timeout_ms)
        k.CloseHandle(h)


def retry(fn, tries=40):
    """fn, again for up to 10 s while Windows refuses it: a virus scanner or Explorer may hold a file for a moment."""
    for i in range(tries):
        try:
            return fn()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.25)


def apply(new, root, log=print):
    """Moves the release in new over the one in root. The replaced files go to root/.update/old-<time>/; on a failure
    they are put back and the error is raised."""
    new, root = Path(new).resolve(), Path(root).resolve()
    trash = root / layouts.UPDATE_DIR / time.strftime('old-%Y%m%d-%H%M%S')
    trash.mkdir(parents=True, exist_ok=True)
    names = [n for n in layouts.RELEASE_ENTRIES if (new / n).exists()]
    done = []   # (name, an old one was moved to trash)
    try:
        for name in names:
            src, dst = new / name, root / name
            had = dst.exists()
            if had:
                retry(lambda: dst.replace(trash / name))
            done.append((name, had))
            if name == 'python':   # this process runs from new/python: a copy, not a move
                shutil.copytree(src, dst)
            else:
                retry(lambda: src.replace(dst))
            log(f'update: {name} replaced')
        for name in layouts.LEGACY_ENTRIES:   # an older release's file this one has not got (the old launcher)
            if (root / name).exists() and not (new / name).exists():
                retry(lambda: (root / name).replace(trash / name))
                done.append((name, True))
                log(f'update: {name} removed')
    except BaseException:
        log('update: failed, putting the old files back\n' + traceback.format_exc())
        for name, had in reversed(done):
            dst = root / name
            if dst.is_dir():
                shutil.rmtree(dst, ignore_errors=True)
            elif dst.exists():
                dst.unlink()
            if had:
                retry(lambda: (trash / name).replace(dst))
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m installer.update')
    ap.add_argument('--apply', type=Path, required=True, help='the unpacked new release')
    ap.add_argument('--root', type=Path, required=True, help='the setup folder to update')
    ap.add_argument('--wait', type=int, help='the launcher process to wait for')
    ap.add_argument('--dest', type=Path, help='the install folder, rebuilt by the new launcher')
    a = ap.parse_args(argv)
    logs = a.root / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    with open(logs / time.strftime('update-%Y%m%d-%H%M%S.log'), 'w', encoding='utf-8') as f:
        def log(text):
            f.write(text + '\n')
            f.flush()
        wait_for(a.wait)
        ok = True
        try:
            apply(a.apply, a.root, log)
        except BaseException as e:   # noqa: BLE001 (told to the player; the old setup still works)
            ok = False
            if os.name == 'nt':
                ctypes.windll.user32.MessageBoxW(
                    None, f'The update could not be installed: {e}\n\nThe previous version is still in place. The '
                    f'details are in {f.name}.', 'Fastball - update', 0x10)
        launcher = next((a.root / x for x in LAUNCHERS if (a.root / x).is_file()), a.root / LAUNCHERS[0])
        args = [str(launcher)] + (['--update', str(a.dest)] if ok and a.dest else [])
        log('update: starting ' + ' '.join(args))
        subprocess.Popen(args, cwd=str(a.root), close_fds=True)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
