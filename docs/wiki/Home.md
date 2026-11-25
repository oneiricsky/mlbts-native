This is the research wiki for a personal fork of [Fastball](https://github.com/sam110411/fastball), the native Windows port of MLB The Show 26 for Switch. The fork exists to find out why the game stalls and where the port loses time, and to build tools for that work. The product is what we learn plus working tools, not releases. Fastball itself, its releases and its issues are upstream's.

Everything here was measured on one PC (an i5-12400F with an RX 6700 XT), game version 1.0.20 unless a page says otherwise. Upstream's own numbers come from a Ryzen 5 5600X with an RTX 3060 Ti and are marked where they appear. Each page says how many runs a number comes from. Where something is a guess, the page says so.

## What has been found

| Problem | Cause | State |
|---|---|---|
| [Freeze before every pitch](Walk-up-freeze) | The game baked its stadium lighting twice in a row | Fixed upstream in 0.2.0; our write-up and patch measurements |
| [Freeze at match start](Match-start-freeze) | The game spends 0.7 s proving empty space has no edges | Fixed on a research branch, not merged |
| [Stalls when something loads](Load-stalls) | Four separate causes, one of them ours | Ours fixed; the rest open |
| [Frame rate in heavy scenes](Frame-rate-and-GPU-waits) | The game waits for the GPU, so costs add up instead of overlapping | Explained, partly improved |
| [PS5 textures and the yellow face](PS5-textures) | A compute pass read the wrong part of a bigger texture | Fixed; still opt-in until more heads are checked |
| [Open upstream bugs](Upstream-bug-research) | Four issues read and ranked | Research only, nothing run |

## How complete the map is

![Function map coverage](completeness.svg)

The tags are C for a string, symbol or import, I for the shape of the code or the call graph, and H for neighbours
only; the lower bar counts the bodies that were read.

![Functions by aspect of the game](aspects.svg)

The labels come from the theme the region pages give each 256 KB window, so a function is grouped by its window
rather than by anything read in its own body. Totals and the per-window census are on [Function map](Function-map)
and [Function census](Function-census).

## How it is built and measured

| Page | Covers |
|---|---|
| [How the port works](How-the-port-works) | the layers, how the game's code becomes C, how graphics and frame timing work |
| [The game binary](The-game-binary) | what the game's code is made of and where things sit in it |
| [Game state machine](Game-state-machine) | the 12 game-flow states: what each vtable slot does, sub-state tables, how a play moves through them, with four detail pages |
| [Region A](Region-A) to [Region F](Region-F) | the game's `main` code in six address ranges, with key functions |
| [Function map](Function-map) | every function of `main` and `sdk`: the census, the per-region registers, and what is known about each |
| [Dev harness and measuring](Dev-harness-and-measuring) | how a run is set up, and the rules for comparing two builds |
| [Tools and the code map](Tools-and-the-code-map) | the scripts that index the code and how to rebuild them |
| [History and open questions](History-and-open-questions) | what is not settled |
| [Start here](Start-here) | the entry point for a new session; the game-code and region pages are generated from the repo skill `mlbts-game-code` |

## Rules the work follows

Find the cause and show evidence before changing code. Ask why the game does a piece of work before trying to make it cheaper. Give numbers before and after, with the run count. No game files, keys or extracted assets are ever committed.
