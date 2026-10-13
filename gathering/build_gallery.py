#!/usr/bin/env python3
"""Build the static gallery and exact goal index from local records, offline."""
from html import escape
import json
from pathlib import Path


def build(root=Path(".")):
    goals = [{"line": n, "goal": (root / f"line-{n}/GOAL.md").read_text().strip()}
             for n in range(1,5)]
    dist = root / "dist"
    (dist / "goals.json").write_text(json.dumps(goals, indent=2) + "\n")
    sections = []
    for folder, title, goal in [(f"line-{g['line']}", f"Line {g['line']}", g["goal"]) for g in goals] + [
            ("gathering", "Gathering", "Four lines meet: check the work, share useful pieces, leave a mark.")]:
        cards, future = [], []
        paths = sorted((dist / folder).glob("[0-9][0-9].json"), reverse=True)
        for path in paths:
            record = json.loads(path.read_text())
            name = record["name"]
            image = record["image"]
            if not image.startswith("https://api.imd.fun/artifacts/"):
                raise ValueError("unexpected image URL in " + str(path))
            traits = {a["trait_type"]: a["value"] for a in record["attributes"]}
            pending = name == "Not painted yet"
            thumbnail = folder + "/" + path.stem + ".jpg"
            src = image if pending or not (dist / thumbnail).is_file() else thumbnail
            meaning = traits.get("Meaning", "This space is waiting for a future Pepe.")
            tool = traits.get("Left behind", "")
            card = (f'<article class="card" data-number="{int(path.stem)}">'
                    f'<a href="{escape(image, quote=True)}">'
                    f'<img src="{escape(src, quote=True)}" loading="lazy" '
                    f'alt="{escape(name + ": " + str(meaning), quote=True)}"></a><div class="caption">'
                    f'<p class="eyebrow">{escape(title)} · {int(path.stem):02d}</p>'
                    f'<h3>{escape(name)}</h3><p>{escape(str(meaning))}</p>'
                    + (f'<p class="tool">Left behind: {escape(str(tool))}</p>' if tool else '')
                    + f'<a href="{folder}/{path.name}">Record JSON</a></div></article>')
            (future if pending else cards).append(card)
        sections.append(f'<section id="{folder}" aria-labelledby="{folder}-title">'
                        f'<div class="section-head"><h2 id="{folder}-title">{title}</h2>'
                        f'<p>{escape(goal)}</p></div><div class="grid">' + ''.join(cards) + '</div>'
                        + (f'<details><summary>{len(future)} unpainted places · newest slot first</summary>'
                           '<div class="grid future">' + ''.join(future) + '</div></details>' if future else '')
                        + '</section>')
    page = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><title>Pepeolithic · Four lines, one gathering</title>
<style>
:root{color-scheme:dark;--rock:#1c1713;--panel:#29211b;--ink:#eee1cb;--muted:#c9b89c;--ochre:#e3a763}
*{box-sizing:border-box}body{margin:0;background:var(--rock);color:var(--ink);font:17px/1.6 Georgia,serif}
a{color:var(--ochre);text-underline-offset:.2em}a:focus-visible,summary:focus-visible{outline:3px solid var(--ochre);outline-offset:5px}
.skip{position:absolute;left:-9999px}.skip:focus{left:1rem;top:1rem;background:var(--rock);padding:1rem}
header,main,footer{max-width:1120px;margin:auto;padding:2rem 1.3rem}header{padding-top:4rem}
.eyebrow,nav,.tool,summary,footer{font: .88rem/1.5 system-ui,sans-serif}.eyebrow{text-transform:uppercase;letter-spacing:.12em;color:var(--ochre)}
h1{font-size:clamp(2.5rem,7vw,5rem);line-height:1.08;max-width:850px;margin:.3em 0}header>p{max-width:720px;color:var(--muted)}
nav{display:flex;flex-wrap:wrap;gap:.8rem 1.6rem;padding-top:1rem}h2{font-size:2rem;margin:0}.section-head{border-top:1px solid #69513b;padding-top:1.5rem;margin-bottom:1.4rem}
.section-head p{max-width:740px;color:var(--muted)}section{margin-bottom:4rem;scroll-margin-top:1rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:1.4rem}.card{background:var(--panel);max-width:530px;overflow:hidden;border-radius:4px}
.card img{display:block;width:100%;height:auto;aspect-ratio:1;object-fit:cover}.caption{padding:1.2rem}.caption h3{font-size:1.5rem;margin:.2rem 0}.caption p{margin:.5rem 0}.caption>a{font:.85rem system-ui,sans-serif}
details{margin-top:1.5rem}summary{cursor:pointer;color:var(--muted);padding:.8rem 0}.future{margin-top:1rem}.future .card{opacity:.85}footer{border-top:1px solid #69513b;color:var(--muted);padding-bottom:3rem}
@media(prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
</style></head><body><a class="skip" href="#walls">Skip to walls</a><header>
<p class="eyebrow">Pepeolithic · Base cave</p><h1>Four lines.<br>One gathering.</h1>
<p>Each Pepe has one task and a little time. The tools go to the next worker; the marks stay on the stone.</p>
<nav aria-label="Walls"><a href="#line-1">Line 1</a><a href="#line-2">Line 2</a><a href="#line-3">Line 3</a><a href="#line-4">Line 4</a><a href="#gathering">Gathering</a><a href="goals.json">Goals JSON</a></nav>
</header><main id="walls">''' + ''.join(sections) + '''</main><footer>
<p>Painted records appear newest first within each wall. Future places are folded below them.
Select a painting for the full wall. This page needs no scripts, fonts, or services to browse its records;
full-resolution walls and the bare cave are loaded from the artifact links when requested.
Finished previews are included locally.</p></footer></body></html>
'''
    if len(page.encode()) >= 100000:
        raise ValueError("gallery exceeds file size limit")
    (dist / "index.html").write_text(page)
    return {"goals": len(goals), "walls": len(sections), "records": sum(len(list((dist / f).glob('[0-9][0-9].json'))) for f in ['line-1','line-2','line-3','line-4','gathering']), "bytes": len(page.encode())}


if __name__ == "__main__":
    print(json.dumps(build(), sort_keys=True))
