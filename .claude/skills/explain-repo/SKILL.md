---
description: Explains this repository's architecture and publishes a diagrammed walkthrough of the data pipeline as an Artifact. Use when the user asks how this project works, wants an overview, or asks for a diagram of the pipeline.
---

# Explain This Repo

Gives a newcomer a fast, accurate orientation to the codebase — a short walkthrough plus real rendered diagrams of the actual run-time flow, published as an Artifact page. Never fall back to a raw ` ```mermaid ` fenced block in chat — it doesn't render in a terminal, it just reads as unparsed text.

## Steps

1. Read `README.md` and `ai_utils/CLAUDE.md` first — they already document the architecture, the design decisions, and their rationale. Don't re-derive from scratch what's already written down there.
2. Load the `artifact-design` skill, then the `artifact-diagramming` skill, before writing anything. Both are required before drawing an Artifact diagram — they set the palette/typography/layout approach and the hand-authored-SVG mechanics this page should follow.
3. Verify the current mechanism against the actual code rather than assuming nothing has changed since last time — in particular, check `MAX_WORKERS` in `extract.py` and the current shape of `compute_checks_passed()` in `transform.py`, so the diagram reflects what the code does right now, not a stale snapshot from a previous run of this skill.
4. Build a single HTML page (a utilitarian/report treatment per the loaded skills' guidance, not editorial) covering:
   - A short prose walkthrough: what the script does end to end, the three-file split and why, the concurrency approach and why it's worth it here.
   - A hand-authored inline-SVG figure tracing the actual run-time data flow through `main.py` — fetch closed PRs → filter to merged → concurrent enrichment fan-out/fan-in → transform + sort → CSV — marking each intermediate JSON file it writes along the way.
   - A second, smaller figure specifically for `compute_checks_passed()`'s decision logic. That's the one part worth a reader's independent attention, so it earns its own diagram rather than being folded into the first one.
5. Publish it with the Artifact tool and give the user the link. Keep the prose short enough to read in under a minute — this orients someone new, it doesn't replace the README.

## Don't do this

- Don't fall back to a Mermaid fence in chat if publishing fails for some reason — say so and ask, rather than silently degrading to unreadable text.
- Don't hardcode a previous run's diagram coordinates or copy its content in. Always redraw from what the code currently does, so the diagram can't silently go stale as the codebase changes.
