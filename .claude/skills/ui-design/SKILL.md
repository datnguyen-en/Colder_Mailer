---
name: ui-design
description: Use when building or restyling any page or component in the cold email tracker frontend (frontend/src). Defines the app's look (white, airy, DM Sans, soft-shadow cards, tracked uppercase labels, pink logo accent) and the exact Tailwind recipes and tokens to use so every screen matches.
---

# Colder Mailer UI

The look is **quiet and white**: lots of space, black text in DM Sans, small uppercase labels with wide letter spacing, and white cards that float on very soft, large shadows. Color is used sparingly. The pink in the logo is the only brand color.

Reference mood: a clean product landing page (floating pill nav, centered hero, rounded cards with inset gray panels and label/value rows).

## 1. Rules

1. **White first.** Page background is pure white. Cards are white too; they separate by a faint border plus a soft shadow, never by a gray page background.
2. **Black text, one gray for body copy, one slate for labels.** No colored headings.
3. **Pink is for brand moments only:** the logo, the chart bars, focus rings, one highlight per screen at most. Never pink text on white (too low contrast). Primary buttons are black.
4. **Labels are small, uppercase, widely tracked, slate colored** (`eyebrow` utility). Values next to them are normal case, black.
5. **Big headings are medium weight (500), tight tracking**, never bold.
6. **Round everything generously:** cards 24px, inner panels 20px, buttons/inputs 12px, pills fully round.
7. **No heavy borders, no hard shadows.** Borders are `border-border` (very faint). Shadows are `shadow-soft` only.
8. Light mode only. Don't add `dark:` styles to new code.
9. Status colors (badges in `components/badges.tsx`) stay as they are: always paired with a text label, pastel background, dark text.

## 2. Tokens (defined in `frontend/src/app/globals.css`)

| Token | Value | Use |
|---|---|---|
| `bg-background` | `#ffffff` | page, cards |
| `text-foreground` | `#0a0a0a` | headings, values |
| `text-muted-foreground` | `#6b7280` | body copy, descriptions |
| `text-label` | `#737d92` | uppercase labels, eyebrows, table headers |
| `bg-muted` | `#f7f7f8` | inset panels, hover rows, active nav item |
| `border-border` | `#ececee` | all borders and dividers |
| `bg-brand` / `text-brand` | `#fd9fa0` | logo pink (decorative only) |
| `bg-brand-strong` | `#e8686b` | chart bars, focus ring (≥3:1 on white) |
| `text-link` | `#1a5fd0` | links inside email bodies only |
| `shadow-soft` | 2-layer, ~8% black, 40px blur | cards, nav pills |
| font | DM Sans (`--font-sans`, loaded in `layout.tsx`) | everything |

Add new colors as tokens in `globals.css`, not as hex values in components.

## 3. Typography

| Role | Classes |
|---|---|
| Eyebrow / label | `eyebrow` (11px, semibold, uppercase, 0.28em tracking, `text-label`) |
| Page title | `text-4xl md:text-5xl font-medium tracking-tight` |
| Section / card title | `text-lg font-medium tracking-tight` |
| Big number (stat) | `text-4xl font-medium tracking-tight tabular-nums` |
| Body | `text-sm text-muted-foreground` (or `text-base` for intro copy) |
| Nav item | `text-[13px] font-medium uppercase tracking-[0.14em]` |

## 4. Component recipes

**Page header** (`components/page-header.tsx`): centered stack: eyebrow, then title, then description (`max-w-xl text-base text-muted-foreground`), then actions. Every page passes an `eyebrow`.

```tsx
<PageHeader eyebrow="People" title="Contacts" description="…">
  <Button>Queue</Button>
</PageHeader>
```

**Top bar** (`components/app-shell.tsx`): two floating white pills on a white page, `rounded-2xl border bg-background shadow-soft`. Left: logo (round, 36px) plus app name in `text-lg font-medium tracking-tight`. Right: nav links; active link gets `bg-muted rounded-xl`.

**Card** (`components/ui/card.tsx`): `rounded-3xl border bg-card shadow-soft`. Already the default. Don't add extra borders or rings.

**Inset panel** (a gray well inside a card, e.g. an email preview or a logo area):

```tsx
<div className="rounded-[20px] border bg-muted p-6">…</div>
```

**Label/value rows** (contact details, settings summaries):

```tsx
<dl className="divide-y rounded-[20px] border">
  <div className="flex items-center justify-between px-5 py-4">
    <dt className="eyebrow">Salary</dt>
    <dd className="text-base">$53/hr</dd>
  </div>
</dl>
```

**Email body** (template editor and preview): wrap rendered email HTML in `email-body` (in `globals.css`) so the editor, the preview and the sent email share paragraph spacing, lists and link style. Body text in the editor uses `components/rich-text-editor.tsx`.

**Stat tile**: eyebrow label on top, big number below, optional hint in `text-xs text-muted-foreground`.

**Round chip** (like a "VS" marker or a step number): `flex size-12 items-center justify-center rounded-full border bg-background eyebrow`.

**Tables**: headers use `eyebrow` styling (set in `components/ui/table.tsx`); rows divide with `border-b`, hover `bg-muted/60`. Keep tables inside a Card.

**Buttons**: black primary (`variant="default"`), white `outline` for secondary actions, `ghost` for icon buttons. `rounded-xl`. One primary button per area.

**Inputs**: `rounded-xl border bg-background`; focus shows the pink ring.

## 5. Spacing and layout

- Content width `max-w-6xl mx-auto`, page gutter `px-4 md:px-8`.
- Page header gets room: `pt-10 pb-12` (more on the dashboard is fine).
- Gaps between cards: `gap-6`. Card padding: 24px (default card), 16px (`size="sm"`).
- Prefer fewer, larger cards over many small boxed sections.

## 6. Checklist before finishing a UI change

- [ ] Only tokens from section 2; no stray hex colors or `dark:` classes.
- [ ] Labels use `eyebrow`; headings are `font-medium tracking-tight`.
- [ ] Cards use the default `Card`; no extra rings or hard shadows.
- [ ] Pink appears only as decoration or graphics, never as body text.
- [ ] Works at phone width (nav scrolls horizontally, grids collapse to one column).
- [ ] `npm run lint && npm run typecheck && npm run build` pass.
