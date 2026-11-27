"""Make a RomFS override that changes how many tokens a new Road to the Show player starts with (offline careers).

    python -I mods/rtts-start-tokens/rtts_start_tokens.py N --romfs <game romfs folder> --out <override folder>

Then run the game with MLB_ROMFS_OVERRIDE=<override folder>. The installed game files are not touched, and the output
holds game data, so keep it under work/ (never in git).

The game loads FRONTEND/RTTS/ATTRIBUTECATEGORIES.XML (f_700040d340) into a table at *(0x7002280f08), one u16 per
play style: <Playstyle id="0|1|2" tokens="..."> is pitcher, two-way and position player (50, 75, 50 as shipped). The
creation command f_7000bc0970 gives the player that number, and the upgrade screens work on a copy of it that their
commit writes back, so a change made here reaches every copy. Changing the player's record in memory while such a
screen is open does not. A career that already exists keeps its own count.
"""
import argparse
import re
import sys
from pathlib import Path

REL = Path("FRONTEND", "RTTS", "ATTRIBUTECATEGORIES.XML")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tokens", type=int)
    ap.add_argument("--romfs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if not 0 <= a.tokens <= 60000:
        sys.exit("tokens: 0 to 60000 (the count is 16-bit, up to 65535, and not every path that adds earned tokens caps it)")
    source, target = a.romfs / REL, a.out / REL
    if source.resolve() == target.resolve():
        sys.exit("--out must not be the game's romfs folder")
    data = source.read_bytes()
    new, n = re.subn(rb'(<Playstyle id="[012]" tokens=")\d+(")', rb"\g<1>%d\g<2>" % a.tokens, data)
    if n != 3:
        sys.exit(f"expected 3 play styles in {source}, found {n}: nothing written")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(new)
    print(f"{target}: 3 play styles start with {a.tokens} tokens")


if __name__ == "__main__":
    main()
