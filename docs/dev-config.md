# Dev harness

The retail game kept its engine's dev-config system. At boot it reads `BOOT/CONFIG_MAIN_USER.TXT`
from the RomFS if that file exists, and otherwise `BOOT/CONFIG_MAIN.TXT`. `#` lines are comments. A
bare line turns a boolean option on (case-insensitive). `KEY=VALUE` lines set values. Options are
matched by a 32-bit hash, so the names appear nowhere in the binary. The names were recovered by
reversing the hash (a custom ELF-style hash followed by `h*0x9E3779B7 + ~h*0x61C88641`), collecting
every hash constant the retail code passes to the three config-query functions (319 call sites, 109
unique hashes), and brute-forcing candidates until 27 matched. The rest are options not named yet,
or other lookups that share the hash function.

**The harness:** `game/romfs/BOOT/CONFIG_MAIN_USER.TXT` containing

```
AIvAI
GameOnly
```

boots the game straight into an AI-vs-AI exhibition without touching the menus, and needs no input.
AIvAI hands both teams to the AI once a game session starts; GameOnly tells the boot flow to start
a game.

## Live options

| Option | Hash | What it does | Named? | Sites |
|---|---|---|---|---|
| `GameOnly` | `0xC6F7ECA5` | Boots straight into a game, skipping menus and the title screen (confirmed). | | 12 |
| `AIvAI` | `0xAA21F9C5` | AI controls both teams in a game session (confirmed). | ✅ | 3 |
| `OpenBetaDemo` | `0x21108949` | Queried across boot and gameplay; the open-beta/demo switch. | | 53 |
| `StartupMovies` | `0x267A2101` | Gates the boot intro movies. | | 1 |
| `FastPlay` | `0x875D5965` | Faster gameplay pacing. | ✅ | 1 |
| `FastLoad` | `0x3DFD2037` | Faster loading. | | 2 |
| `hrderbyOnly` | `0x07BDBC05` | Home Run Derby only. | | 7 |
| `ForceBootflow` | `0x96C88199` | Forces the boot flow. | | 1 |
| `ForcePlayGo` | `0x68452829` | Forces play-go (straight to gameplay). | | 4 |
| `NoCrowd` | `0x5B29C6D7` | No crowd rendering/audio. | | 1 |
| `NoIdle` | `0xA743410D` | No idle behavior. | | 1 |
| `NoWarmUp` | `0x1DB0461F` | Skips warm-up. | | 2 |
| `NoTTY` | `0x4F35A145` | No developer TTY output. | | 2 |
| `NoDOF` | `0x01161AA3` | Depth of field off. | ✅ | 1 |
| `NoTips` | `0x8333DD01` | No loading-screen tips. | ✅ | 2 |
| `CatcherView` | `0x4FFFBFD9` | Catcher view camera. | ✅ | 2 |
| `DisableUIElem` | `0xEAB3C09D` | Disables UI elements. | ✅ | 1 |
| `DisableJumboBink` | `0x6CFC5DB1` | No Bink movies on the jumbotron. | ✅ | 1 |
| `AlwaysDelayService` | `0x8D9D830D` | Always delays a service call. | | 2 |
| `DebugMatchupStats` | `0xE9154801` | Debug matchup-statistics overlay. | | 1 |
| `TestStorylines` | `0xA53B6861` | Storylines test path. | | 1 |
| `Savedata_Compression_Test` | `0x3EEB7277` | Save-data compression test. | | 2 |
| `getstadiumdata` | `0x0E1C0855` | Stadium-data action word. | ✅ | 6 |
| `Tutorial` | `0x35C16BC7` | Tutorial path. | | 1 |
| `Mobile` | `0x1020EF0D` | Mobile-platform paths. | | 14 |
| `pregame` | `0xF29AFC8D` | Pregame state. | | 1 |

"Sites" is how many places in the retail code pass the hash to one of the three config-query
functions. The hashes are the values the game compares config flags against. "Named?" means the
option appears (commented out) in CONFIG_MAIN.TXT itself.

## Named in CONFIG_MAIN.TXT but compiled out

Their handlers are gone from the retail binary; uncommenting them in CONFIG_MAIN.TXT does nothing.

| Option | CONFIG_MAIN.TXT | Why it does nothing |
|---|---|---|
| `RunForever` | yes; in CScorer | No retail code queries its hash. |
| `DoPlayInit` | yes; in PlayInit | No retail code queries its hash. |
| `Inning`, `InnHalf`, `Outs`, `Strikes`, `Balls`, `HomeScore`, `AwayScore` | yes; in PlayInit | `KEY=VALUE` lines for DoPlayInit's scenario; the scenario itself is compiled out. |
| `UseAutoHit`, `HitAzimuth`, `HitIncline`, `HitSpeed` | yes; in Autohit | These feed DoPlayInit's scenario, which is compiled out. |
| `NoWad`, `NoHost` | yes; in FileSystems | No retail code queries their hashes. |
| `FileSys=ROM`, `SoundFileSys=ROM` | yes; in FileSystems | `KEY=VALUE` options; no retail code queries these hashes. |
| `world=ps3/stadiums/sf`, `rig=day` | yes; in world | `KEY=VALUE` options for the PS3-era sandbox; no retail code queries them. |
| `NoJumboMips` | yes; in Jumbotron | No retail code queries its hash. |
| `FlyCamToggle` | yes; in Graphics | No retail code queries its hash. |

Flag values, not options: the constants `1`, `5`, `100` and `255` in the query table are the values
the game compares config flags against, not option names.

Watch for fake matches when extending the table: short common words collide with the hash. One
candidate in this set looked plausible and was not.
