"""Guesses names for unnamed boot options by joining words (docs/dev-config.md, "Guessed names").

    python -I tools/config_guess.py [--control]

Each unnamed hash is tried against its own list: words from the functions that check it plus common switch words.
--control searches for hashes of random letters instead, to show how many hits chance alone gives. A hit is a
candidate only: read the code behind it before believing it. Needs tools/map_all.py to have run. Takes about 4 minutes.
"""
import bisect
import collections
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_options as c  # noqa: E402

INDEX = c.ROOT / 'work/map/index'
A, B = 0x9E3779B7, 0x61C88641

PRE = '''no force disable enable skip show hide debug test use only auto fast all do always never dump log print
allow ignore play run new old load save quick demo is has draw render max min set'''.split()
SUF = '''only off on mode test demo debug disable enable all info stats view log menu screen file path dir url server'''.split()
GEN = '''game games frontend fe boot flow bootflow movie movies video bink intro audio sound music crowd pa pbp commentary
speech vo voice jumbo jumbotron save savedata data load loading screen screens tips server net network online offline
login ui hud overlay camera cam fly replay presentation pres anim animation weather rain wind pitch pitching pitcher bat
batting batter swing field fielding stadium roster franchise career rtts season postseason spring training allstar derby
hrderby hr tutorial patch patching playgo stats memory mem heap profile texture shader shadow shadows dof blur bloom
effects fx time inning outs home away team teams player players umpire coach fans ai cpu user vs control controls pad
vibration rumble hitch warmup idle tty pregame postgame lineup lineups intros cutscene cutscenes story storylines
moments challenge dd diamond dynasty marketplace store cloud first run language english region country version build
retail dev qa e3 press kiosk attract fps framerate vsync wait delay timeout seed random error errors assert crash
watchdog hang wad wads file files cache preload stream streaming install trophy trophies achievements news online
service update check sync init settings options difficulty slider sliders injury injuries steals balks walks strikeouts
strikes balls fouls contact power speed physics ball flight trail catcher fielder runner runners base bases create'''.split()
PRE_B = [p.upper().encode() for p in PRE]
SUF_B = [s.upper().encode() for s in SUF]
GEN_B = [w.upper().encode() for w in GEN]


def inner(h):
    """The 28-bit ELF value behind a final option hash."""
    return ((h + B) // 2 * pow((A - B) // 2, -1, 2 ** 31)) % 2 ** 31


def feed(v, s):
    for ch in s:
        v = (v << 4) + ch
        g = v & 0xf0000000
        if g:
            v = (v & 0x0fffffff) ^ (g >> 24)
    return v


def context():
    """hash -> the words in the strings and read roles of the functions that check it."""
    _, used, _, per_hash = c.scan()
    starts = c.function_starts()
    text = collections.defaultdict(list)
    for name in ('function_strings.jsonl', 'roles.jsonl', 'roles_read.jsonl'):
        for line in (INDEX / name).read_text(encoding='utf-8').splitlines():
            r = json.loads(line)
            if r.get('module', 'main') == 'main':
                a = int(r['addr'], 16) - 0x7000000000
                text[a] += r.get('strings', [])[:60] + [r.get('role') or '']
    out = {}
    for h in used:
        words = []
        for site in per_hash[h]:
            for s in text[starts[bisect.bisect_right(starts, site) - 1]]:
                words += [w for w in re.findall(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+', s) if 2 <= len(w) <= 16]
        out[h] = [w.upper().encode() for w, _ in collections.Counter(w.lower() for w in words).most_common(120)]
    return out


def search(want, cw):
    vocab = list(dict.fromkeys(cw + GEN_B))
    found = set()
    tried = 0

    def check(state, parts):
        if state == want:
            found.add(parts)
    for hs, p in [(0, b'')] + [(feed(0, p), p) for p in PRE_B]:     # [prefix] word [word or suffix]
        for w in vocab:
            s1 = feed(hs, w)
            check(s1, (p, w))
            for q in SUF_B:
                check(feed(s1, q), (p, w, q))
            for w2 in vocab:
                check(feed(s1, w2), (p, w, w2))
            tried += 1 + len(SUF_B) + len(vocab)
    for s in SUF_B + PRE_B:
        check(feed(0, s), (s,))
    for a in cw[:60]:                                               # context word, word, suffix
        s1 = feed(0, a)
        for b in vocab:
            s2 = feed(s1, b)
            for d in SUF_B:
                check(feed(s2, d), (a, b, d))
            tried += len(SUF_B)
    return sorted(''.join(x.decode().capitalize() for x in t if x) for t in found), tried


def main():
    control = '--control' in sys.argv[1:]
    doc = c.documented()
    # the names found before this search (the doc's own CloudSaveUrl row came from it)
    known = {h for h, n in doc.items() if c.option_hash(n.encode()) == h and n != 'CloudSaveUrl'}
    total = hit = 0
    for h, cw in sorted(context().items()):
        if h in known:
            continue
        want = inner(h)
        if control:
            rnd = random.Random(h)
            want = feed(0, bytes(rnd.randrange(65, 91) for _ in range(rnd.randrange(7, 18))))
        names, tried = search(want, cw)
        total += tried
        if names:
            hit += 1
            print(f'0x{h:08X}', names, flush=True)
    print(f'options with a hit: {hit}; candidates {total}; matches expected by chance about '
          f'{total / 2 ** c.HASH_BITS:.1f}')


if __name__ == '__main__':
    main()
