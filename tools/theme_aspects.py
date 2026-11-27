"""The aspects the theme pipeline labels, and the words that name each one.

The list is the wiki's (`tools/wiki_completeness.py`, `ASPECT_OF_THEME`). The keywords are the evidence vocabulary:
the adjudicator looks for them in a quoted string, in the role text of a cited callee, or in an `operations` sentence.
A keyword is matched as a whole word on lower case text, so `bat` no longer hits `battle`; keep the entries specific
(`team` alone still matches half the game and is not in the list).

A keyword hit is not proof, it is a machine-checkable form of evidence. The hand audit in `theme_audit.py` is what
turns it into precision numbers, per evidence strength.
"""
import re

ASPECTS = [
    "Online and Diamond Dynasty",
    "Road to the Show",
    "Franchise, league and roster",
    "Gameplay: pitching",
    "Gameplay: batting",
    "Gameplay: fielding",
    "Gameplay: baserunning",
    "Gameplay: in-play",
    "Menus and UI",
    "Presentation and animation",
    "Graphics and textures",
    "Audio",
    "Data and serialization",
    "Stats and records",
    "Shared engine code",
]

KEYWORDS = {
    "Online and Diamond Dynasty": [
        "diamond dynasty", "diamond", "dynasty", "dd_", " dd ", "stub", "pack", "marketplace",
        "collection", "battle royale", "br_", "co-op", "coop", "matchmaking", "vault", "gamer card",
        "gamer_card", "leaderboard", "conquest", "showdown", "mission", "program", "online", "network",
        "session", "server", "login", "auth", "commerce", "entitlement", "postgame summary",
        "card entry", "card", "challenge",
    ],
    "Road to the Show": [
        "road to the show", "rtts", "career", "create-player", "create_player", "player lock",
        "ballplayer", "my player", "archetype", "perk", "development", "appearance", "equipment",
        "amateur", "player creation",
    ],
    "Franchise, league and roster": [
        "franchise", "league", "roster", "trade", "contract", "salary", "budget", "general manager",
        "team strategy", "prospect", "standings", "playoff", "schedule", "free agent", "hall of fame",
        "award", "season", "draft",
    ],
    "Gameplay: pitching": [
        "pitch", "pitcher", "mound", "bullpen", "rotation", "release", "repertoire", "pickoff", "balk",
        "umpire", "strike zone", "ball/strike", "throwing",
    ],
    "Gameplay: batting": [
        "bat", "swing", "hitter", "plate", "pci", "timing", "contact", "bunt", "check swing", "at-bat",
        "at bat", "hit", "power", "batting",
    ],
    "Gameplay: fielding": [
        "fielder", "catch", "dive", "cutoff", "relay", "fly ball", "groundball", "ground ball",
        "defensive", "fielding", "arm strength", "throwing", "throw",
    ],
    "Gameplay: baserunning": [
        "runner", "baserun", "steal", "leadoff", "lead", "slide", "tag", "pickoff", "base",
    ],
    "Gameplay: in-play": [
        "in-play", "in play", "play result", "hit and run", "ball in play", "fielder choice", "out",
        "safe", "inning", "live ball", "play state", "pitch result",
    ],
    "Menus and UI": [
        "menu", "screen", "button", "widget", "list", "row", "tab", "focus", "cursor", "popup",
        "dialog", "text", "layout", "input", "selection", "scroll", " ui ", "gui", "imgui", "page",
        "panel", "option", "label", "checkbox", "slider",
    ],
    "Presentation and animation": [
        "animation", "anim", "camera", "replay", "cutscene", "presentation", "overlay", "stadium",
        "lighting", "sky", "jumbotron", "commentary", "play event", "walkup", "walk-up", "batter up",
        "crowd",
    ],
    "Graphics and textures": [
        "texture", "shader", "mesh", "draw", "gpu", "nvn", "render", "vertex", "pixel", "material",
        "framebuffer", "decal", "model", "msaa", "bc7", "surface", "image", "sprite", "bloom",
        "shadow", "post-process",
    ],
    "Audio": [
        "audio", "sound", "music", "crowd", "organ", " pa ", "commentary", "mixing", "voice", "scream",
        "audout", "audren", "sfx", "bank", "stream", "volume", "speaker",
    ],
    "Data and serialization": [
        "json", "serialize", "deserialize", "save", "load", "parse", "reflect", "registration",
        "schema", "file", "read", "write", "buffer", "stream", "encoding", "zlib", "memory card",
        "compression", "archive",
    ],
    "Stats and records": [
        "stat", "record", "leaderboard", "training", "progress", "rating", "attribute", "percent",
        "history", "log", "score", "standings", "award",
    ],
    # generic engine machinery: containers, strings, memory, maths, file plumbing. The readers file this here
    # instead of under "Menus and UI", which used to absorb every list helper.
    "Shared engine code": [
        "vector", "container", "allocator", "memory pool", "string helper", "string buffer", "memcpy",
        "memset", "hash", "sort", "binary tree", "tree node", "linked list", "list node", "refcount",
        "reference count", "smart pointer", "generic", "template", "std::", "buffer", "stack frame",
        "math", "matrix", "quaternion", "random number", "crc", "checksum",
    ],
}

# how a word is looked up: lower case, whole words only, so "bat" does not hit "battle" and "out" not "route"
def hits(text, aspect):
    low = (text or "").lower()
    out = []
    for k in KEYWORDS.get(aspect, []):
        kw = k.strip().lower()
        if not kw:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", low):
            out.append(k)
    return out
