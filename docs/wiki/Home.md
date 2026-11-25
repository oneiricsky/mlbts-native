This is the research wiki for a personal fork of [Fastball](https://github.com/sam110411/fastball), the native Windows port of MLB The Show 26 for Switch. The fork exists to find out why the game stalls and where the port loses time, and to build tools for that work. The product is what we learn plus working tools, not releases. Fastball itself, its releases and its issues are upstream's.

### Specs

```
OS: Windows 11 Education (26H2) x86_64
CPU: 12th Gen Intel(R) Core(TM) i5-12400F
GPU: AMD Radeon RX 6700 XT (12 GB)
RAM: 32GB DDR4
```

## Tag legend

Throughout the wiki, functions are tagged with the following letters to indicate how each one was mapped:

| Tag | Meaning |
|---|---|
| C | string, symbol, import |
| I | inferred via shape of code or call graph |
| H | inferred via neighbours |

---

## How complete the map is

![Function map coverage]({{completeness.svg}})

<br>


![Functions by aspect of the game]({{aspects.svg}})


## How far the theme labels have got

![Theme labels accepted]({{theming.svg}})

Two independent reads and an evidence check have yielded 252 individual function labels so far. The continuation
accepted 160 labels across 388 functions. See the accepted labels by aspect and the evidence rules on
[Theming progress](Theming-progress).

## Table of Contents

{{toc}}


## Rules the work follows

Find the cause and show evidence before changing code. Ask why the game does a piece of work before trying to make it cheaper. Give numbers before and after, with the run count. No game files, keys or extracted assets are ever committed.
