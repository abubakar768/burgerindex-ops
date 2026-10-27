# burgerindex ops — design system

The rules every screen follows. The source of truth for values is
`src/app/globals.css` (tokens) and `src/components/ui.module.css` (components);
this file says what each one is for, so a new screen picks the same thing an
existing one did. It describes the design from the "Auto Crawlers Fix" canvas
and the build since; it is not a redesign.

For UX checks beyond this file, the `ui-ux-pro-max` skill in
`.claude/skills/` has the full rule set. Where it disagrees with this file (see
[Deviations](#deviations-from-ui-ux-pro-max)), this file wins.

## 1. Character

An internal operations console. The people using it are engineers checking
whether crawls are healthy and acting on the ones that are not, so:

- **Dense, not airy.** Tables carry most screens. 14 px body text, tight rows.
- **Calm by default, loud only when something is wrong.** Most of the page is
  ink on panel; amber (`--warn`) appears only where a human should look.
- **Every action says what it will and will not do**, because Run, Stop and
  Fix touch production machines and cost money.
- **Dark first.** The canvas is dark; light is the opt-in theme, designed
  separately rather than inverted.

## 2. Colour

Components use tokens only, never raw hex. Every token exists in both themes.

### Grounds and lines

| Token | Use |
|---|---|
| `--bg` | page background |
| `--panel` | cards, tables, sections, sidebar |
| `--raised` | secondary buttons, hover, toasts: one step above panel |
| `--panel-blue` | the confirm bar and accent sections |
| `--code-bg` | log and diff panels, inline `code` |
| `--row-hover` / `--row-sel` | selectable table rows |
| `--line` | card and table borders, header rule |
| `--line-soft` | between table rows, footer rules |
| `--line-strong` | hover borders, tags, ghost buttons |
| `--line-dashed` | empty states, dashed pills |

### Ink

Five levels, darkest first. Pick by role, not by look.

| Token | Use |
|---|---|
| `--ink` | titles, primary values, selected nav |
| `--ink-2` | table cell text, button labels |
| `--ink-3` | column headers, card labels, notes, subtitles |
| `--ink-4` | sub-lines under a cell, meta, placeholders, footers |
| `--ink-dim` | **disabled controls only** — it is below 4.5:1 on purpose |

### Meaning

| Token family | Means | Never use for |
|---|---|---|
| `--accent*` | the primary action, links, focus ring, selected/active state, "running" | warnings |
| `--warn*` | needs a human: failed, stale heartbeat, RAM near limit, P0, schedule with no spider | destructive actions |
| `--ok*` | healthy: live, ran fine, check passed | decoration |
| `--danger*` | the one irreversible control: Kill (SIGKILL) | anything else |
| `--src-sched/-dash/-manual-*` | who started a crawl | — |
| `--infra-*` | issue categories a code change will not fix | — |
| `--diff-*`, `--count-*` | added and removed lines | — |

### Contrast

Every text token except `--ink-dim` clears **4.5:1 on every ground it is
used on, in both themes** (WCAG AA). Check with a contrast tool when adding a
token or a new text/ground pairing; the light theme's accent, warn and ink-4
were each darkened a step to get there.

Colour is never the only signal. A stale heartbeat also says "stale"; a hot
RAM reading also shows its percentage; a failed check has a cross, not just
amber.

## 3. Type

| Role | Font | Size / line | Weight |
|---|---|---|---|
| Page title (h1) | Plus Jakarta Sans | 30/38 (24/32 under 720 px) | 700 |
| Stat value | Plus Jakarta Sans | 32/40 | 700 |
| Section title (h2) | Plus Jakarta Sans | 18 | 700 |
| Confirm / banner title | Plus Jakarta Sans | 15 | 600–700 |
| Body, table cells, buttons | Plus Jakarta Sans | 14 | 400 (600–700 on emphasis) |
| Secondary text, notes | Plus Jakarta Sans | 13 | 400 |
| Column headers, card labels | Plus Jakarta Sans | 12, `letter-spacing: 0.06em`, upper case | 400 |
| Identifiers: spider, PID, file, branch | Spline Sans Mono | 13 | 400 |
| Eyebrow (`MODULE / …`), badges | Spline Sans Mono | 12, `letter-spacing: 0.08em` | 400 |

- **Nothing below 12 px.**
- **Numbers that update in place use tabular figures** (`font-variant-numeric:
  tabular-nums`), so a poll does not make columns jitter.
- Identifiers are always mono, so a spider name reads as something you could
  paste into a terminal.

## 4. Space and layout

- **4 px grid.** In use: 2, 4, 6, 8, 10, 12, 16, 18, 20, 24, 32, 40, 48.
- **Page:** 40 px × 24 px padding (24 × 16 under 720 px), content max 1216 px,
  24 px between blocks.
- **Shell:** a 236 px sticky left sidebar. Under 900 px it becomes a top strip;
  four destinations do not need a drawer.
- **Split view** (Live, Fix): main column `flex 999 1 600px`, side column
  `flex 1 1 380px`; the side drops below the main when there is no room.
- **Stat and meter cards:** `auto-fit, minmax(220px, 1fr)`.
- **Tables** scroll sideways inside their own frame (`Table minWidth`); the page
  itself never scrolls sideways.

Radius: cards and sections 12, controls 8, toasts 10, pills and tags round.
No shadows, except toasts, which float over content.

## 5. Components

### Buttons

One `primary` per view: the thing this screen is for (Run, Fix, Approve,
Continue). Sizes: `sm` 36 px inside table rows, default 40, `lg` 44 in
action panels, `xl` 48 for a single full-width call to action.

| Tone | Use |
|---|---|
| `primary` | the main action |
| `ghost` | secondary action next to a primary (Cancel, Retry fix, Try again) |
| default | filters and neutral actions |
| `on` | a filter that is selected (`aria-pressed`) |
| `solid` | a quiet standalone action (Sync) |
| `warn` → `warnSolid` | Stop, then its confirmation |
| `danger` | Kill only |

While a request is in flight the button is disabled and its label says what
is happening: "Starting…", "Queueing…", "Pushing…".

### Status

- **Pill**: page-level status beside the title (Live, 408 scheduled, Failed).
- **Tag**: metadata inside a row (source, env, P0, Paused, Not in crawlers repo).
- **Category chip**: an issue category; amber if a code change can fix it,
  blue-grey if not.

### Containers

- **Card / MeterCard / StatCard**: one number with its label and a note that
  says what the number means ("alert at 85%").
- **Section**: a titled block of related content.
- **Banner**: page-wide state, with an icon: `ok`, `warn`, `info`.

### Confirm bar

An inline panel above the table, not a modal. **Required before anything that
starts a crawl, sends a signal, or runs Claude** — Run, Stop, Fix, Retry fix.
It names the target in mono, says what will happen and what will not, and
calls out P0 crawlers. Two buttons: the action (primary) and Cancel (ghost).

### Tables

Grid rows, not `<table>`, so columns can stack. Header row 12 px caps in
`--ink-3`; cells 14 px; a sub-line under a cell is 12 px `--ink-4`. Rows a
user picks are buttons (`SelectableRow`, `aria-pressed`). Long values wrap
(`overflow-wrap: anywhere`) rather than truncate; where a clamp is
unavoidable, the full text must still be reachable without hovering.

### Feedback

- **Loading:** skeleton rows in the shape of the content, never a blank frame.
- **Empty:** a title, one sentence on why, and an action if there is one.
  Errors use the same block with "Try again".
- **Toasts:** bottom right, `aria-live="polite"`, dismissible. A toast is never
  the only record of something the user has to act on.

## 6. Interaction and accessibility

- Focus ring: 2 px `--accent`, 2 px offset, on every interactive element.
  Never remove it without a replacement.
- Pointer targets at least 24 × 24 px (WCAG 2.2 AA); buttons are 36+.
- Filters use `aria-pressed`; the current nav item uses `aria-current="page"`.
- Every input has a visible label; errors are announced (`role="alert"`) and
  tied to their field.
- A skip link goes straight to the page content.
- Motion: only the skeleton shimmer and the fix spinner, both off under
  `prefers-reduced-motion`.

## 7. Words

- Say what happens, then what does not: "Starts on prod… Its next scheduled
  run stays as is." "Nothing is pushed."
- Times are UTC and say so.
- Name the thing: `starbucks-esp-crawl`, PID 53107, not "the crawler".
- An error says what to do next, not just that something failed.

## Deviations from ui-ux-pro-max

| Its rule | Here | Why |
|---|---|---|
| 44 × 44 touch targets | 24 px minimum, 36 px buttons | desktop tool, pointer first; WCAG 2.2's web target size is 24 |
| 16 px base text | 14 px | dense tables are the point; 12 px is the floor |
| Mobile-first | desktop-first, works down to phone width | used at a desk; phones get a working, not a primary, layout |
| Pick a style / palette per product | fixed by this file | the design already exists |
