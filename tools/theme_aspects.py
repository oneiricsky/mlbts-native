"""The aspects the theme pipeline labels, and the words that name each one.

The list is the wiki's (`tools/wiki_completeness.py`, `ASPECT_OF_THEME`). The keywords are the evidence vocabulary:
the adjudicator looks for them in a quoted string, in the role text of a cited callee, or in an `operations` sentence.
A keyword is a substring test on lower case text, so keep the entries specific: `team` alone matches half the game.

A keyword hit is not proof, it is a machine-checkable form of evidence. The hand audit in `theme_audit.py` is what
turns it into precision numbers, per evidence strength.
"""

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
}

# how a word is looked up: lower case, with spaces kept so " pa " does not match "pack"
def hits(text, aspect):
    low = " " + (text or "").lower() + " "
    return [k for k in KEYWORDS.get(aspect, []) if k in low]
