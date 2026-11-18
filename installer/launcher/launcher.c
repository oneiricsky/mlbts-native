/* MLBTS-Setup.exe: starts python\pythonw.exe -m installer.gui with this exe's folder as the working directory, without
   a console window. tools/make_release.py builds it with the release's llvm-mingw:
       llvm/bin/llvm-windres -I runtime/mlb -O coff launcher.rc -o launcher_rc.o
       llvm/bin/clang -O2 -mwindows launcher.c launcher_rc.o -o MLBTS-Setup.exe
   After TotK Recomp installer/launcher/launcher.c @ v0.4.0 (MIT), English only.
   System DPI aware, like the window's Python process (installer/gui.py): the error box is drawn at the display's
   scale instead of stretched.
   Its own arguments are passed on to the window (installer/gui.py): the updater (installer/update.py) starts the new
   setup with --update <install folder>; --menu opens the window; any other argument goes to mlb.exe.
   It is the one program a player runs: once the game is built, installer/gui.py starts mlb.exe at once without a
   window (straight_to_game). */
#include <windows.h>
#include <wchar.h>

#define PATH_CHARS (MAX_PATH * 2)
#define ARGS_CHARS 2048

/* The command line after the program's own name (quoted or not), without the spaces before it. */
static const wchar_t *own_args(void)
{
    const wchar_t *p = GetCommandLineW();
    if (*p == L'"') {
        for (p++; *p && *p != L'"'; p++) {}
        if (*p) p++;
    } else {
        while (*p && *p != L' ' && *p != L'\t') p++;
    }
    while (*p == L' ' || *p == L'\t') p++;
    return p;
}

static void fail(const wchar_t *what)
{
    wchar_t text[PATH_CHARS + 256];
    swprintf(text, sizeof text / sizeof *text,
             L"The setup could not start: %ls.\n\nUnpack the whole download into an empty folder (not inside the zip "
             L"viewer) and start MLBTS-Setup.exe from there.", what);
    MessageBoxW(NULL, text, L"MLB The Show 26 - PC port setup", MB_OK | MB_ICONERROR);
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command_line, int show)
{
    wchar_t folder[PATH_CHARS], python[PATH_CHARS], command[PATH_CHARS + 64 + ARGS_CHARS];
    const wchar_t *args = own_args();
    DWORD n = GetModuleFileNameW(NULL, folder, PATH_CHARS);
    STARTUPINFOW si = { sizeof si };
    PROCESS_INFORMATION pi;
    (void)instance; (void)previous; (void)command_line; (void)show;
    SetProcessDPIAware();   /* before the message box exists */
    if (n == 0 || n >= PATH_CHARS) { fail(L"its own path is too long"); return 1; }
    while (n > 0 && folder[n - 1] != L'\\') n--;
    folder[n > 0 ? n - 1 : 0] = 0;
    if (swprintf(python, PATH_CHARS, L"%ls\\python\\pythonw.exe", folder) < 0 ||
        GetFileAttributesW(python) == INVALID_FILE_ATTRIBUTES) { fail(L"python\\pythonw.exe is missing"); return 1; }
    if (wcslen(args) >= ARGS_CHARS) args = L"";
    if (swprintf(command, sizeof command / sizeof *command, L"\"%ls\" -I -m installer.gui%ls%ls", python,
                 *args ? L" " : L"", args) < 0) { fail(L"path too long"); return 1; }
    if (!CreateProcessW(python, command, NULL, NULL, FALSE, 0, NULL, folder, &si, &pi)) {
        fail(L"python\\pythonw.exe did not start");
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
