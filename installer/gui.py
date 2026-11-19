"""Fastball's window, setup and launcher: python -m installer.gui (Fastball.exe starts it with the bundled Python).

One window, three screens:
- the install form: the base game and update NSPs, prod.keys and the install folder, filled in from what the setup
  finds by itself (detect.py: the emulators' key and game folders, Downloads, Desktop, ...), and the options;
- the progress screen: the steps of the command-line setup (installer/cli.py, run as a child process; its JSON events
  drive the screen), a progress bar, Cancel;
- the launcher: Play, and Update when this setup is newer than the install, Import Ryujinx save, Open folder. It also
  asks GitHub for a newer release (update.py) and offers "Download and update": the new release is downloaded and
  swapped in over this one in its own folder, then started with --update <install folder>, which goes straight to the
  rebuild.

One executable: once the game is built, Fastball.exe starts it at once, without the window (straight_to_game). The
window opens instead when there is something to do (no install yet, an install to finish or rebuild, a newer release
on GitHub: asked at most once a day, in 3 s), with --menu, or with Shift held while it starts.

Portable: the game goes into MLBTS\\ inside the setup folder by default (the folder RecompLauncher uses too), and the
last install folder and the file paths are remembered in launcher.json in the setup folder (paths only, never the keys'
contents). Setups up to 0.1.5 kept that in %LOCALAPPDATA%\\MLBTS-Native\\setup.json: it is read once and removed.

Command line (Fastball.exe passes its arguments on):
  --menu            open the window even when the game is ready
  --dest DIR        the install to play or manage (default: the last one)
  --update DIR      rebuild that install with this setup (the updater starts the new setup with it)
  --selftest        build every screen and close (tests; no network)
Every other argument goes to mlb.exe when the game starts: Fastball.exe --fullscreen --fps-limit 120 (mlb.exe
--help lists them). The setup without a window is python\\python.exe -m installer (installer/cli.py).
"""
import ctypes
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import detect
from . import layout as layouts
from . import update
from .steps import STATE, state_file

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = layouts.find(ROOT)
SETTINGS = LAYOUT.state
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
GIB = 1 << 30
UPDATE_EVERY = 20 * 3600   # straight_to_game asks GitHub for a newer release at most this often (seconds)
# The window's own arguments; every other one is the game's (mlb.exe)
OWN_FLAGS, OWN_OPTIONS = ('--menu', '--selftest'), ('--update', '--dest')


def game_args(argv=None):
    """The arguments for mlb.exe: what the window was started with, without its own."""
    argv, out, i = list(sys.argv[1:] if argv is None else argv), [], 0
    while i < len(argv):
        if argv[i] in OWN_OPTIONS:
            i += 2
            continue
        if argv[i] not in OWN_FLAGS:
            out.append(argv[i])
        i += 1
    return out
# The command line, from any working directory and with -I: runpy finds the package beside this one
RUN_CLI = ("import sys, runpy; sys.path.insert(0, sys.argv.pop(1)); sys.argv[0] = 'installer'; "
           "runpy.run_module('installer', run_name='__main__', alter_sys=True)")

# The window's colours: a dark theme, a blue accent for the main action, the baseball's stitch red as the brand line
BG, HEADER_BG, SURFACE, SURFACE_HI, BORDER = '#111923', '#0a1017', '#1a2532', '#243345', '#2c3b4f'
TEXT, MUTED, DIM, HEADER_FG = '#e6edf5', '#8d9db2', '#5c6b7e', '#ffffff'
ACCENT, ACCENT_HI, ACCENT_LO, STITCH = '#2f81f7', '#4c95fa', '#1f69d6', '#d6303a'
OK, BAD, WARN = '#46c068', '#f0645d', '#e3b341'
SEMI = 'Segoe UI Semibold'


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_settings():
    if SETTINGS.is_file() or LAYOUT.dev or '--selftest' in sys.argv:
        return read_json(SETTINGS)
    # From a setup up to 0.1.5: its memory moves into this folder, and nothing stays in %LOCALAPPDATA%
    old = layouts.legacy_settings()
    data = {k: v for k, v in read_json(old).items() if k in ('base', 'update', 'keys', 'dest')}
    if data:
        save_settings(data)
        if SETTINGS.is_file():
            try:
                old.unlink()
                old.parent.rmdir()   # only when empty: an older updater's setups\ folder stays
            except OSError:
                pass
    return data


def save_settings(data):
    if '--selftest' in sys.argv:   # the release check's tour must leave the player's (and the developer's) memory alone
        return
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, indent=1), encoding='utf-8')
    except OSError:
        pass


def install_state(dest):
    """The install's fastball-install.json, or None when dest holds no finished install."""
    try:
        p = Path(dest)
        if not (p / 'mlb.exe').is_file():
            return None
        return json.loads(state_file(p).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None


def default_dest():
    """MLBTS inside the setup folder (portable), unless its disk lacks room for the game: then a folder on the disk
    with the most free space."""
    d = LAYOUT.default_dest()
    if LAYOUT.dev or (d / 'game' / 'romfs.complete').is_file() or detect.free_bytes(ROOT) >= 39 * GIB:
        return d
    return detect.default_dest()


def shift_held():
    try:
        return bool(os.name == 'nt' and ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)   # VK_SHIFT
    except (AttributeError, OSError):
        return False


def start_game(dest, args=()):
    """mlb.exe of dest, with the game's arguments; False (and why) when it could not start."""
    try:
        subprocess.Popen([str(Path(dest) / 'mlb.exe'), *args], cwd=dest,
                         creationflags=subprocess.DETACHED_PROCESS | NO_WINDOW, close_fds=True)
        return True, None
    except OSError as e:
        return False, e


def newer_release(settings):
    """GitHub's latest release when it is newer than this setup, at most one request every UPDATE_EVERY seconds (the
    answer is kept in launcher.json); None offline or when there is none."""
    last = settings.get('update_check') or {}
    if time.time() - float(last.get('time') or 0) >= UPDATE_EVERY:
        try:
            last = {'time': time.time(), 'info': update.latest(timeout=3)}
        except Exception:   # noqa: BLE001 (offline, GitHub down, a rate limit: the game starts anyway)
            last = {'time': time.time(), 'info': last.get('info')}
        settings['update_check'] = last
        save_settings(settings)
    info = last.get('info')
    return info if info and update.newer(info.get('version'), LAYOUT.release) else None


def straight_to_game():
    """The game starts without the window when its install is ready and nothing waits for the player. True when it
    started."""
    if any(a in sys.argv for a in ('--menu', '--selftest', '--update')) or shift_held():
        return False
    settings = load_settings()
    dest = arg_after('--dest') or settings.get('dest')
    state = install_state(dest) if dest else None
    if not state:
        return False
    installed = state.get('release')
    if setup_newer_than(installed) or update.newer(installed, LAYOUT.release) or newer_release(settings):
        return False   # a rebuild, an older setup, an update on GitHub: the window says so
    return start_game(dest, game_args())[0]


def arg_after(flag):
    """The command-line value after flag, or None."""
    try:
        i = sys.argv.index(flag)
        return sys.argv[i + 1]
    except (ValueError, IndexError):
        return None


def setup_newer_than(installed):
    """This setup should rebuild an install of that release: it is newer, or the install's release is not known."""
    return update.version_key(installed) is None or update.newer(LAYOUT.release, installed)


def where(path):
    """A short phrase for where a file was found."""
    s = str(path).lower()
    for name in detect.EMULATORS:
        if f'\\{name.lower()}\\' in s:
            return f'Found in {name}\'s folder'
    return f'Found in {Path(path).parent}'


class App:
    def __init__(self, selftest=False):
        if os.name == 'nt':
            try:   # sharp text at 125% and 150% display scale; Tk sizes its fonts from the DPI it then sees
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                pass
        self.root = tk.Tk()
        self.root.title('Fastball - MLB The Show 26 for PC')
        # Tk sizes fonts by the display scale but not pixel sizes: px() scales those (1.5 at 150%)
        self.scale = max(1.0, self.root.winfo_fpixels('1i') / 96)
        w, h = self.px(820), min(self.px(700), self.root.winfo_screenheight() - self.px(80))
        self.root.minsize(self.px(720), min(self.px(600), h))
        self.root.geometry(f'{w}x{h}')
        self.logo = None
        for icon in (ROOT / 'installer' / 'icon.png', ROOT / 'runtime' / 'mlb' / 'mlb.png'):
            if icon.is_file():
                try:
                    image = tk.PhotoImage(file=str(icon))
                    self.root.iconphoto(True, image)
                    self.logo = image.subsample(max(1, round(image.width() / self.px(34))))
                except tk.TclError:
                    pass
                break
        self.style()
        self.title_bar()
        self.settings = {} if selftest else load_settings()
        self.events = queue.Queue()
        self.proc = None
        self.body = None
        self.header()
        self.selftest = selftest
        self.download_cancel = None   # a threading.Event while an update downloads
        self.update_checked = False
        dest = arg_after('--dest') or self.settings.get('dest')
        update_dest = arg_after('--update')   # started by the previous setup's updater
        if update_dest and install_state(update_dest):
            dest = update_dest
        if dest and install_state(dest):
            self.show_launcher(Path(dest))
            if update_dest and setup_newer_than((install_state(dest) or {}).get('release')):
                self.run_setup(['--dest', str(dest)], Path(dest))
        else:
            self.show_form()
        if not selftest and not LAYOUT.dev and (ROOT / layouts.UPDATE_DIR).exists():
            # what the last in-place update left (update.py): the old files, the unpacked release; its Python may
            # still be ending, so a moment later, and what is still held stays for the next start
            cleanup = threading.Timer(5, shutil.rmtree, (ROOT / layouts.UPDATE_DIR,), {'ignore_errors': True})
            cleanup.daemon = True   # never keeps the process after the window
            cleanup.start()
        if not selftest and not LAYOUT.dev and (ROOT / 'Fastball.exe').is_file():
            # an older setup's updater (0.1.5 and before) unpacked this release and started its Fastball.exe copy
            # (update.py): that launcher has ended by now, and Fastball.exe is the one to run from here on
            for name in layouts.LEGACY_ENTRIES:
                gone = threading.Timer(3, lambda p=ROOT / name: p.unlink(missing_ok=True) if p.is_file() else None)
                gone.daemon = True
                gone.start()
        self.root.after(100, self.poll)

    # ---- look -------------------------------------------------------------------------------------------------------

    def px(self, n):
        """n pixels at 100% display scale, in this display's pixels."""
        return round(n * self.scale)

    @property
    def wrap(self):
        """The wrap length of the body's text."""
        return self.px(760)

    def style(self):
        """A flat dark theme over ttk's clam (standard library only). Labels keep one background everywhere, so the
        logic's style names (Ok.TLabel, Bad.TLabel, Muted.TLabel) read the same on every screen; cards have their own
        Card* styles."""
        px = self.px
        self.root.configure(bg=BG)
        s = ttk.Style(self.root)
        s.theme_use('clam')
        base = ('Segoe UI', 10)
        # not option_add('*Font'): a ttk label's own -font would then override its style
        s.configure('.', font=base, background=BG, foreground=TEXT, bordercolor=BORDER, lightcolor=BG, darkcolor=BG,
                    troughcolor=SURFACE, fieldbackground=SURFACE, selectbackground=ACCENT, selectforeground=HEADER_FG,
                    insertcolor=TEXT, focuscolor=BG)
        s.map('.', foreground=[('disabled', DIM)])
        s.configure('TFrame', background=BG)
        s.configure('TLabel', background=BG, foreground=TEXT)
        s.configure('Title.TLabel', font=(SEMI, 18))
        s.configure('Section.TLabel', font=(SEMI, 9), foreground=MUTED)
        s.configure('Muted.TLabel', foreground=MUTED)
        s.configure('Small.TLabel', foreground=MUTED, font=('Segoe UI', 9))
        s.configure('Ok.TLabel', foreground=OK)
        s.configure('Bad.TLabel', foreground=BAD)
        s.configure('Step.TLabel', font=base)
        s.configure('StepNow.TLabel', font=(SEMI, 10))
        s.configure('Now.TLabel', foreground=ACCENT)   # the mark of the running step
        s.configure('Card.TFrame', background=SURFACE)
        s.configure('Card.TLabel', background=SURFACE, foreground=TEXT)
        s.configure('CardMuted.TLabel', background=SURFACE, foreground=MUTED)
        s.configure('CardTitle.TLabel', background=SURFACE, foreground=TEXT, font=(SEMI, 11))
        s.configure('Row.TLabel', font=(SEMI, 10))
        s.configure('On.TLabel', foreground=OK, font=(SEMI, 9))
        s.configure('Off.TLabel', foreground=DIM, font=(SEMI, 9))
        s.configure('TSeparator', background=BORDER)

        def button(name, bg, hover, press, fg, font, pad, ring):
            s.configure(name, background=bg, foreground=fg, bordercolor=bg, lightcolor=bg, darkcolor=bg, font=font,
                        padding=pad, relief='flat', anchor='center', focuscolor=bg)
            states = [('disabled', SURFACE), ('pressed', press), ('active', hover)]
            s.map(name, background=states, lightcolor=states, darkcolor=states, focuscolor=states,
                  bordercolor=[('focus', ring), *states], foreground=[('disabled', DIM)])
        button('TButton', SURFACE, SURFACE_HI, BORDER, TEXT, base, (px(14), px(6)), ACCENT)
        button('Accent.TButton', ACCENT, ACCENT_HI, ACCENT_LO, HEADER_FG, (SEMI, 10), (px(14), px(6)), '#a9cbff')
        button('Big.TButton', ACCENT, ACCENT_HI, ACCENT_LO, HEADER_FG, (SEMI, 12), (px(30), px(10)), '#a9cbff')
        button('BigAlt.TButton', SURFACE, SURFACE_HI, BORDER, TEXT, (SEMI, 12), (px(26), px(10)), ACCENT)

        s.configure('TEntry', fieldbackground=SURFACE, foreground=TEXT, bordercolor=BORDER, lightcolor=SURFACE,
                    darkcolor=SURFACE, insertcolor=TEXT, padding=(px(8), px(5)))
        s.map('TEntry', bordercolor=[('focus', ACCENT)], lightcolor=[('focus', ACCENT)])

        # The box is drawn here (rounded, with a tick) rather than by the theme: clam draws an X on Tk 8.6 and a tick
        # on Tk 9 (the release's), and this looks the same on both
        size = px(16)
        self.boxes = {k: self.check_image(size, *v) for k, v in {
            'off': (SURFACE, BORDER, False), 'off_hover': (SURFACE_HI, MUTED, False),
            'on': (ACCENT, ACCENT, True), 'on_hover': (ACCENT_HI, ACCENT_HI, True)}.items()}
        if 'Fastball.indicator' not in s.element_names():
            s.element_create('Fastball.indicator', 'image', self.boxes['off'],
                             ('selected', 'active', self.boxes['on_hover']), ('selected', self.boxes['on']),
                             ('active', self.boxes['off_hover']), width=size + px(10), sticky='w')
        s.layout('TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
            ('Fastball.indicator', {'side': 'left', 'sticky': ''}),
            ('Checkbutton.label', {'side': 'left', 'sticky': 'nswe'})]})])
        s.configure('TCheckbutton', background=BG, foreground=TEXT, padding=(0, px(3)))
        s.map('TCheckbutton', background=[('active', BG)], foreground=[('disabled', DIM), ('active', HEADER_FG)])

        s.configure('Horizontal.TProgressbar', troughcolor=SURFACE, background=ACCENT, bordercolor=SURFACE,
                    lightcolor=ACCENT, darkcolor=ACCENT, thickness=px(8))

    def check_image(self, n, fill, edge, tick):
        """An n x n checkbox: a rounded square of fill with a 1 px edge, a white tick when tick; smoothed edges."""
        def rgb(c):
            return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))

        def mix(a, b, t):   # a over b, t = how much of a
            return tuple(round(x * t + y * (1 - t)) for x, y in zip(a, b))
        bg, fill, edge, white = rgb(BG), rgb(fill), rgb(edge), (255, 255, 255)
        r = n * 0.22   # corner radius
        w = max(1.6, n / 8)   # tick stroke
        pts = [(n * 0.24, n * 0.52), (n * 0.42, n * 0.70), (n * 0.76, n * 0.32)]

        def seg(px_, py, a, b):   # distance from the pixel centre to the segment a-b
            (ax, ay), (bx, by) = a, b
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((px_ - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
            return ((px_ - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5
        rows = []
        for y in range(n):
            row = []
            for x in range(n):
                cx, cy = x + 0.5, y + 0.5
                # distance outside the rounded square (negative inside)
                qx, qy = max(abs(cx - n / 2) - (n / 2 - r), 0), max(abs(cy - n / 2) - (n / 2 - r), 0)
                d = (qx * qx + qy * qy) ** 0.5 - r
                c = mix(edge, fill, max(0.0, min(1.0, d + 1.5)))   # the 1 px edge
                if tick:
                    near = min(seg(cx, cy, *pts[:2]), seg(cx, cy, *pts[1:]))
                    c = mix(white, c, max(0.0, min(1.0, w / 2 + 0.5 - near)))
                row.append('#%02x%02x%02x' % mix(c, bg, max(0.0, min(1.0, 0.5 - d))))
            rows.append('{' + ' '.join(row) + '}')
        image = tk.PhotoImage(master=self.root, width=n, height=n)
        image.put(' '.join(rows))
        return image

    def title_bar(self):
        """A seamless title bar: Windows 11 paints it (and the window's edge) in the header's colour, so the two read
        as one band; Windows 10 (20H1 and later) draws it dark. Still Windows' own bar: snapping, dragging and the
        buttons work as in any window."""
        if os.name != 'nt':
            return

        def colorref(c):   # '#rrggbb' -> 0x00bbggrr
            return ctypes.c_uint(int(c[5:7], 16) << 16 | int(c[3:5], 16) << 8 | int(c[1:3], 16))
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            set_attr = ctypes.windll.dwmapi.DwmSetWindowAttribute
            # 20 dark mode, 34 border colour, 35 caption colour, 36 caption text colour (each ignored where unknown)
            for attr, value in ((20, ctypes.c_int(1)), (34, colorref(HEADER_BG)), (35, colorref(HEADER_BG)),
                                (36, colorref(MUTED))):
                set_attr(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
        except (AttributeError, OSError):
            pass

    def header(self):
        px = self.px
        h = tk.Frame(self.root, bg=HEADER_BG)
        h.pack(fill='x')
        if self.logo:
            tk.Label(h, image=self.logo, bg=HEADER_BG).pack(side='left', padx=(px(20), px(10)), pady=(px(4), px(14)))
        else:
            tk.Frame(h, width=px(10), bg=HEADER_BG).pack(side='left', padx=(px(10), 0), pady=(px(4), px(14)))
        titles = tk.Frame(h, bg=HEADER_BG)
        titles.pack(side='left')
        tk.Label(titles, text='Fastball', bg=HEADER_BG, fg=HEADER_FG, font=(SEMI, 15)).pack(anchor='w')
        tk.Label(titles, text='MLB The Show 26 for PC', bg=HEADER_BG, fg=MUTED, font=('Segoe UI', 9)).pack(
            anchor='w')
        tk.Label(h, text=f'v{LAYOUT.release}', bg=SURFACE, fg=MUTED, font=('Segoe UI', 9), padx=px(10),
                 pady=px(3)).pack(side='right', padx=px(20))
        tk.Frame(self.root, bg=STITCH, height=max(2, px(2))).pack(fill='x')   # the baseball's stitches

    def screen(self):
        if self.body:
            self.body.destroy()
        px = self.px
        self.body = ttk.Frame(self.root, padding=(px(28), px(20), px(28), px(18)))
        self.body.pack(fill='both', expand=True)
        return self.body

    def section(self, parent, text, top=16):
        """A small heading over a group of fields or buttons."""
        ttk.Label(parent, text=text.upper(), style='Section.TLabel').pack(anchor='w', pady=(self.px(top), self.px(6)))

    def card(self, parent, color=ACCENT):
        """A raised panel with a coloured edge on its left (notices); returns its inside."""
        outer = tk.Frame(parent, bg=color)
        outer.pack(fill='x', pady=(0, self.px(10)))
        inner = ttk.Frame(outer, style='Card.TFrame', padding=(self.px(14), self.px(10)))
        inner.pack(fill='x', padx=(self.px(3), 0))
        return inner

    def footer(self, parent):
        """The bottom bar of a screen, under a line."""
        foot = ttk.Frame(parent)
        foot.pack(side='bottom', fill='x', pady=(self.px(12), 0))
        ttk.Separator(parent).pack(side='bottom', fill='x')
        return foot

    # ---- install form -----------------------------------------------------------------------------------------------

    def show_form(self):
        b = self.screen()
        px = self.px
        foot = self.footer(b)
        ttk.Label(b, text='Set up the game', style='Title.TLabel').pack(anchor='w')
        ttk.Label(b, text='No game files are included in this download: the setup builds the game on your PC from your '
                          'own MLB The Show 26 and its 1.0.20 (or 1.0.15) update as NSP files dumped from your Switch, '
                          'and your Switch\'s prod.keys.', wraplength=self.wrap, style='Muted.TLabel',
                  justify='left').pack(anchor='w', pady=(px(2), 0))
        self.section(b, 'Your files', top=14)
        grid = ttk.Frame(b)
        grid.pack(fill='x')
        grid.columnconfigure(1, weight=1)
        s = self.settings
        self.vars = {k: tk.StringVar(value=s.get(k, '')) for k in ('base', 'update', 'keys', 'dest')}
        self.notes = {}
        rows = [('base', 'Base game (NSP)', [('NSP files', '*.nsp')]),
                ('update', 'Update 1.0.20 (NSP)', [('NSP files', '*.nsp')]),
                ('keys', 'Keys (prod.keys)', [('Keys', '*.keys'), ('All files', '*.*')]),
                ('dest', 'Install folder', None)]
        for i, (key, label, types) in enumerate(rows):
            r = i * 2
            top = 0 if i == 0 else px(6)
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky='w', padx=(0, px(14)), pady=(top, 0))
            ttk.Entry(grid, textvariable=self.vars[key]).grid(row=r, column=1, sticky='ew', pady=(top, 0))
            ttk.Button(grid, text='Browse', command=lambda k=key, t=types: self.browse(k, t)).grid(
                row=r, column=2, sticky='ns', padx=(px(8), 0), pady=(top, 0))
            note = ttk.Label(grid, text='', style='Muted.TLabel')
            note.grid(row=r + 1, column=1, columnspan=2, sticky='w', pady=(px(2), 0))
            self.notes[key] = note
            self.vars[key].trace_add('write', lambda *_a, k=key: self.validate(k))
        self.section(b, 'Options')
        opts = ttk.Frame(b)   # the DLSS and save boxes join it once detect() has looked (detected)
        opts.pack(fill='x')
        # shortcuts off by default: the port lives in its folder, and deleting the folder removes all of it
        self.opt = {'shortcut': tk.BooleanVar(value=False),
                    'import_save': tk.BooleanVar(value=False), 'equipment': tk.BooleanVar(value=False),
                    'packages': tk.BooleanVar(value=False)}
        ttk.Checkbutton(opts, text='Shortcuts on the desktop and in the Start menu',
                        variable=self.opt['shortcut']).pack(anchor='w')
        ttk.Checkbutton(opts, text='Unlock all Road to the Show equipment for offline play (adds a few minutes)',
                        variable=self.opt['equipment']).pack(anchor='w')
        ttk.Checkbutton(opts, text='Add Road to the Show packages: earn equipment from packs like the online game '
                                   '(items start locked)', variable=self.opt['packages']).pack(anchor='w')
        # the upscalers are not a choice here: the setup downloads what this PC's graphics card runs (steps.py
        # Finish.upscalers) and the game's settings turn them on; this line says what it found
        self.gpu_note = ttk.Label(opts, text='', style='Muted.TLabel', wraplength=self.wrap, justify='left')
        self.save_box = ttk.Checkbutton(opts, text='Copy my MLB The Show 26 save from Ryujinx',
                                        variable=self.opt['import_save'])
        self.form_error = ttk.Label(foot, text='', style='Bad.TLabel', wraplength=self.px(540), justify='left')
        self.form_error.pack(side='left')
        self.install_btn = ttk.Button(foot, text='Install', style='Big.TButton', command=self.start_install)
        self.install_btn.pack(side='right')
        if s.get('dest') and Path(s['dest']).is_dir() and install_state(s['dest']) is None:
            self.install_btn.configure(text='Continue install')
        for k in self.vars:
            self.validate(k)
        self.notes['base'].configure(text='Looking for your game files...', style='Muted.TLabel')
        threading.Thread(target=self.detect, daemon=True).start()

    def detect(self):
        """Fill the empty fields from what is on the PC (a thread: it may look through a few folders)."""
        extra = [ROOT.parent, ROOT]
        for k in ('base', 'update'):
            if self.vars[k].get():
                extra.insert(0, Path(self.vars[k].get()).parent)
        found = detect.find_game_files(extra)
        keys = detect.find_keys([ROOT, ROOT.parent] + [p.parent for p in found.values() if p])
        gpus = detect.gpus()
        info = {'found': found, 'keys': keys, 'gpus': gpus, 'rtx': detect.nvidia_rtx(gpus),
                'fsr': detect.fsr_gpu(gpus), 'save': detect.ryujinx_save(),
                'dest': default_dest()}
        self.events.put(('detected', info))

    def detected(self, info):
        if not self.root.winfo_exists() or not hasattr(self, 'vars') or not self.notes['base'].winfo_exists():
            return   # the form is gone (another screen opened while the search ran)
        for k in ('base', 'update'):
            p = info['found'].get(k)
            if p and not self.vars[k].get():
                self.vars[k].set(str(p))
                self.notes[k].configure(text=where(p), style='Ok.TLabel')
        if info['keys'] and not self.vars['keys'].get():
            self.vars['keys'].set(str(info['keys']))
            self.notes['keys'].configure(text=where(info['keys']), style='Ok.TLabel')
        if not self.vars['dest'].get():
            self.vars['dest'].set(str(info['dest']))
        ups = [n for n, on in (('NVIDIA DLSS (about 56 MB)', info['rtx']), ('AMD FSR (about 36 MB)', info['fsr'])) if on]
        if ups:
            card = next((g for g in info['gpus'] if any(v in g.upper() for v in ('AMD', 'RADEON', 'NVIDIA', 'INTEL'))),
                        info['gpus'][0])
            self.gpu_note.configure(text=f'Graphics card: {card}. The setup also downloads {" and ".join(ups)} for it; '
                                         'turn it on in the game\'s settings (F1, Graphics).')
            self.gpu_note.pack(anchor='w', pady=(self.px(4), 0))
        if info['save']:
            self.opt['import_save'].set(not (Path(self.vars['dest'].get()) / 'profile' / 'save').exists())
            self.save_box.pack(anchor='w')
        for k in ('base', 'update', 'keys'):
            if str(self.notes[k].cget('style')) != 'Ok.TLabel':
                self.validate(k)

    def validate(self, key):
        v = self.vars[key].get().strip().strip('"')
        note = self.notes[key]
        if key == 'dest':
            if not v:
                note.configure(text='', style='Muted.TLabel')
                return
            if LAYOUT.reserved(v):
                note.configure(text=f'Pick a folder of its own, such as {LAYOUT.default_dest()}', style='Bad.TLabel')
                return
            free = detect.free_bytes(v)
            done = (Path(v) / 'game' / 'romfs.complete').is_file()
            need = 'about 2 GB (the game files are already there)' if done else 'about 37 GB'
            note.configure(text=f'Needs {need}; {free / (1 << 30):.0f} GB free on that disk',
                           style='Bad.TLabel' if free < (2 if done else 37) * (1 << 30) else 'Muted.TLabel')
            return
        if not v:
            note.configure(text='Not found: pick the file' if key != 'keys' else 'Not found: pick your prod.keys',
                           style='Bad.TLabel')
            return
        p = Path(v)
        if not p.is_file():
            note.configure(text='This file does not exist', style='Bad.TLabel')
            return
        if key == 'keys':
            try:
                ok = 'header_key' in p.read_text(encoding='utf-8', errors='replace')
            except OSError:
                ok = False
            if not ok:
                note.configure(text='Not a prod.keys file', style='Bad.TLabel')
            elif str(note.cget('style')) != 'Ok.TLabel':
                note.configure(text='Keys file', style='Ok.TLabel')
            return
        info = detect.identify(p)
        if info is None:
            note.configure(text='Not an NSP file', style='Bad.TLabel')
        elif info['kind'] == 'other':
            note.configure(text='Not MLB The Show 26', style='Bad.TLabel')
        elif info['kind'] != key:
            note.configure(text=f'This is the {info["kind"]} file; the setup will use it as such', style='Muted.TLabel')
        elif key == 'update' and info['version'] not in (None, *detect.UPDATE_VERSIONS):
            note.configure(text=f'Update version {info["version"]}: the port needs 1.0.20 (1310720) or 1.0.15 (983040)',
                           style='Bad.TLabel')
        elif str(note.cget('style')) != 'Ok.TLabel':
            v = detect.UPDATE_VERSIONS.get(info['version'])
            note.configure(text='MLB The Show 26' + ((f' {v} update' if v else ' update') if key == 'update' else ''),
                           style='Ok.TLabel')

    def browse(self, key, types):
        cur = self.vars[key].get()
        start = str(Path(cur).parent) if cur else str(Path.home())
        if types is None:
            p = filedialog.askdirectory(initialdir=start, title='Install folder')
            if p:
                p = Path(p)
                if p.name != 'MLB The Show 26' and any(p.iterdir()) and not state_file(p).is_file():
                    p = p / 'MLB The Show 26'   # never spread the game over a folder that holds other things
        else:
            p = filedialog.askopenfilename(initialdir=start, filetypes=types)
        if p:
            self.vars[key].set(str(Path(p)))

    def start_install(self):
        v = {k: self.vars[k].get().strip().strip('"') for k in self.vars}
        if not v['dest'] or LAYOUT.reserved(v['dest']):
            self.form_error.configure(text=f'Pick an install folder of its own, such as {LAYOUT.default_dest()}.')
            return
        resume = state_file(v['dest']).is_file()
        if not resume:
            for k, what in (('base', 'base game'), ('update', 'update'), ('keys', 'prod.keys')):
                if not v[k] or not Path(v[k]).is_file():
                    self.form_error.configure(text=f'Pick the {what} file.')
                    return
        self.settings.update(v)
        save_settings(self.settings)
        args = ['--dest', v['dest']]
        for k in ('base', 'update', 'keys'):
            if v[k] and Path(v[k]).is_file():
                args += [f'--{k}', v[k]]
        args += [f'--{k.replace("_", "-")}' for k, var in self.opt.items() if var.get()]
        self.run_setup(args, Path(v['dest']))

    # ---- progress ---------------------------------------------------------------------------------------------------

    def run_setup(self, args, dest):
        b = self.screen()
        px = self.px
        foot = self.footer(b)
        self.dest = dest
        ttk.Label(b, text='Installing', style='Title.TLabel').pack(anchor='w')
        ttk.Label(b, text=f'into {dest}', style='Muted.TLabel').pack(anchor='w')
        self.section(b, 'Steps')
        self.step_box = ttk.Frame(b)
        self.step_box.pack(fill='x')
        self.step_rows = {}
        self.now_text = ttk.Label(b, text='Starting...', wraplength=self.wrap, justify='left')
        self.now_text.pack(anchor='w', pady=(px(18), px(8)))
        self.bar = ttk.Progressbar(b, mode='indeterminate')
        self.bar.pack(fill='x')
        self.bar.start(12)
        self.messages = ttk.Label(b, text='', wraplength=self.wrap, style='Muted.TLabel', justify='left')
        self.messages.pack(anchor='w', pady=(px(12), 0), fill='x')
        self.cancel_btn = ttk.Button(foot, text='Cancel', command=self.cancel)
        self.cancel_btn.pack(side='right')
        ttk.Label(foot, text='You can cancel and continue later: finished work is kept.', style='Muted.TLabel').pack(
            side='left')
        self.warnings, self.error, self.log_path, self.result = [], None, None, None
        cmd = [str(LAYOUT.python), '-I', '-X', 'utf8', '-c', RUN_CLI, str(ROOT), *args]
        self.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        threading.Thread(target=self.read_events, args=(self.proc,), daemon=True).start()

    def read_events(self, proc):
        for raw in proc.stdout:
            line = raw.decode('utf-8', 'replace').strip()
            try:
                self.events.put(('event', json.loads(line)))
            except ValueError:
                if line:
                    self.events.put(('event', {'type': 'warning', 'text': line}))
        proc.wait()
        self.events.put(('exit', proc.returncode))

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'detected':
                    self.detected(data)
                elif kind == 'event':
                    self.on_event(data)
                elif kind == 'exit':
                    self.finished(data)
                elif kind == 'update':
                    self.offer_update(data)
                elif kind == 'download':
                    self.download_event(*data)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)   # one loop for the window's life, started in __init__

    def on_event(self, e):
        t = e.get('type')
        if t == 'start':
            self.log_path = e.get('log')
            for s in e.get('steps', []):
                row = ttk.Frame(self.step_box)
                row.pack(fill='x', pady=max(1, self.px(2)))
                mark = ttk.Label(row, text='○', width=3, style='Muted.TLabel')
                mark.pack(side='left')
                name = ttk.Label(row, text=s['title'], style='Step.TLabel')
                name.pack(side='left')
                self.step_rows[s['id']] = (mark, name)
        elif t == 'step' and e.get('step') in self.step_rows:
            mark, name = self.step_rows[e['step']]
            state = e.get('state')
            if state == 'started':
                mark.configure(text='●', style='Now.TLabel')
                name.configure(style='StepNow.TLabel')
                self.now_text.configure(text=name.cget('text') + '...')
                self.bar.configure(mode='indeterminate')
                self.bar.start(12)
            elif state == 'done':
                mark.configure(text='✓', style='Ok.TLabel')
                name.configure(style='Step.TLabel')
            elif state == 'skipped':
                mark.configure(text='✓', style='Muted.TLabel')
                name.configure(style='Muted.TLabel', text=name.cget('text') + '  (already done)')
        elif t == 'progress':
            self.now_text.configure(text=e.get('text', ''))
            if e.get('total'):
                if str(self.bar.cget('mode')) != 'determinate':
                    self.bar.stop()
                    self.bar.configure(mode='determinate', maximum=1000)
                self.bar.configure(value=1000 * e['done'] / e['total'])
        elif t == 'warning':
            self.warnings.append(e.get('text', ''))
            self.messages.configure(text='\n'.join('⚠ ' + w for w in self.warnings[-4:]))
        elif t == 'error':
            self.error = e.get('text', '')
            if e.get('step') in self.step_rows:
                self.step_rows[e['step']][0].configure(text='✗', style='Bad.TLabel')
        elif t == 'end':
            self.result = e.get('result')

    def finished(self, code):
        self.proc = None
        self.bar.stop()
        if self.result == 'ok':
            self.show_launcher(self.dest, just_installed=True)
            return
        foot = self.cancel_btn.master
        for w in foot.winfo_children():
            w.destroy()
        if self.result == 'cancelled':
            self.now_text.configure(text='Cancelled. Start the setup again to continue where it stopped.')
        else:
            self.now_text.configure(text=self.error or f'The setup stopped (exit code {code}).', style='Bad.TLabel')
        self.bar.configure(mode='determinate', value=0)
        ttk.Button(foot, text='Back', style='Accent.TButton', command=self.show_form).pack(side='right')
        if self.log_path:
            ttk.Button(foot, text='Open setup log', command=lambda: os.startfile(self.log_path)).pack(
                side='right', padx=self.px(8))

    def cancel(self):
        if self.proc and messagebox.askyesno('Cancel', 'Stop the setup? Finished work is kept, and the next start '
                                                        'continues where it stopped.', parent=self.root):
            self.result = 'cancelled'
            # the whole tree: the setup, the extraction or the compiler and its jobs
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(self.proc.pid)], capture_output=True,
                           creationflags=NO_WINDOW)

    # ---- launcher ---------------------------------------------------------------------------------------------------

    def show_launcher(self, dest, just_installed=False):
        b = self.screen()
        px = self.px
        self.launcher_dest = Path(dest)
        state = install_state(dest) or {}
        installed = state.get('release') or 'unknown'
        outdated = setup_newer_than(installed)
        tips = ('In the game: F1 opens the settings menu, F11 switches full screen. Controllers: Xbox and '
                'PlayStation pads work; the keyboard works too.\nFrom now on Fastball.exe starts the game '
                'straight away; hold Shift while starting it (or pass --menu) to open this window. It checks for new '
                'versions of the port once a day; an update keeps your game files, saves and settings.')
        ttk.Label(self.footer(b), text=tips, wraplength=self.wrap, style='Small.TLabel', justify='left').pack(
            anchor='w')
        ttk.Label(b, text='Installed! Ready to play.' if just_installed else 'Ready to play',
                  style='Title.TLabel').pack(anchor='w')
        ttk.Label(b, text=f'Port version {installed}   ·   {dest}', style='Muted.TLabel').pack(
            anchor='w', pady=(0, px(14)))
        if outdated:
            ttk.Label(self.card(b), text=f'This setup is version {LAYOUT.release}. Update rebuilds the game with it in '
                                         'a few minutes; your game files, saves and settings stay.',
                      wraplength=self.wrap - px(40), style='Card.TLabel', justify='left').pack(anchor='w')
        elif update.newer(installed, LAYOUT.release):
            ttk.Label(self.card(b, WARN), text=f'This setup (version {LAYOUT.release}) is older than the installed '
                                               'port: use the newer setup to repair it.',
                      wraplength=self.wrap - px(40), style='CardMuted.TLabel', justify='left').pack(anchor='w')
        self.update_box = ttk.Frame(b)   # filled by offer_update when GitHub has a newer release
        self.update_box.pack(anchor='w', fill='x')
        if just_installed and getattr(self, 'warnings', None):
            ttk.Label(self.card(b, WARN), text='\n'.join('⚠ ' + w for w in self.warnings),
                      wraplength=self.wrap - px(40), style='CardMuted.TLabel', justify='left').pack(anchor='w')
        main = ttk.Frame(b)
        main.pack(anchor='w', pady=(px(4), 0))
        ttk.Button(main, text='▶   Play', style='Big.TButton', command=lambda: self.play(dest)).pack(side='left')
        if outdated:
            ttk.Button(main, text='Update', style='BigAlt.TButton',
                       command=lambda: self.run_setup(['--dest', str(dest)], dest)).pack(side='left', padx=px(10))
        self.section(b, 'Manage', top=20)
        more = ttk.Frame(b)
        more.pack(anchor='w')
        gap = (0, px(8))
        if detect.ryujinx_save():
            ttk.Button(more, text='Import Ryujinx save', command=lambda: self.import_save(dest)).pack(
                side='left', padx=gap)
        ttk.Button(more, text='Open install folder', command=lambda: os.startfile(dest)).pack(side='left', padx=gap)
        if not outdated:
            ttk.Button(more, text='Repair', command=lambda: self.run_setup(['--dest', str(dest)], dest)).pack(
                side='left', padx=gap)
        ttk.Button(more, text='Install somewhere else', command=self.show_form).pack(side='left', padx=gap)
        self.section(b, 'Road to the Show', top=20)
        steps = state.get('steps') or {}

        def option(name, on, flag, note):
            """One add-on: its name and whether it is in, what the button does, Add or Remove."""
            row = ttk.Frame(b)
            row.pack(fill='x', pady=(0, px(8)))
            ttk.Button(row, text='Remove' if on else 'Add', width=8,
                       command=lambda: self.run_setup(['--dest', str(dest), flag], dest)).pack(side='right')
            text = ttk.Frame(row)   # centred beside the button
            text.pack(side='left', fill='x')
            head = ttk.Frame(text)
            head.pack(anchor='w')
            ttk.Label(head, text=name, style='Row.TLabel').pack(side='left')
            ttk.Label(head, text='ON' if on else 'OFF', style='On.TLabel' if on else 'Off.TLabel').pack(
                side='left', padx=px(8))
            if note:
                ttk.Label(text, text=note, style='Muted.TLabel', wraplength=self.wrap - px(120),
                          justify='left').pack(anchor='w')
        on = bool((steps.get('equipment') or {}).get('installed'))
        option('Equipment', on, '--no-equipment' if on else '--equipment',
               None if on else 'Adding equipment will unlock all equipment items in every Road to the Show save')
        on = bool((steps.get('packages') or {}).get('installed'))
        option('Packages', on, '--no-packages' if on else '--packages',
               'Removing packages will unlock all equipment items in every Road to the Show save' if on else
               'Adding packages will lock all equipment items until you earn them from packs')
        self.settings['dest'] = str(dest)
        save_settings(self.settings)
        if not self.selftest and not self.update_checked:
            self.update_checked = True   # once per start
            threading.Thread(target=self.check_update, daemon=True).start()
        elif getattr(self, 'update_info', None):
            self.offer_update(self.update_info)

    # ---- updates (update.py) ----------------------------------------------------------------------------------------

    def check_update(self):
        """A thread: the latest release on GitHub; offered when newer than this setup. Failures stay quiet (offline)."""
        try:
            info = update.latest()
        except Exception:   # noqa: BLE001 (no network, GitHub down, rate limit: the launcher works without it)
            return
        if info and update.newer(info['version'], LAYOUT.release):
            self.events.put(('update', info))

    def offer_update(self, info):
        self.update_info = info
        box = getattr(self, 'update_box', None)
        if not box or not box.winfo_exists() or box.winfo_children():
            return
        px = self.px
        card = self.card(box, OK)
        row = ttk.Frame(card, style='Card.TFrame')
        row.pack(fill='x')
        ttk.Button(row, text="What's new", command=lambda: os.startfile(info['page'])).pack(side='right')
        ttk.Button(row, text='Download and update', style='Accent.TButton',
                   command=lambda: self.start_download(info)).pack(side='right', padx=px(8))
        ttk.Label(row, text=f'Version {info["version"]} of the port is available', style='CardTitle.TLabel').pack(
            side='left')
        size = f'about {info["size"] >> 20} MB, ' if info.get('size') else ''
        ttk.Label(card, text=f'Downloads the new version ({size}from GitHub) into this folder, then rebuilds the '
                             'game with it in a few minutes.', style='CardMuted.TLabel', wraplength=self.wrap - px(40),
                  justify='left').pack(anchor='w', pady=(px(4), 0))

    def start_download(self, info):
        dest = self.launcher_dest
        b = self.screen()
        px = self.px
        foot = self.footer(b)
        ttk.Label(b, text=f'Updating to version {info["version"]}', style='Title.TLabel').pack(anchor='w')
        ttk.Label(b, text=f'for {dest}', style='Muted.TLabel').pack(anchor='w')
        self.now_text = ttk.Label(b, text='Connecting to GitHub...', wraplength=self.wrap, justify='left')
        self.now_text.pack(anchor='w', pady=(px(24), px(8)))
        self.bar = ttk.Progressbar(b, mode='determinate', maximum=1000)
        self.bar.pack(fill='x')
        ttk.Button(foot, text='Cancel', command=lambda: self.download_cancel and self.download_cancel.set()).pack(
            side='right')
        ttk.Label(foot, text='After the download, the new version replaces this one and rebuilds the game.',
                  style='Muted.TLabel').pack(side='left')
        self.download_cancel = cancel = threading.Event()

        def work():
            def progress(text, done, total):
                self.events.put(('download', ('progress', text, done, total)))
            try:
                folder = update.download(info, ROOT, progress, cancel.is_set)
                self.events.put(('download', ('done', folder, dest, None)))
            except update.Cancelled:
                self.events.put(('download', ('cancelled', None, dest, None)))
            except Exception as e:   # noqa: BLE001 (shown to the player)
                self.events.put(('download', ('error', str(e) or type(e).__name__, dest, None)))
        threading.Thread(target=work, daemon=True).start()

    def download_event(self, kind, a, b, c):
        if kind == 'progress':
            if self.now_text.winfo_exists():
                self.now_text.configure(text=a)
                if c:
                    self.bar.configure(value=1000 * b / c)
            return
        self.download_cancel = None
        if kind == 'done':
            try:
                if LAYOUT.dev:   # never over a repository: the new setup runs from where it was unpacked
                    exe = next(Path(a) / x for x in update.LAUNCHERS if (Path(a) / x).is_file())
                    subprocess.Popen([str(exe), '--update', str(b)], cwd=a, close_fds=True)
                else:   # in place: its own Python swaps it in once this window is gone, then starts it (update.py)
                    update.start_apply(a, ROOT, b)
            except OSError as e:
                messagebox.showerror('Update', f'The new setup could not start: {e}\n\nIt is in {a}.',
                                     parent=self.root)
                self.show_launcher(b)
                return
            self.root.after(300, self.root.destroy)
            return
        if kind == 'error':
            messagebox.showerror('Update', f'The update could not be downloaded: {a}\n\nYou can try again later, or '
                                 'download the new setup from GitHub yourself.', parent=self.root)
        self.show_launcher(b)

    def play(self, dest):
        ok, e = start_game(dest, game_args())
        if not ok:
            messagebox.showerror('Play', f'mlb.exe could not start: {e}', parent=self.root)
            return
        self.root.after(500, self.root.destroy)

    def import_save(self, dest):
        if not messagebox.askyesno('Import Ryujinx save', 'Copy your MLB The Show 26 save from Ryujinx into this '
                                   'install? The current save is kept in profile\\save-before-import. Close the game '
                                   'first.', parent=self.root):
            return
        r = subprocess.run([str(Path(dest) / 'mlb.exe'), '--import-save'], cwd=dest, capture_output=True,
                           creationflags=NO_WINDOW)
        text = (r.stdout + r.stderr).decode('utf-8', 'replace').strip()
        (messagebox.showinfo if r.returncode == 0 else messagebox.showerror)(
            'Import Ryujinx save', ('Done.\n\n' if r.returncode == 0 else 'Not imported.\n\n') + text[-800:],
            parent=self.root)

    def run(self):
        if self.selftest:
            def tour():
                self.show_form()
                self.root.update()
                self.run_setup_preview()
                self.root.update()
                self.show_launcher(Path(self.settings.get('dest') or ROOT))
                self.root.update()
                self.offer_update({'version': '99.0.0', 'url': '', 'size': 1 << 27, 'sha256': None, 'page': ''})
                self.root.update()
                self.root.destroy()
            self.root.after(300, tour)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.mainloop()

    def run_setup_preview(self):
        """The progress screen without a child process (selftest)."""
        b = self.screen()
        self.step_box = ttk.Frame(b)
        self.step_box.pack()
        self.step_rows = {}
        self.now_text = ttk.Label(b)
        self.bar = ttk.Progressbar(b)
        self.messages = ttk.Label(b)
        self.warnings = []
        for e in ({'type': 'start', 'steps': [{'id': 'check', 'title': 'Check'}]},
                  {'type': 'step', 'step': 'check', 'state': 'started'},
                  {'type': 'progress', 'step': 'check', 'text': 'x', 'done': 1, 'total': 2},
                  {'type': 'step', 'step': 'check', 'state': 'done'}):
            self.on_event(e)

    def close(self):
        if self.proc and not messagebox.askyesno('Quit', 'The setup is running. Stop it and quit? Finished work is '
                                                          'kept.', parent=self.root):
            return
        if self.proc:
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(self.proc.pid)], capture_output=True,
                           creationflags=NO_WINDOW)
        if self.download_cancel:   # the download thread stops at its next block; its partial file is removed
            self.download_cancel.set()
        self.root.destroy()


def main():
    if straight_to_game():
        return
    App(selftest='--selftest' in sys.argv).run()


if __name__ == '__main__':
    main()
