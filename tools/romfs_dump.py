"""List / extract the patched RomFS of a base + update NSP pair (sparse base, BKTR patch, compressed storage).

Usage:
    python -I tools/romfs_dump.py --keys prod.keys --titlekeys title.keys BASE.nsp UPDATE.nsp OUTDIR
        [--verify N] [--extract GLOB ...] [--extract-all]

Writes OUTDIR/romfs_list.tsv (size, data offset, path) and OUTDIR/romfs_info.json. --verify N checks N random IVFC
data blocks (and every hash block of the upper levels touched) against the level above, up to the master hash.
Extracted files go to OUTDIR/romfs/.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import random
import shutil
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ncastorage as ns  # noqa: E402
import nxextract as nx  # noqa: E402


def open_program(nsp, keys, titlekeys):
    fh = open(nsp, "rb")
    whole = nx.File(fh, 0, os.path.getsize(nsp))
    entries = nx.parse_pfs0(whole.read)
    tickets = {}
    for name, off, size in entries:
        if name.endswith(".tik"):
            t = whole.read(off, size)
            tickets[t[0x2A0:0x2B0].hex()] = t[0x180:0x190]
    for name, off, size in entries:
        if name.endswith(".nca") and not name.endswith(".cnmt.nca"):
            n = nx.Nca(nx.File(fh, off, size), keys, titlekeys, tickets)
            if n.content_type == 0:
                sec = next(s for s in n.sections if s["fs_type"] == 0)
                return n, sec
    raise SystemExit(f"no program NCA in {nsp}")


def verify_ivfc(info, n, master):
    """Check n random level-6 blocks up the hash chain. Returns (checked, failures)."""
    st, lv = info["ivfc"], info["levels"]
    fails = 0
    rnd = random.Random(1234)
    data_off, data_size, data_log = lv[5]
    nblocks = -(-data_size // (1 << data_log))
    picks = [0, nblocks - 1] + [rnd.randrange(nblocks) for _ in range(max(0, n - 2))]
    for b in picks:
        idx = b
        for level in range(5, 0, -1):
            off, size, log = lv[level]
            bs = 1 << log
            start = idx * bs
            chunk = st.read(off + start, min(bs, size - start))
            chunk += bytes(bs - len(chunk))  # last block hashed zero-padded
            h = hashlib.sha256(chunk).digest()
            poff = lv[level - 1][0]
            expect = st.read(poff + idx * 32, 32)
            if h != expect:
                fails += 1
                break
            idx = (idx * 32) >> lv[level - 1][2]
        else:
            l1off, l1size, _ = lv[0]
            if hashlib.sha256(st.read(l1off, l1size)).digest() != master:
                fails += 1
    return len(picks), fails


_rename_fallback_noted = False


def finish_part(part, dst):
    """Rename a finished <name>.part to <name>. A player's setup (issue #24, setup 0.1.5) stopped on the first .XML of
    the RomFS: after 7,582 .MOD/.AB renames in the same tree, os.replace of AND/CHARACTERS/MASTERFILES/CLOTHPOSESETS.XML
    failed with WinError 17 (ERROR_NOT_SAME_DEVICE) although both names were in one folder on one drive. That is not
    the file system's answer; a security program's file filter that watches some file types can give it. Retry a
    moment (a scanner holding the file), then copy the bytes over and delete the .part, which needs no rename."""
    global _rename_fallback_noted
    for i in range(8):
        try:
            os.replace(part, dst)
            return
        except FileNotFoundError:
            raise
        except OSError as e:
            err = e
            time.sleep(0.25)
    if not _rename_fallback_noted:
        _rename_fallback_noted = True
        print(f"note: renaming {part.name} failed ({err}); copying instead (an antivirus may be watching this folder)",
              flush=True)
    shutil.copyfile(part, dst)
    if dst.stat().st_size != part.stat().st_size:
        raise OSError(f"copy of {part} to {dst} came out short")
    part.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", required=True)
    ap.add_argument("--titlekeys")
    ap.add_argument("base")
    ap.add_argument("update")
    ap.add_argument("outdir")
    ap.add_argument("--verify", type=int, default=64)
    ap.add_argument("--extract", nargs="*", default=[])
    ap.add_argument("--extract-all", action="store_true")
    ap.add_argument("--progress", action="store_true",
                    help="print 'progress <bytes done> <bytes total>' lines (files already complete count as done) for "
                         "the setup (installer/steps.py), at most twice a second")
    a = ap.parse_args()
    keys = nx.load_keys(a.keys)
    tk = nx.load_keys(a.titlekeys) if a.titlekeys else {}
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    base_nca, base_sec = open_program(a.base, keys, tk)
    upd_nca, upd_sec = open_program(a.update, keys, tk)
    romfs, info = ns.patched_romfs(upd_nca, upd_sec, base_nca, base_sec)
    f = ns.fsh_fields(upd_sec["fsh"])
    checked, fails = verify_ivfc(info, a.verify, f["ivfc_master_hash"])
    print(f"IVFC verify: {checked} blocks, {fails} failures")
    if fails:   # a damaged or cut game file, or the wrong base for this update: extracting it would give a broken game
        raise SystemExit(f"IVFC verify failed on {fails} of {checked} blocks: the game files are damaged or do not "
                         "belong together")
    hdr = romfs.read(0, 0x50)
    files = nx.parse_romfs(romfs.read, 0)
    rep = {k: v for k, v in info.items() if k not in ("ivfc", "levels")}
    rep.update(ivfc_blocks_checked=checked, ivfc_failures=fails, romfs_header_size=int.from_bytes(hdr[:8], "little"),
               file_count=len(files), total_bytes=sum(s for _, _, s in files))
    with open(out / "romfs_list.tsv", "w", encoding="utf-8") as lf:
        for p, off, size in files:
            lf.write(f"{size}\t{off}\t{p}\n")
    (out / "romfs_info.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    pats = a.extract
    if a.extract_all or pats:
        # Resumable: a file is written to <name>.part and renamed when complete; complete files are skipped.
        done = skipped = 0
        written = 0
        t0 = time.monotonic()
        total = sum(s for _, _, s in files)
        progress_done, progress_at = 0, 0.0

        def progress(force=False):
            nonlocal progress_at
            now = time.monotonic()
            if a.progress and (force or now - progress_at >= 0.5):
                progress_at = now
                print(f"progress {progress_done} {total}", flush=True)

        for p, off, size in sorted(files, key=lambda x: x[1]):
            if not a.extract_all and not any(fnmatch.fnmatch(p.lower(), g.lower()) for g in pats):
                continue
            dst = out / "romfs" / p.lstrip("/")
            if dst.exists() and dst.stat().st_size == size:
                skipped += 1
                progress_done += size
                progress()
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            part = dst.with_name(dst.name + ".part")
            with open(part, "wb") as w:
                pos = 0
                while pos < size:
                    n = min(16 << 20, size - pos)
                    w.write(romfs.read(off + pos, n))
                    pos += n
                    progress_done += n
                    progress()
            finish_part(part, dst)
            done += 1
            written += size
            if done % 500 == 0:
                rate = written / max(time.monotonic() - t0, 1e-3) / 2**20
                print(f"extracted {done} files ({skipped} already there), {written / 2**30:.1f} GiB, {rate:.0f} MiB/s",
                      flush=True)
        progress(force=True)
        print("extracted", done, "files;", skipped, "were already complete")
        if a.extract_all:   # the runtime mounts the directory only once this marker is there (fs_host.c mount_rom)
            def complete(p, size):
                f = out / "romfs" / p.lstrip("/")
                return f.is_file() and f.stat().st_size == size
            missing = [p for p, _, size in files if not complete(p, size)]
            if missing:
                raise SystemExit(f"{len(missing)} files missing or short, e.g. {missing[0]}: not marking complete")
            marker = out / "romfs.complete"
            marker.write_text(json.dumps({"file_count": len(files), "total_bytes": sum(s for _, _, s in files)}) + "\n")
            print("RomFS complete:", marker)


if __name__ == "__main__":
    main()
