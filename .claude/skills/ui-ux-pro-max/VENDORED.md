# Vendored: ui-ux-pro-max

Source: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
Commit: 28b3b8dee8c976df4fa3e94aed4e092ad43fcb03 (`.claude/skills/ui-ux-pro-max/`)
License: MIT, see LICENSE in this folder.

Copied as a project skill, not installed as a plugin, so it is pinned and
reviewed: nothing changes here unless someone re-vendors it.

Local changes:

- SKILL.md: `${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/` became
  `.claude/skills/ui-ux-pro-max/`. The variable is only set for plugins; as a
  project skill it is empty and every command pointed at `/.claude/...`.
  Commands now run from the repo root.
- Left out, because only upstream's own catalog maintenance uses them (nothing
  under scripts/ reads them at search time): `scripts/tests/`,
  `scripts/validate_data.py`, `data/phosphor-icons-upstream.json`,
  `data/google-font-licenses.json`, `data/data-provenance.json`,
  `data/catalog-summary.json`.

Checked before adding: the scripts are standard-library Python with no network,
subprocess or eval calls (`urllib.parse` only), and no file holds hidden
Unicode or instructions aimed at the agent.

How this repo uses it: as a review checklist for the dashboard, not to pick a
style. The visual design is fixed in web/DESIGN.md; rules aimed at phones or
marketing pages (44 px touch targets, 16 px body text) give way to it.

To update: download the new commit, repeat the exclusions and the SKILL.md
path change, re-run the checks above, and update the commit here.
