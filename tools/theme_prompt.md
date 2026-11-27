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
- `Shared engine code`
- `Unclear`

`Unclear` means you cannot tell even after the rules below. It is not a bin for code that is generic: generic code
has its own category, `Shared engine code`.

Library code (encryption, image decoding, JSON, ImGui, audio codecs) is filtered out before the dossier is built, so
it should not appear. If a library routine slips through, answer `Unclear` and say "library".

## Choosing between the close ones

- **A menu that belongs to one mode is that mode.** A Diamond Dynasty card screen is `Online and Diamond Dynasty`;
  an Options screen is `Menus and UI`. Ask what the *data* is for, not what the screen is made of.
- **Generic machinery is `Shared engine code`.** Containers, list and tree helpers, string buffers, allocators,
  memory and file plumbing, maths and hashing are `Shared engine code` wherever they are called from. They are not
  `Menus and UI`: that category is for code that draws or drives an actual screen, menu, button or layout.
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
   - `string`: `evidence` quotes, verbatim **inside double quotation marks**, a string from that function's own
     `strings:` line, and the quote has to name the aspect ("DIAMOND DYNASTY", "FRANCHISE", "crowd", "pitch",
     "SWING"...). The machine matches the quoted text against this function's strings as whole words and ignores any
     game word elsewhere in the sentence, so a remark like "this looks like a menu helper" proves nothing.
   - `callee`: `evidence` names an address from that function's `calls:` line and says what that callee does, from
     its role in brackets, that makes the aspect apply. The machine checks that the address is a direct callee **and
     that the callee itself has a label**. Calling a function nobody has labelled is not evidence: those rows were
     right about half the time and are rejected.
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
   A `known:` line that carries a `read role` (the function's body was read earlier and this is what that read
   concluded) is a **lead, not evidence**: it may steer which aspect you look for, and it saves you working out what
   the body does, but the evidence you cite must still be this function's own quoted string, a `class:` string, or a
   labelled callee. The same holds for a `map role` or a `name` in that line.
4. Confidence 0.0 to 1.0. Use 0.9+ only when a string names it outright.
5. Write **only** the output file named in the task. Do not modify the dossier, the map index or anything else.

## Output format

One JSON object per line:

```json
{"addr":"0x7000ac04d0","aspect":"Online and Diamond Dynasty","confidence":0.9,"evidence":"uses \"PLR_FE\" card entry","basis":"string"}
{"addr":"0x7000123456","aspect":"Audio","confidence":0.6,"evidence":"class method string \"AUDIO_MIX_ROW\" next to \"AUDIO_BUS\": the class mixes audio","basis":"class"}
```
Keep each `evidence` under 200 characters.
