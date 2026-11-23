"""Build the GitHub wiki pages in work/wiki from the repo's own sources.

    python -I tools/wiki_build.py [--out work/wiki]

Sources (one place each, so the wiki never drifts from them):
  docs/wiki/*.md                                the hand-written findings pages and Home
  .claude/skills/mlbts-game-code/SKILL.md       -> Start-here
  .claude/skills/mlbts-game-code/references/*   -> How-the-port-works, The-game-binary, Known-game-functions,
                                                   Tracing-playbook, History-and-open-questions
  docs/map/regions/*.md                         -> Region-A ... Region-F
  docs/map/README.md                            -> Tools-and-the-code-map
Skill and map pages are generated: edit the source, not the wiki page. Wiki pages carry no front matter and no top
heading (GitHub shows the page name), and links between pages use the wiki's own page names.
Publishing is separate (tools/wiki_publish.py): this script only writes files.
"""
import argparse, os, re, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
SK = ROOT + "/.claude/skills/mlbts-game-code"

SKILL_PAGES = {
    "SKILL.md": "Start-here",
    "references/port-architecture.md": "How-the-port-works",
    "references/game-binary.md": "The-game-binary",
    "references/known-functions.md": "Known-game-functions",
    "references/tracing-playbook.md": "Tracing-playbook",
    "references/history-and-open-questions.md": "History-and-open-questions",
}
LINKS = {  # text in the source -> wiki page
    "references/port-architecture.md": "How-the-port-works",
    "references/game-binary.md": "The-game-binary",
    "references/known-functions.md": "Known-game-functions",
    "references/tracing-playbook.md": "Tracing-playbook",
    "references/history-and-open-questions.md": "History-and-open-questions",
    "known-functions.md": "Known-game-functions",
    "game-binary.md": "The-game-binary",
    "port-architecture.md": "How-the-port-works",
    "tracing-playbook.md": "Tracing-playbook",
}
REGIONS = {"A": "A-0x7000000000-0x70005fffff", "B": "B-0x7000600000-0x7000bfffff", "C": "C-0x7000c00000-0x7000ffffff",
           "D": "D-0x7001000000-0x70013fffff", "E": "E-0x7001400000-0x70017fffff", "F": "F-0x7001800000-end-and-sdk"}
BANNER = ("_This page is generated from `%s` in the repo by `tools/wiki_build.py`. Edit the source, not this page._\n\n")


def read(p):
    return open(p, encoding="utf-8").read()


def strip_front_and_title(t):
    t = re.sub(r"\A---\n.*?\n---\n", "", t, flags=re.S)
    return re.sub(r"\A\s*# [^\n]*\n+", "", t)


def relink(t):
    for src, page in sorted(LINKS.items(), key=lambda kv: -len(kv[0])):
        t = t.replace(f"`{src}`", f"[{page.replace('-', ' ')}]({page})")
    t = re.sub(r"`?docs/map/regions/\*\.md`?(?: \(A to F\))?", "the region pages ([A](Region-A), [B](Region-B), [C](Region-C), "
               "[D](Region-D), [E](Region-E), [F](Region-F))", t)
    t = re.sub(r"`docs/map/regions/([A-F])-[^`]*`", lambda m: f"[Region {m.group(1)}](Region-{m.group(1)})", t)
    t = re.sub(r"`docs/map/README\.md`[^|\n]*", "[Tools and the code map](Tools-and-the-code-map)", t)
    return t


def write(out, name, body, source):
    open(f"{out}/{name}.md", "w", encoding="utf-8", newline="\n").write((BANNER % source if source else "") + body.strip() + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=ROOT + "/work/wiki")
    a = ap.parse_args()
    shutil.rmtree(a.out, ignore_errors=True)
    os.makedirs(a.out)
    pages = []
    for f in sorted(os.listdir(ROOT + "/docs/wiki")):
        if f.endswith(".md"):
            shutil.copy(f"{ROOT}/docs/wiki/{f}", f"{a.out}/{f}")
            pages.append(f[:-3])
    for src, page in SKILL_PAGES.items():
        body = relink(strip_front_and_title(read(f"{SK}/{src}")))
        write(a.out, page, body, f".claude/skills/mlbts-game-code/{src}")
        pages.append(page)
    for letter, stem in REGIONS.items():
        body = relink(strip_front_and_title(read(f"{ROOT}/docs/map/regions/{stem}.md")))
        write(a.out, f"Region-{letter}", body, f"docs/map/regions/{stem}.md")
        pages.append(f"Region-{letter}")
    readme = relink(strip_front_and_title(read(ROOT + "/docs/map/README.md")))
    readme = re.sub(r"\[(source/[^\]]+)\]\([^)]*\)", r"`docs/map/\1`", readme)
    readme = readme.replace("[coverage.md](coverage.md)", "`docs/map/coverage.md`").replace("[binary.md](binary.md)", "[The game binary](The-game-binary)")
    readme = re.sub(r"\[regions/\]\(regions/\)", "the region pages", readme)
    write(a.out, "Tools-and-the-code-map", readme, "docs/map/README.md")
    pages.append("Tools-and-the-code-map")
    side = ["[Home](Home)", "", "Findings"] + [f"- [{p.replace('-', ' ')}]({p})" for p in
            ("Walk-up-freeze", "Match-start-freeze", "Load-stalls", "Frame-rate-and-GPU-waits", "PS5-textures", "Upstream-bug-research")]
    side += ["", "How it works"] + [f"- [{p.replace('-', ' ')}]({p})" for p in
             ("How-the-port-works", "The-game-binary", "Known-game-functions", "Tracing-playbook", "Dev-harness-and-measuring")]
    side += ["", "Game binary regions"] + [f"- [Region {l}](Region-{l})" for l in REGIONS]
    side += ["", "Reference"] + [f"- [{p.replace('-', ' ')}]({p})" for p in
             ("History-and-open-questions", "Tools-and-the-code-map", "Start-here")]
    open(f"{a.out}/_Sidebar.md", "w", newline="\n").write("\n".join(side) + "\n")
    missing = [p for p in pages if not os.path.exists(f"{a.out}/{p}.md")]
    print(f"{len(pages)} pages written to {a.out}; missing: {missing}")
    # every [text](Page) link must point at a page we wrote
    names = set(pages) | {"Home"}
    bad = []
    for p in pages:
        for m in re.finditer(r"\]\(([A-Za-z0-9-]+)\)", read(f"{a.out}/{p}.md")):
            if m.group(1) not in names:
                bad.append((p, m.group(1)))
    print("broken wiki links:", bad[:10] or "none")


if __name__ == "__main__":
    main()
