"""The setup window and launcher: python -m installer.gui (MLBTS-Setup.exe starts it with the bundled Python).

One window, three screens:
- the install form: the base game and update NSPs, prod.keys and the install folder, filled in from what the setup
  finds by itself (detect.py: the emulators' key and game folders, Downloads, Desktop, ...), and the options;
- the progress screen: the steps of the command-line setup (installer/cli.py, run as a child process; its JSON events
  drive the screen), a progress bar, Cancel;
- the launcher: Play, and Update when this setup is newer than the install, Import Ryujinx save, Open folder. It also
  asks GitHub for a newer release (update.py) and offers "Download and update": the new setup is downloaded, unpacked
  beside this one and started with --update <install folder>, which goes straight to the rebuild.

The last install folder and the file paths are remembered in %LOCALAPPDATA%\\MLBTS-Native\\setup.json (paths only,
never the keys' contents), so starting the setup again opens the launcher on that folder.

--selftest builds every screen and closes (tests; no network).
"""
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import detect
from . import layout as layouts
from . import update
from .steps import STATE

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = layouts.find(ROOT)
SETTINGS = layouts.settings_dir() / 'setup.json'
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
# The command line, from any working directory and with -I: runpy finds the package beside this one
RUN_CLI = ("import sys, runpy; sys.path.insert(0, sys.argv.pop(1)); sys.argv[0] = 'installer'; "
           "runpy.run_module('installer', run_name='__main__', alter_sys=True)")

ACCENT, HEADER_BG, HEADER_FG, OK, BAD, MUTED = '#0b4f9c', '#0d2340', '#ffffff', '#1b7f3b', '#b3261e', '#5f6b7a'


def load_settings():
    try:
        data = json.loads(SETTINGS.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    if '--selftest' in sys.argv:   # the release check's tour must leave the player's (and the developer's) memory alone
        return
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, indent=1), encoding='utf-8')
    except OSError:
        pass


def install_state(dest):
    """The install's mlbts-install.json, or None when dest holds no finished install."""
    try:
        p = Path(dest)
        if not (p / 'mlb.exe').is_file():
            return None
        return json.loads((p / STATE).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None


def inside_setup(dest):
    """dest is the setup folder or inside it (a release only: the repository's work/ is fine for tests)."""
    if LAYOUT.dev:
        return False
    try:
        d = Path(dest).resolve()
    except OSError:
        return False
    return d == ROOT or ROOT in d.parents


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
        self.root.title('MLB The Show 26 - PC port setup')
        self.root.minsize(720, 560)
        self.root.geometry('760x600')
        for icon in (ROOT / 'installer' / 'icon.png', ROOT / 'runtime' / 'mlb' / 'mlb.png'):
            if icon.is_file():
                try:
                    self.root.iconphoto(True, tk.PhotoImage(file=str(icon)))
                except tk.TclError:
                    pass
                break
        self.style()
        self.settings = {} if selftest else load_settings()
        self.events = queue.Queue()
        self.proc = None
        self.body = None
        self.header()
        self.selftest = selftest
        self.download_cancel = None   # a threading.Event while an update downloads
        self.update_checked = False
        dest = self.settings.get('dest')
        update_dest = arg_after('--update')   # started by the previous setup's updater
        if update_dest and install_state(update_dest):
            dest = update_dest
        if dest and install_state(dest):
            self.show_launcher(Path(dest))
            if update_dest and setup_newer_than((install_state(dest) or {}).get('release')):
                self.run_setup(['--dest', str(dest)], Path(dest))
        else:
            self.show_form()
        self.root.after(100, self.poll)

    # ---- look -------------------------------------------------------------------------------------------------------

    def style(self):
        s = ttk.Style(self.root)
        base = ('Segoe UI', 10)
        s.configure('.', font=base)   # not option_add('*Font'): a ttk label's own -font would then override its style
        s.configure('Title.TLabel', font=('Segoe UI Semibold', 15))
        s.configure('Section.TLabel', font=('Segoe UI Semibold', 11))
        s.configure('Muted.TLabel', foreground=MUTED)
        s.configure('Ok.TLabel', foreground=OK)
        s.configure('Bad.TLabel', foreground=BAD)
        s.configure('Big.TButton', font=('Segoe UI Semibold', 12), padding=(22, 8))
        s.configure('Step.TLabel', font=('Segoe UI', 10))
        s.configure('StepNow.TLabel', font=('Segoe UI Semibold', 10))

    def header(self):
        h = tk.Frame(self.root, bg=HEADER_BG, height=64)
        h.pack(fill='x')
        tk.Label(h, text='MLB The Show 26', bg=HEADER_BG, fg=HEADER_FG, font=('Segoe UI Semibold', 17)).pack(
            side='left', padx=(18, 8), pady=12)
        tk.Label(h, text='PC port', bg=HEADER_BG, fg='#9fb7d6', font=('Segoe UI', 13)).pack(side='left', pady=12)
        tk.Label(h, text=f'setup {LAYOUT.release}', bg=HEADER_BG, fg='#9fb7d6', font=('Segoe UI', 9)).pack(
            side='right', padx=18)

    def screen(self):
        if self.body:
            self.body.destroy()
        self.body = ttk.Frame(self.root, padding=(22, 16, 22, 16))
        self.body.pack(fill='both', expand=True)
        return self.body

    # ---- install form -----------------------------------------------------------------------------------------------

    def show_form(self):
        b = self.screen()
        ttk.Label(b, text='This setup builds the game on your PC from your own game files. No game files are included '
                          'in this download: you need MLB The Show 26 and its 1.0.20 (or 1.0.15) update as NSP files dumped from '
                          'your Switch, and your Switch\'s prod.keys.', wraplength=700, style='Muted.TLabel').pack(
            anchor='w', pady=(0, 12))
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
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky='w', padx=(0, 10), pady=(6, 0))
            ttk.Entry(grid, textvariable=self.vars[key]).grid(row=r, column=1, sticky='ew', pady=(6, 0))
            ttk.Button(grid, text='Browse...', command=lambda k=key, t=types: self.browse(k, t)).grid(
                row=r, column=2, padx=(8, 0), pady=(6, 0))
            note = ttk.Label(grid, text='', style='Muted.TLabel')
            note.grid(row=r + 1, column=1, sticky='w')
            self.notes[key] = note
            self.vars[key].trace_add('write', lambda *_a, k=key: self.validate(k))
        ttk.Label(b, text='Options', style='Section.TLabel').pack(anchor='w', pady=(14, 4))
        self.opt = {'shortcut': tk.BooleanVar(value=True), 'dlss': tk.BooleanVar(value=False),
                    'import_save': tk.BooleanVar(value=False), 'equipment': tk.BooleanVar(value=False),
                    'packages': tk.BooleanVar(value=False)}
        ttk.Checkbutton(b, text='Shortcuts on the desktop and in the Start menu', variable=self.opt['shortcut']).pack(
            anchor='w')
        ttk.Checkbutton(b, text='Unlock all Road to the Show equipment for offline play (adds a few minutes)',
                        variable=self.opt['equipment']).pack(anchor='w')
        ttk.Checkbutton(b, text='Add Road to the Show packages: earn equipment from packs like the online game (items '
                                'start locked)', variable=self.opt['packages']).pack(anchor='w')
        self.dlss_box = ttk.Checkbutton(b, text='Download NVIDIA DLSS (sharper picture on RTX graphics cards; from '
                                                'NVIDIA, about 56 MB)', variable=self.opt['dlss'])
        self.save_box = ttk.Checkbutton(b, text='Copy my MLB The Show 26 save from Ryujinx',
                                        variable=self.opt['import_save'])
        foot = ttk.Frame(b)
        foot.pack(side='bottom', fill='x', pady=(10, 0))
        self.form_error = ttk.Label(foot, text='', style='Bad.TLabel', wraplength=520)
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
        info = {'found': found, 'keys': keys, 'rtx': detect.nvidia_rtx(), 'save': detect.ryujinx_save(),
                'dest': detect.default_dest()}
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
        if info['rtx']:
            self.opt['dlss'].set(True)
            self.dlss_box.pack(anchor='w')
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
            if inside_setup(v):
                note.configure(text='Pick a folder outside the setup folder (it can be deleted after the install)',
                               style='Bad.TLabel')
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
                if p.name != 'MLB The Show 26' and any(p.iterdir()) and not (p / STATE).is_file():
                    p = p / 'MLB The Show 26'   # never spread the game over a folder that holds other things
        else:
            p = filedialog.askopenfilename(initialdir=start, filetypes=types)
        if p:
            self.vars[key].set(str(Path(p)))

    def start_install(self):
        v = {k: self.vars[k].get().strip().strip('"') for k in self.vars}
        if not v['dest'] or inside_setup(v['dest']):
            self.form_error.configure(text='Pick an install folder outside the setup folder.')
            return
        resume = (Path(v['dest']) / STATE).is_file()
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
        self.dest = dest
        ttk.Label(b, text='Installing', style='Title.TLabel').pack(anchor='w')
        ttk.Label(b, text=f'into {dest}', style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
        self.step_box = ttk.Frame(b)
        self.step_box.pack(fill='x')
        self.step_rows = {}
        self.now_text = ttk.Label(b, text='Starting...', wraplength=700)
        self.now_text.pack(anchor='w', pady=(14, 4))
        self.bar = ttk.Progressbar(b, mode='indeterminate')
        self.bar.pack(fill='x')
        self.bar.start(12)
        self.messages = ttk.Label(b, text='', wraplength=700, style='Muted.TLabel', justify='left')
        self.messages.pack(anchor='w', pady=(10, 0), fill='x')
        foot = ttk.Frame(b)
        foot.pack(side='bottom', fill='x')
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
                row.pack(fill='x', pady=1)
                mark = ttk.Label(row, text='○', width=3, style='Muted.TLabel')
                mark.pack(side='left')
                name = ttk.Label(row, text=s['title'], style='Step.TLabel')
                name.pack(side='left')
                self.step_rows[s['id']] = (mark, name)
        elif t == 'step' and e.get('step') in self.step_rows:
            mark, name = self.step_rows[e['step']]
            state = e.get('state')
            if state == 'started':
                mark.configure(text='▶', style='TLabel')
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
        ttk.Button(foot, text='Back', command=self.show_form).pack(side='right')
        if self.log_path:
            ttk.Button(foot, text='Open setup log', command=lambda: os.startfile(self.log_path)).pack(
                side='right', padx=8)

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
        self.launcher_dest = Path(dest)
        state = install_state(dest) or {}
        installed = state.get('release') or 'unknown'
        outdated = setup_newer_than(installed)
        ttk.Label(b, text='Installed! Ready to play.' if just_installed else 'Ready to play',
                  style='Title.TLabel').pack(anchor='w')
        ttk.Label(b, text=f'{dest}', style='Muted.TLabel').pack(anchor='w')
        ttk.Label(b, text=f'Port version {installed}', style='Muted.TLabel').pack(anchor='w', pady=(0, 14))
        if outdated:
            ttk.Label(b, text=f'This setup is version {LAYOUT.release}. Update rebuilds the game with it in a few '
                              'minutes; your game files, saves and settings stay.', wraplength=700).pack(
                anchor='w', pady=(0, 10))
        elif update.newer(installed, LAYOUT.release):
            ttk.Label(b, text=f'This setup (version {LAYOUT.release}) is older than the installed port: use the newer '
                              'setup to repair it.', wraplength=700, style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
        self.update_box = ttk.Frame(b)   # filled by offer_update when GitHub has a newer release
        self.update_box.pack(anchor='w', fill='x')
        if just_installed and getattr(self, 'warnings', None):
            ttk.Label(b, text='\n'.join('⚠ ' + w for w in self.warnings), wraplength=700,
                      style='Muted.TLabel', justify='left').pack(anchor='w', pady=(0, 10))
        main = ttk.Frame(b)
        main.pack(anchor='w', pady=(6, 16))
        ttk.Button(main, text='▶  Play', style='Big.TButton', command=lambda: self.play(dest)).pack(side='left')
        if outdated:
            ttk.Button(main, text='Update', style='Big.TButton',
                       command=lambda: self.run_setup(['--dest', str(dest)], dest)).pack(side='left', padx=10)
        more = ttk.Frame(b)
        more.pack(anchor='w')
        if detect.ryujinx_save():
            ttk.Button(more, text='Import Ryujinx save', command=lambda: self.import_save(dest)).pack(side='left')
        ttk.Button(more, text='Open install folder', command=lambda: os.startfile(dest)).pack(side='left', padx=8)
        if not outdated:
            ttk.Button(more, text='Repair', command=lambda: self.run_setup(['--dest', str(dest)], dest)).pack(
                side='left')
        ttk.Button(more, text='Install somewhere else', command=self.show_form).pack(side='left', padx=8)
        extra = ttk.Frame(b)
        extra.pack(anchor='w', pady=(8, 0))
        if ((state.get('steps') or {}).get('equipment') or {}).get('installed'):
            ttk.Button(extra, text='Remove Road to the Show equipment',
                       command=lambda: self.run_setup(['--dest', str(dest), '--no-equipment'], dest)).pack(side='left')
        else:
            ttk.Button(extra, text='Add Road to the Show equipment',
                       command=lambda: self.run_setup(['--dest', str(dest), '--equipment'], dest)).pack(side='left')
            ttk.Label(extra, text='adding equipment will unlock all equipment items in every Road to the Show save',
                      style='Muted.TLabel').pack(side='left', padx=8)
        extra = ttk.Frame(b)
        extra.pack(anchor='w', pady=(8, 0))
        if ((state.get('steps') or {}).get('packages') or {}).get('installed'):
            ttk.Button(extra, text='Remove Road to the Show packages',
                       command=lambda: self.run_setup(['--dest', str(dest), '--no-packages'], dest)).pack(side='left')
            ttk.Label(extra, text='removing packages will unlock all equipment items in every Road to the Show save',
                      style='Muted.TLabel').pack(side='left', padx=8)
        else:
            ttk.Button(extra, text='Add Road to the Show packages',
                       command=lambda: self.run_setup(['--dest', str(dest), '--packages'], dest)).pack(side='left')
            ttk.Label(extra, text='adding packages will lock all equipment items until you earn them from packs',
                      style='Muted.TLabel').pack(side='left', padx=8)
        tips = ('In the game: F1 opens the settings menu, F11 switches full screen. Controllers: Xbox and '
                'PlayStation pads work; the keyboard works too.\nThis window checks for new versions of the port '
                'when it opens; an update keeps your game files, saves and settings.')
        ttk.Label(b, text=tips, wraplength=700, style='Muted.TLabel', justify='left').pack(side='bottom', anchor='w')
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
        ttk.Label(box, text=f'Version {info["version"]} of the port is available.', style='Section.TLabel').pack(
            anchor='w')
        row = ttk.Frame(box)
        row.pack(anchor='w', pady=(4, 6))
        ttk.Button(row, text='Download and update', command=lambda: self.start_download(info)).pack(side='left')
        ttk.Button(row, text="What's new", command=lambda: os.startfile(info['page'])).pack(side='left', padx=8)
        size = f'about {info["size"] >> 20} MB, ' if info.get('size') else ''
        ttk.Label(box, text=f'Downloads the new setup ({size}from GitHub) next to this one, then rebuilds the game '
                            'with it in a few minutes.', style='Muted.TLabel', wraplength=700).pack(anchor='w')

    def start_download(self, info):
        dest = self.launcher_dest
        b = self.screen()
        ttk.Label(b, text=f'Updating to version {info["version"]}', style='Title.TLabel').pack(anchor='w')
        ttk.Label(b, text=f'for {dest}', style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
        self.now_text = ttk.Label(b, text='Connecting to GitHub...', wraplength=700)
        self.now_text.pack(anchor='w', pady=(14, 4))
        self.bar = ttk.Progressbar(b, mode='determinate', maximum=1000)
        self.bar.pack(fill='x')
        foot = ttk.Frame(b)
        foot.pack(side='bottom', fill='x')
        ttk.Button(foot, text='Cancel', command=lambda: self.download_cancel and self.download_cancel.set()).pack(
            side='right')
        ttk.Label(foot, text='After the download, the new setup opens and rebuilds the game.',
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
            exe = Path(a) / 'MLBTS-Setup.exe'
            try:
                subprocess.Popen([str(exe), '--update', str(b)], cwd=a, close_fds=True)
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
        exe = Path(dest) / 'mlb.exe'
        try:
            subprocess.Popen([str(exe)], cwd=dest, creationflags=subprocess.DETACHED_PROCESS | NO_WINDOW,
                             close_fds=True)
        except OSError as e:
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
    App(selftest='--selftest' in sys.argv).run()


if __name__ == '__main__':
    main()
