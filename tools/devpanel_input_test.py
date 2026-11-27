"""Drives the dev panel (runtime/gfx/ui/devpanel.cpp) with real window messages and checks the `devpanel:` log lines.

Needs a dev build (mlb_ui.exe, built with -DMLB_DEV_HARNESS) in work/build and takes the game lock. It sends F7, a click
into the Seed field, typed digits, a click on Apply, Drop into scenario 3, Drop marker, Start frame log and F7 again,
and fails unless every expected log line shows up. Usage: python -I tools/devpanel_input_test.py [exe name]
"""
import ctypes, ctypes.wintypes as wt, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = Path('D:/AI/Apps/mlbts-native')
BUILD = MAIN / 'work' / 'build'
LOCK = MAIN / 'work' / 'game.lock'
u32 = ctypes.windll.user32
WM_KEYDOWN, WM_KEYUP, WM_CHAR, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x100, 0x101, 0x102, 0x200, 0x201, 0x202
VK_F7 = 0x76


def find_hwnd(pid):
    found = []
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(h):
            found.append(h)
        return True
    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def post(h, m, w=0, l=0):
    u32.PostMessageW(h, m, w, l)
    time.sleep(0.15)


def click(h, x, y):
    l = (y << 16) | (x & 0xffff)
    post(h, WM_MOUSEMOVE, 0, l)
    post(h, WM_MOUSEMOVE, 0, l)
    post(h, WM_LBUTTONDOWN, 1, l)
    time.sleep(0.1)
    post(h, WM_LBUTTONUP, 0, l)


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else 'mlb_ui.exe'
    log = BUILD / 'devpanel_input.log'
    os.mkdir(LOCK)   # fails if another session runs the game
    proc = None
    try:
        env = dict(os.environ, MLB_EXEFS=str(BUILD / 'game/exefs'), MLB_ROMFS=str(BUILD / 'game/romfs'),
                   MLB_PROFILE=str(BUILD / 'profile'), MLB_DEV_MODE='1', MLB_DEVPANEL_RECTS='1',
                   MLB_HARNESS_HOME='2', MLB_HARNESS_AWAY='1')
        with open(log, 'w') as f:
            proc = subprocess.Popen([str(BUILD / exe)], cwd=BUILD, env=env, stdout=f, stderr=subprocess.STDOUT)
            time.sleep(25)
            h = find_hwnd(proc.pid)
            assert h, 'no game window'
            text = lambda: log.read_text(errors='replace')
            assert 'audout: WASAPI device' in text(), 'no audio output device'
            post(h, WM_KEYDOWN, VK_F7, 1), post(h, WM_KEYUP, VK_F7, 1 | 3 << 30)
            time.sleep(2)
            assert 'menu: dev panel open' in text(), 'F7 did not open the panel'
            rect = lambda n: tuple(map(int, re.search(r"rect '%s' (\d+) (\d+)" % re.escape(n), text()).groups()))
            click(h, *rect('Seed'))
            for c in '4242':
                post(h, WM_CHAR, ord(c), 1)
            click(h, *rect('Apply'))
            click(h, *rect('Scenario 3'))
            click(h, *rect('Drop into scenario'))
            click(h, *rect('Drop marker'))
            click(h, *rect('Start frame log'))
            time.sleep(1)
            post(h, WM_KEYDOWN, VK_F7, 1), post(h, WM_KEYUP, VK_F7, 1 | 3 << 30)
            time.sleep(1)
            t = text()
            want = ["seed 4242 and fixed clock", "apply scenario 'Top 7, 1 out", "harness: marker marker frame",
                    "harness: framelog started", "menu: dev panel closed"]
            bad = [w for w in want if w not in t]
            for line in t.splitlines():
                if 'devpanel:' in line or 'dev panel' in line or 'harness:' in line:
                    print(line)
            print('FAIL: missing ' + repr(bad) if bad else 'PASS: all %d expected lines present' % len(want))
            return 1 if bad else 0
    finally:
        if proc:
            proc.kill()
        os.rmdir(LOCK)


if __name__ == '__main__':
    sys.exit(main())
