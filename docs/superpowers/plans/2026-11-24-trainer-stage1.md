# In-game trainer, stage 1: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A panel inside the running game that sets balls, strikes, outs and scores, jumps to a later inning, and saves
and replays situations, switched on in a new F1 "Trainer" tab.

**Architecture:** Four units from the spec: game access (the only code with addresses), rules (a thread-safe state
machine ticked once per presented frame), an ImGui panel that only sends requests, and settings rows. Stage 1 writes
memory only; no code patches.

**Tech Stack:** C (gnu11) and C++17 in `runtime/`, Dear ImGui, clang, a standalone C test program.

**Spec:** `docs/superpowers/specs/2026-11-24-trainer-design.md`. Stages 2 to 4 get their own plans after this one has
run live.

## Global Constraints

- Game version 1.0.20 only; any other build shows the trainer as unavailable.
- Off by default (`MLB_TRAINER=0`). Off: no game memory is read or written and no game input is changed.
- Every setting is a row in `runtime/mlb/cfg.c` (which also makes it a command-line flag). No `cfg`/`getenv` lookup in
  a per-draw or per-call path: re-read only when `cfg_version()` changes.
- `recomp/` unchanged. MLB code in `runtime/mlb/`. Edits in `runtime/gfx/` carry a `// fastball:` comment.
- Offline only. No game code or data in git.
- Panel text contrast at least 7:1 (4.5:1 floor) over the panel at its lowest opacity, even on a white picture; rows at
  least 24 px high at 720 lines.
- Keys: F2 show/hide, F3 save, F4 replay. Controller: both stick clicks.
- Commits: Conventional Commit types, Sky Miles as author, SSH-signed, the session's Co-Authored-By line.
- Another session may be editing the main checkout and running the game: work in a worktree, and take
  `mkdir D:/AI/Apps/mlbts-native/work/game.lock` before any game run (remove it afterwards).

## Review Focus

1. The match ends or is quit while an inning jump or a confirmation is pending: it is dropped, nothing is written
   (Task 2, `test_match_end_drops_pending`).
2. `trainer.txt` is hand-edited or cut off: bad lines are ignored, good ones load (Task 2, `test_bad_slot_lines`).
3. Replaying a situation from an earlier inning: score and count come back, the panel says the inning cannot go back
   (Task 2, `test_load_earlier_inning`).
4. Two trainer keys set to the same key: all three fall back to F2/F3/F4 (Task 2, `test_duplicate_keys`).
5. F1 opened while the panel is up: the panel closes and the game gets no leaked button (Task 2,
   `test_menu_closes_panel`; the held-button half is the existing latch in `hid.c`, checked live in Task 5).

---

## File structure

| File | Role |
|---|---|
| `runtime/mlb/trainer_game.c`, `.h` | addresses, checked reads and writes |
| `runtime/mlb/trainer.c`, `.h` | requests, confirmation, inning jump, slots, keys, visibility, test commands |
| `runtime/gfx/ui/trainer_ui.cpp`, `.h` | panel, mark, keys |
| `runtime/gfx/ui/trainer_theme.h` | colours and sizes, plain C so the test can read them |
| `tools/trainer_test.c` | host test, no game |
| modified | `runtime/mlb/cfg.c`, `runtime/mlb/hid.c`, `runtime/gfx/ui/menu.cpp`, `menu_win.cpp`, `menu.h` |
| docs | `docs/trainer.md`, README fork-features row |

---

### Task 1: Worktree, test program and game access

**Files:** Create `runtime/mlb/trainer_game.h`, `runtime/mlb/trainer_game.c`, `tools/trainer_test.c`.

**Interfaces — produces:**

```c
typedef enum { TR_OK, TR_WRONG_VERSION, TR_NO_MATCH, TR_UNEXPECTED, TR_OUT_OF_RANGE } TrStatus;
typedef enum { TR_AWAY_SCORE, TR_HOME_SCORE, TR_BALLS, TR_STRIKES, TR_OUTS, TR_HALF, TR_FIELD_COUNT } TrField;
typedef struct { int v[TR_FIELD_COUNT]; } TrCount;
TrStatus tr_game_init(const char *build);
void tr_game_set_slots(uint64_t count_slot, uint64_t teams_slot, uint64_t settings_slot);  // tests
TrStatus tr_count_read(TrCount *out);
TrStatus tr_count_write(TrField f, int value);
int tr_batting_side(void);            // 0 or 1, -1 unknown
int tr_game_mode(void);               // settings key 19, -1 unknown
const char *tr_status_text(TrStatus s);
```

Values (spec; evidence in `tools/scenario.py` and `known-functions.md`):

| What | Chain |
|---|---|
| count object O | `g = u64[0x700227e6b8]; O = u64[g]`; u32 at `O+0x8` away, `+0xc` home, `+0x10` balls, `+0x14` strikes, `+0x18` outs, `+0x20` half index |
| batting side | `t = u64[0x7003aeb728]; b = u64[t+0x20]`; byte `b+0x124` |
| game mode | `s = u64[0x7004651350]`; byte `s+0x3e+19` |

Ranges. Read accepts balls 0..4, strikes 0..3, outs 0..3 (transitions), scores 0..99, half 0..199; anything else is
`TR_UNEXPECTED`. Write accepts balls 0..3, strikes 0..2, outs 0..2, same scores and half. Every pointer step is
checked with `mem_guest_readable`; a null or unreadable step is `TR_NO_MATCH`.

- [ ] **Step 1:** Make the worktree on branch `feat/trainer` at `.claude/worktrees/trainer` with
  superpowers:using-git-worktrees, and join the shared `work/` as the other worktrees do:
  `cmd //c "mklink /J .claude\\worktrees\\trainer\\work D:\\AI\\Apps\\mlbts-native\\work"`.
- [ ] **Step 2:** Write `tools/trainer_test.c`. Header comment gives the command, in the style of
  `tools/harness_parse_test.c`:

```bash
"C:/Program Files/LLVM/bin/clang.exe" -O1 -Wall -std=gnu11 -D_CRT_SECURE_NO_WARNINGS -I runtime/mlb -I runtime/core \
  -I runtime/gfx -o work/scratch/trainer_test.exe tools/trainer_test.c runtime/mlb/trainer_game.c && work/scratch/trainer_test.exe
```

  It defines `mem_guest_readable` (true inside its own fake blocks) and `rt_log`, builds a fake count object, team
  table and settings block, passes their addresses to `tr_game_set_slots`, and counts failed `CHECK`s (exit code).

```c
static void test_version(void) { CHECK(tr_game_init("1.0.15") == TR_WRONG_VERSION); CHECK(tr_count_read(&c) == TR_WRONG_VERSION);
                                 CHECK(tr_game_init("1.0.20") == TR_OK); }
static void test_read(void)    { /* fake: away 4, home 3, balls 3, strikes 2, outs 1, half 13 */
                                 CHECK(tr_count_read(&c) == TR_OK); CHECK(c.v[TR_BALLS] == 3 && c.v[TR_HALF] == 13); }
static void test_write(void)   { CHECK(tr_count_write(TR_OUTS, 2) == TR_OK); CHECK(fake_u32(0x18) == 2);
                                 CHECK(tr_count_write(TR_OUTS, 3) == TR_OUT_OF_RANGE); CHECK(fake_u32(0x18) == 2);
                                 CHECK(tr_count_write(TR_BALLS, -1) == TR_OUT_OF_RANGE); }
static void test_no_match(void){ /* O pointer 0, then unreadable */ CHECK(tr_count_read(&c) == TR_NO_MATCH);
                                 CHECK(tr_count_write(TR_BALLS, 1) == TR_NO_MATCH); }
static void test_garbage(void) { /* balls = 700 */ CHECK(tr_count_read(&c) == TR_UNEXPECTED);
                                 CHECK(tr_count_write(TR_BALLS, 1) == TR_UNEXPECTED); CHECK(fake_u32(0x10) == 700); }
static void test_side_mode(void){ CHECK(tr_batting_side() == 1); CHECK(tr_game_mode() == 5); }
```

- [ ] **Step 3:** Run the command. Expected: compile failure, `trainer_game.h` not found.
- [ ] **Step 4:** Implement the interface in `trainer_game.c`. A write first does a full read and refuses on any status
  but `TR_OK`.
- [ ] **Step 5:** Run again. Expected: `0 failed`, exit code 0.
- [ ] **Step 6:** Commit `feat(trainer): checked access to the match count` (the three files).

### Task 2: Rules

**Files:** Create `runtime/mlb/trainer.h`, `runtime/mlb/trainer.c`. Modify `tools/trainer_test.c` (add `trainer.c`
to the command).

**Interfaces — consumes** Task 1. **Produces** (all thread-safe, one `PlatMutex`):

```c
#define TR_SLOTS 3
typedef struct { TrStatus status; TrCount now; int enabled, visible, jumping, jump_target, needs_confirm, slot;
                 int used[TR_SLOTS]; TrCount slots[TR_SLOTS]; char message[96]; } TrView;
void trainer_init(const char *profile_dir);        // reads <profile_dir>/trainer.txt
void trainer_set_enabled(int on);                  // off: hidden, pending dropped, tick touches no game memory
void trainer_set(TrField f, int value);
void trainer_slot_select(int slot);
void trainer_slot_save(int slot);
void trainer_slot_load(int slot);
void trainer_jump(int half_index);
void trainer_cancel(void);
void trainer_confirm(int yes);
void trainer_toggle(void);                         // no effect while disabled
void trainer_menu_opened(void);                    // hides the panel
int  trainer_visible(void);                        // visible = has input focus
void trainer_tick(uint64_t now_ns);                // once per presented frame; the only place that writes the game
void trainer_view(TrView *out);
int  trainer_keys(const char *show, const char *save, const char *load, int vk[3]); // 0: clash, vk = F2,F3,F4
int  trainer_command(const char *cmd);             // test hook: show|hide|set <field> <n>|save <n>|load <n>|jump <half>|confirm
```

Behaviour:

- Slot arguments in C are 0..2; the file, the panel and test commands number them 1..3.
- A change of the read status is logged once (`trainer: <tr_status_text>`), not every tick.
- Requests queue; the next tick applies them and the tick after logs `trainer: <field> = <want>, read back <got>`.
  Field names: `away`, `home`, `balls`, `strikes`, `outs`, `half`.
- Confirmation: when `tr_game_mode()` is 1 (Season), 3 (Franchise) or 4 (Road to the Show), the first change of a
  match is held with `needs_confirm`; yes applies it and later ones, no drops it. A tick that sees any status but
  `TR_OK` forgets the confirmation and drops everything pending.
- Slots: `trainer.txt`, one line per used slot, `slot <1..3> <away> <home> <balls> <strikes> <outs> <half>`, written on
  save; lines that do not parse or are outside the write ranges are skipped.
- Load: scores at once; then, for a later half index, a jump with balls, strikes, outs and scores applied after it;
  for the same one, everything at once; for an earlier one, everything but the inning, message
  `Inning not restored: the game cannot go back.`
- Jump (algorithm from `tools/scenario.py` `apply_one`, as a state machine; `cur` = half index, target `t > cur`):
  1. if the batting side is known and `t % 2 != side`: write outs 2, wait until the half index changes, wait 2.5 s;
  2. if `t > cur`: write half = `t - 1` and outs 2, wait until the half index is `t`, wait 2.5 s;
  3. apply the pending count.
  No timeout (the player may be making the out); message `Waiting for the next out.`; `trainer_cancel` stops it.
  `t <= cur` is refused with `The game cannot go back an inning.` (equal: nothing to do).

- [ ] **Step 1:** Add tests (each starts from a fresh fake match in mode 5 and an empty temp profile; `tick(s)` calls
  `trainer_tick` at time `s` seconds):

```c
static void test_set_applies_on_tick(void) { trainer_set(TR_BALLS, 3); CHECK(fake_u32(0x10) == 0); tick(1); CHECK(fake_u32(0x10) == 3); }
static void test_disabled_touches_nothing(void) { trainer_set_enabled(0); trainer_set(TR_BALLS, 3); tick(1);
    CHECK(fake_u32(0x10) == 0); CHECK(g_readable_calls == 0); trainer_toggle(); CHECK(!trainer_visible()); }
static void test_confirm_in_franchise(void) { fake_mode(3); trainer_set(TR_OUTS, 2); tick(1); trainer_view(&v);
    CHECK(v.needs_confirm && fake_u32(0x18) == 0); trainer_confirm(1); tick(2); CHECK(fake_u32(0x18) == 2);
    trainer_set(TR_BALLS, 1); tick(3); CHECK(fake_u32(0x10) == 1); }
static void test_confirm_no_drops(void) { fake_mode(1); trainer_set(TR_OUTS, 2); tick(1); trainer_confirm(0); tick(2); CHECK(fake_u32(0x18) == 0); }
static void test_jump_same_side(void) { /* half 0, side 0, target 4 */ trainer_jump(4); tick(1);
    CHECK(fake_u32(0x20) == 3 && fake_u32(0x18) == 2); fake_set(0x20, 4); tick(2); tick(5); trainer_view(&v); CHECK(!v.jumping); }
static void test_jump_extra_transition(void) { /* half 0, side 0, target 3 */ trainer_jump(3); tick(1);
    CHECK(fake_u32(0x20) == 0 && fake_u32(0x18) == 2); fake_set(0x20, 1); fake_side(1); tick(2); tick(5);
    CHECK(fake_u32(0x20) == 2); fake_set(0x20, 3); tick(6); tick(9); trainer_view(&v); CHECK(!v.jumping); }
static void test_jump_back_refused(void) { fake_set(0x20, 6); trainer_jump(2); tick(1); trainer_view(&v);
    CHECK(!v.jumping && fake_u32(0x20) == 6); CHECK(strstr(v.message, "cannot go back")); }
static void test_slot_roundtrip(void) { /* set fake 4,3,3,2,2,half 4 */ trainer_slot_save(0); tick(1); /* zero all but the half index */
    trainer_init(g_profile); trainer_slot_load(0); tick(2); CHECK(fake_u32(0x10) == 3 && fake_u32(0x8) == 4); }
static void test_load_earlier_inning(void) { /* slot saved at half 2, match now at half 8 */ trainer_slot_load(0); tick(1);
    CHECK(fake_u32(0x20) == 8 && fake_u32(0x10) == 3); trainer_view(&v); CHECK(strstr(v.message, "Inning not restored")); }
static void test_bad_slot_lines(void) { write_profile("slot 1 4 3 3 2 9 4\nslot 9 0 0 0 0 0 0\njunk\nslot 2 1 0 0 0 1 2\nslot 3 5\n");
    trainer_init(g_profile); trainer_view(&v); CHECK(!v.used[0] && v.used[1] && !v.used[2]); }
static void test_match_end_drops_pending(void) { trainer_jump(4); tick(1); fake_match_gone(); tick(2); fake_match_back();
    fake_set(0x20, 4); tick(9); trainer_view(&v); CHECK(!v.jumping && fake_u32(0x10) == 0); }
static void test_duplicate_keys(void) { int vk[3]; CHECK(trainer_keys("F5","F6","F7",vk) && vk[0] == 0x74);
    CHECK(!trainer_keys("F3","F3","F4",vk)); CHECK(vk[0] == 0x71 && vk[1] == 0x72 && vk[2] == 0x73); }
static void test_menu_closes_panel(void) { trainer_toggle(); CHECK(trainer_visible()); trainer_menu_opened(); CHECK(!trainer_visible()); }
static void test_command(void) { CHECK(trainer_command("set strikes 2")); tick(1); CHECK(fake_u32(0x14) == 2); CHECK(!trainer_command("set nonsense 1")); }
```

- [ ] **Step 2:** Run. Expected: compile failure, `trainer.h` not found.
- [ ] **Step 3:** Implement `trainer.c`.
- [ ] **Step 4:** Run. Expected: `0 failed`.
- [ ] **Step 5:** Commit `feat(trainer): situations, inning jumps and confirmation`.

### Task 3: Settings rows and the F1 tab

**Files:** Modify `runtime/mlb/cfg.c` (table `metas`), `runtime/gfx/ui/menu.cpp` (`kTabNames`, `TAB_*`, a
`tab_trainer`, the switch near line 960).

**Interfaces — produces** cfg keys:

| Key | Default | Values | Apply |
|---|---|---|---|
| `TRAINER` | `0` | `0\|1` | LIVE |
| `TRAINER_CORNER` | `top_right` | `top_left\|top_right\|bottom_left\|bottom_right` | LIVE |
| `TRAINER_OPACITY` | `90` | `85..100` | LIVE |
| `TRAINER_KEY_SHOW` / `_SAVE` / `_LOAD` | `F2` / `F3` / `F4` | `F2\|F3\|F4\|F5\|F6\|F7` | LIVE |

- [ ] **Step 1:** Add the rows with a comment naming `trainer.c`.
- [ ] **Step 2:** Add `TAB_TRAINER` after `TAB_ADVANCED` (existing tab numbers keep), with `opt_toggle`,
  `opt_choice`, `opt_slider` rows for every key. The toggle's description: "A panel over the running match for the
  count, outs, score, inning and saved situations. F2 or both stick clicks open it. Offline only; changes made in a
  Season, Franchise or Road to the Show match can be saved with it." On another game version call
  `opt_unavailable("The trainer knows game version 1.0.20 only")`.
- [ ] **Step 3:** Build from the worktree root:
  `python -I tools/build.py --out work/build_trainer --exefs work/build/game/exefs --portable`. Expected: exit 0,
  `work/build_trainer/mlb.exe` newer than the sources.
- [ ] **Step 4:** `work/build_trainer/mlb.exe --help | grep -i trainer`. Expected: all six settings.
- [ ] **Step 5:** Commit `feat(trainer): settings and the F1 Trainer tab`.

### Task 4: Panel and input

**Files:** Create `runtime/gfx/ui/trainer_theme.h`, `trainer_ui.h`, `trainer_ui.cpp`. Modify `menu.cpp`
(`menu_overlay_frame`, `push`, `change_open`), `menu_win.cpp` (`menu_window_msg`), `runtime/mlb/hid.c` (`poll`),
`tools/trainer_test.c`.

**Interfaces — consumes** Task 2 and 3. **Produces:**

```c
// trainer_theme.h (C): 0xRRGGBB
#define TR_COL_BG 0x0A140F
#define TR_COL_TEXT 0xF0F0F0
#define TR_COL_ACCENT 0xEDC254
#define TR_COL_DIM 0xC8C8C8
#define TR_ALPHA_MIN 85
#define TR_ROW_PX_1080 36
// trainer_ui.h
void trainer_ui_frame_begin(uint64_t frame);          // cfg refresh on version change, test commands, trainer_tick
int  trainer_ui_wants_draw(void);
void trainer_ui_draw(float scale, uint32_t w, uint32_t h);
int  trainer_ui_key(unsigned vk);                     // window thread; 1 when it was a trainer key
```

Behaviour:

- `menu_overlay_frame` calls `trainer_ui_frame_begin` before its early return, and does not return early while
  `trainer_ui_wants_draw()`. `trainer_init(rt_config()->profile)` and `tr_game_init(rt_game_build)` run on first use.
- Panel (spec sketch): title, "F2 hide"; rows Balls, Strikes, Outs, Away, Home with `<` `>`; "Jump to inning" with
  inning, top/bottom and `go`, or the message and `cancel`; slot selector with save and load, showing
  `3-2, 2 out, 4-3, bottom 7`; the confirmation as two buttons in the panel; when status is not `TR_OK`, only
  `tr_status_text`. No tab bar in stage 1. A `TRAINER` mark shows in the corner while a jump is pending and the panel
  is hidden.
- While visible: `push` and `menu_window_msg` forward keys and mouse as for the open menu; `pad_events` runs; Esc or
  pad B hides. `change_open(1)` calls `trainer_menu_opened`.
- `hid.c` `poll`: with `TRAINER` on, both stick clicks going down together (not while the menu or text entry is open)
  calls `trainer_toggle`; `open` also includes `trainer_visible()`, so the existing latch hides input from the game.
  With it off, the sticks are untouched.
- Key hook: with `TRAINER` on, `trainer_ui_key` handles the three configured keys (panel visible or not), ignoring
  auto-repeat; F3/F4 act on the selected slot.
- Under `MLB_DEV_HARNESS` only: `MLB_TRAINER_TEST="<frame>:<command>;..."` runs `trainer_command` at those frames.

- [ ] **Step 1:** Add to the test:

```c
static void test_contrast(void) { uint32_t over_white = blend(TR_COL_BG, 0xFFFFFF, TR_ALPHA_MIN);
    CHECK(contrast(TR_COL_TEXT, over_white) >= 7.0); CHECK(contrast(TR_COL_ACCENT, over_white) >= 7.0);
    CHECK(contrast(TR_COL_DIM, over_white) >= 7.0); CHECK(TR_ROW_PX_1080 * 720 / 1080 >= 24); }
```

  (`contrast` is the WCAG 2.2 relative-luminance ratio; `blend` mixes in sRGB values.)
- [ ] **Step 2:** Run. Expected: compile failure on the missing header.
- [ ] **Step 3:** Add `trainer_theme.h`; run; expected `0 failed`. If a ratio fails, raise `TR_ALPHA_MIN` (and the
  cfg range) or lighten the colour; never lower the threshold.
- [ ] **Step 4:** Implement the panel and the input changes.
- [ ] **Step 5:** Build as in Task 3. Expected: exit 0, no new warnings from the new files.
- [ ] **Step 6:** Commit `feat(trainer): in-game panel, keys and pad`.

### Task 5: Live check and documents

**Files:** Create `docs/trainer.md`. Modify `README.md` (fork features table),
`.claude/skills/mlbts-game-code/references/known-functions.md` (anything learned).

- [ ] **Step 1:** Take the lock; `python -I tools/game.py create trainer --exe D:/AI/Apps/mlbts-native/.claude/worktrees/trainer/work/build_trainer/mlb.exe`.
  Boot straight into an AI-vs-AI match with a hidden window, as `docs/dev-config.md` "Headless test runs" describes.
  First check the log has no `audout: no output device`.
- [ ] **Step 2:** Run with `MLB_TRAINER=1` and test commands after the first pitch: `set balls 3`, `set strikes 2`,
  `set outs 2`, `set away 4`, `set home 3`. Expected: five `read back` lines with want equal to got, and
  `tools/scenario.py`'s memory reader agreeing.
- [ ] **Step 3:** `save 1`, then five times: change the count, `load 1`. Expected: 5 of 5 read back the saved values.
- [ ] **Step 4:** `jump` two half innings ahead with each parity. Expected: the half index and the batting side match
  (`expected_side` in `scenario.py`), and the match plays on for 60 s.
- [ ] **Step 5:** Stay at the main menu with the trainer on. Expected: the panel reports no match and writes nothing.
  If the count object reads as valid there, add a condition to `tr_count_read` that tells a menu from a match, with a
  test, and record the evidence.
- [ ] **Step 6:** Off check: three runs each of `work/build/mlb.exe` and the new exe with `MLB_TRAINER=0`, same match,
  uncapped; `tools/perf_summary.py`. Expected: no `trainer:` log lines and frame times within the run-to-run spread.
  Write the numbers in `docs/trainer.md`.
- [ ] **Step 7:** One `MLB_SHOT` picture with the panel open. Say first that the tests cannot judge layout or how it
  sits over the HUD; report what the picture shows.
- [ ] **Step 8:** Ask the owner to try F2, the stick clicks and F1-while-open with a controller, which no headless run
  covers. Release the slot and remove the lock.
- [ ] **Step 9:** Write `docs/trainer.md` (what it does, how to use it, what else changes, how it was checked, what was
  not) and the README row. Commit `docs(trainer): usage and live checks`.

Merging `feat/trainer` into `main` waits for the owner (superpowers:finishing-a-development-branch).
