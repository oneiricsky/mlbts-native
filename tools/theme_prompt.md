# Theme read: one function, one aspect, evidence required

You are reading a dossier of `main` functions from MLB The Show 26 (Switch, 1.0.20, static recompilation). Each entry
is one function: address, size, callers, callees with their known roles, the 256 KB window theme, the function's own
strings, and its operations (calls, loads, stores, branches).

**Answer one question per function: which single aspect of the game does it serve?**

"serves" means: the part of the game whose *behaviour* changes if this function is wrong.

Allowed values, exactly as written:

- `Online and Diamond Dynasty`
- `Road to the Show`
- `Franchise, league and roster`
- `Gameplay: pitching`
- `Gameplay: batting`
- `Gameplay: fielding`
- `Gameplay: baserunning`
- `Gameplay: in-play`
- `Menus and UI`
- `Presentation and animation`
- `Graphics and textures`
- `Audio`
- `Data and serialization`
- `Stats and records`
- `Unclear`

## Choosing between the close ones

- **A menu that belongs to one mode is that mode.** A Diamond Dynasty card screen is `Online and Diamond Dynasty`;
  an Options screen is `Menus and UI`. Ask what the *data* is for, not what the screen is made of.
- **Generic machinery is `Menus and UI`.** A list-scrolling, row-layout, focus, text-measure or input helper is
  `Menus and UI` wherever it is called from, and so is a generic container hook.
- **`Data and serialization` is for reading and writing data, not for using it**: JSON, reflection, save and load,
  class registration, file parsing.
- **`Audio` means audio**: mixing, playback, stream headers, custom-music options. A menu that stores a music choice
  is `Menus and UI` unless it does the audio work itself.
- **`Graphics and textures`** is drawing, scene loading, texture decode and GPU state.
- **`Presentation and animation`** is how the game looks and moves: camera, animation, replays, overlays, play-event
  text.
- **When two answers both seem right, pick the narrower system that owns the code**, and say so in the evidence.

## Rules

1. One line per function, no prose outside the JSONL. Every address in the dossier appears exactly once.
2. **Evidence is required.** `basis` is one of:
   - `string`: `evidence` quotes, verbatim, a string from that function's own `strings:` line, and the quote has to
     name the aspect ("DIAMOND DYNASTY", "FRANCHISE", "crowd", "pitch", "SWING"...). The machine checks that the
     quoted string really is this function's, so copy it exactly.
   - `callee`: `evidence` names an address from that function's `calls:` line and says what that callee does, from
     its role in brackets, that makes the aspect apply. The machine checks that the address is a direct callee.
   - `class`: the function is a vtable method and its own body is bare (a getter, an empty stub, a field write).
     `evidence` quotes a string from that function's `class:` line — prefer `method strings` (its siblings' own
     strings) over `near strings` (strings one hop out) — or names a `named methods` slot and what it does. A class
     whose methods quote a mode's own vocabulary (a training drill, a card collection, a league setting) is that
     mode's class. The machine checks that the quoted string really is quoted inside that class, or that the named
     address really is one of its methods.
   - `operations`: `evidence` points at the operations that decide it, e.g. "writes the +0x1f5c field that the
     callee f_X reads". The machine treats this as a form, not proof, so use it only when the operations are
     unmistakable; naming a direct callee inside the text helps.
   - `guess`: allowed only with `Unclear`; never guess an aspect.
3. **The window theme is not evidence.** It is one label for 256 KB and is measured at 37.5% right per function. If
   the only thing pointing at an aspect is the window label, answer `Unclear` with the evidence "window only".
   The `class:` line is not the window: it is the function's own class and is allowed as evidence.
4. Confidence 0.0 to 1.0. Use 0.9+ only when a string names it outright.
5. Write **only** the output file named in the task. Do not modify the dossier, the map index or anything else.

## Output format

One JSON object per line:

```json
{"addr":"0x7000ac04d0","aspect":"Online and Diamond Dynasty","confidence":0.9,"evidence":"uses \"PLR_FE\" card entry","basis":"string"}
{"addr":"0x7000123456","aspect":"Audio","confidence":0.6,"evidence":"class method string \"AUDIO_MIX_ROW\" next to \"AUDIO_BUS\": the class mixes audio","basis":"class"}
```
Keep each `evidence` under 200 characters.
