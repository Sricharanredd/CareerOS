# Stage 1 — Responsive Implementation Report

Frontend-only responsive pass (Phases B–F) following `docs/STAGE1_RESPONSIVE_AUDIT.md`.

- Baseline: `faafe74` on `main` (tag `stage0-baseline`) plus the untracked audit doc.
- Scope: `frontend/` only. No backend, API, database, auth, AI or routing changes.
- No dependency added, no design token changed, no breakpoint added (Tailwind defaults only).
- Nothing committed or pushed. No dev server or service was started or stopped; the
  already-running dev server was inspected in a browser (section 5).

## 1. Status of the 14 required items

| # | Item | Status |
|---|---|---|
| 1 | Responsive layouts on every route | **Partially completed** — shell, page headers, grids, board and tables behave from 320 px; four low-severity findings (R15, R17, R18, R20) were deliberately not changed |
| 2 | Navigation (sidebar, header, mobile drawer, user menu) | **Completed** — mobile drawer is now a real dialog; desktop sidebar and header unchanged |
| 3 | Typography and spacing | **Completed** — no size/spacing token changed; row and section headers reflow instead of squeezing |
| 4 | Dashboard cards and KPI grids | **Completed** — grid progression preserved; trend chart is readable and labelled on touch; local-date fallback fixed |
| 5 | Tables and list views | **Completed** — applications table/card switch preserved; board columns scroll with snap points |
| 6 | Charts | **Completed** — no fixed-size chart exists; dashboard trend bars now expose values to touch and assistive tech; analytics charts untouched |
| 7 | Forms and input controls | **Partially completed** — label hit areas and switch targets fixed; salary row (R15) left as is |
| 8 | Dialogs, drawers and modals | **Completed** — viewport-aware height, stackable drawer footers, focus trap and focus return added |
| 9 | Touch targets | **Completed** — 44 px minimum for buttons, nav links and checkbox labels on coarse pointers only |
| 10 | Accessibility tied to responsive interaction | **Partially completed** — dialog semantics, focus trap/return, Escape and non-hover values fixed; no automated a11y scan or screen-reader test run |
| 11 | Visual identity and design system preserved | **Completed** — same colours, radii, shadows, fonts and components |
| 12 | No feature, business-logic, API, DB, auth or AI changes | **Completed** — only presentation markup/classes and one type widening (`formatDate` now accepts `Date`) |
| 13 | Static validation | **Completed** — typecheck, 23 tests and production build pass |
| 14 | Runtime visual verification at 320/360/390/430/768/820/1024/1280/1440 px | **Requires runtime verification** — not performed |

## 2. Changes by area

### Foundation — touch targets (`src/index.css`)

One media query, coarse pointers only, so desktop density is untouched:

```css
@media (pointer: coarse) {
  button:not([data-compact]),
  nav a,
  label:has(> input[type="checkbox"]) { min-height: 44px; min-width: 44px; }
}
```

The task completion circle is marked `data-compact` and gets a 44 px hit area from a
`before:-inset-3` pseudo-element instead, so its 20 px visual size is preserved (R4, R14).

### Shell (`src/layout/AppShell.tsx`, `src/components/ui/Overlay.tsx`)

- `useOverlay` is now exported and reused by the mobile navigation drawer: `role="dialog"`,
  `aria-modal`, accessible name, Escape, body scroll lock, initial focus, focus trap and
  focus return (R3).
- Desktop sidebar, header, theme control visibility and user menu are unchanged.
- The handler is stored in a ref so a new `onClose` identity no longer re-runs the effect and
  steals focus while a dialog is open.
- The scroll lock is shared by all overlays and released by the last one to close — see section 5.

### Shared primitives

- `Tabs.tsx` — tablist is a horizontal scroll container with non-shrinking, non-wrapping tabs
  (R1, R2). The underline style is unchanged.
- `Toast.tsx` — width is `calc(100vw - 2rem)` capped at `max-w-sm`, so it stays inside a 320 px
  viewport (R7).
- `Overlay.tsx` — modal panel is a `flex` column capped at `100dvh` minus page padding, header and
  footer fixed, body `min-h-0` + scroll (R8); drawer footer stacks primary-over-secondary below
  `sm` (R9).
- `Layout.tsx` — `SectionTitle` stacks its action below the heading below `sm` (R13).
- `format.ts` — `formatDate` accepts `Date` (needed for the local-date fallback, no caller change).

### Pages

- `DashboardPage` — per-bar `role="img"` + `aria-label`, counts visible without hover on phones,
  local-date fallback (R6, R16).
- `TasksPage` — row is a two-column grid on phones (toggle + text) with the action group on its own
  row; desktop is still a single flex row (R5).
- `InterviewsPage` — card actions move below the content below `sm` (R11).
- `AnalyzerPage` — history timestamp moves under the title on phones; bespoke delete overlay
  replaced with the shared `ConfirmDialog` (R10, R12).
- `ApplicationsPage` — board keeps horizontal scroll and gains `snap-x` / `snap-start` (R19).
- `ApplicationDrawer` — footer stacking comes from `Drawer`; title is now a string so the dialog
  has an accessible name.

### Not changed (deliberately)

| Finding | Reason |
|---|---|
| R15 salary row four columns from `sm` | Inside a 576 px modal the four fields are narrow but never clipped; changing it alters desktop layout for no proven breakage |
| R17 `w-44` company filter | Fits at 320 px today |
| R18 dashboard pipeline `w-28` | Shortening to 80 px made single-word labels overflow their box; reverted |
| R20 no global `overflow-x` guard | Masking overflow would hide the real causes; no page currently overflows |

## 3. Files changed

```
frontend/src/index.css
frontend/src/components/ui/Layout.tsx
frontend/src/components/ui/Overlay.tsx
frontend/src/components/ui/Tabs.tsx
frontend/src/components/ui/Toast.tsx
frontend/src/components/ui/Overlay.test.tsx   (new)
frontend/src/layout/AppShell.tsx
frontend/src/lib/format.ts
frontend/src/features/applications/ApplicationDrawer.tsx
frontend/src/pages/AnalyzerPage.tsx
frontend/src/pages/ApplicationsPage.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/pages/InterviewsPage.tsx
frontend/src/pages/TasksPage.tsx
docs/STAGE1_RESPONSIVE_AUDIT.md                (new, Phase A)
docs/STAGE1_RESPONSIVE_IMPLEMENTATION_REPORT.md (this file)
```

## 4. Validation performed

| Check | Command | Result |
|---|---|---|
| Types | `npm run typecheck` (`tsc -p tsconfig.json`) | pass |
| Tests | `npm test -- --run` | 4 files, 23 tests pass (current totals; see section 5) |
| Build | `npm run build` (`tsc && vite build`) | pass; CSS 48.83 kB, JS 540.01 kB (pre-existing chunk-size warning) |
| Compiled CSS | search built asset | `@media(pointer:coarse)` rule, `max-sm:opacity-100`, `100dvh`, `before:content` all present |
| Servers started | — | none |
| Browser / visual check | — | desktop-width document-scroll check only (section 5); no visual pass |

New test coverage: `Overlay.test.tsx` asserts the dialog is labelled and modal, Escape calls
`onClose`, initial focus lands on the panel, Tab / Shift+Tab wrap inside the dialog, and the
scroll-lock/topmost-overlay cases added in section 5.

## 5. Follow-up fix — vertical page scrolling (runtime bug)

Reported after manual phone testing: Applications, Resumes and Interviews render but do not
scroll vertically at mobile width; other pages scroll.

### Root cause

`useOverlay` locked the page by writing `document.body.style.overflow = "hidden"` and restored a
per-instance copy in its cleanup. When a nested overlay unmounted in the same commit as its
parent — the `ConfirmDialog` inside `ApplicationDrawer` / `ResumeDrawer` after a delete, or any
route change that removes a drawer — React ran the parent cleanup first and the child cleanup
after:

1. Parent cleanup restores the value it saved: `""` → page unlocked.
2. Child cleanup restores the value it saved: `"hidden"` → page locked again, with no open overlay.

The lock is on `body`, so it survives SPA route changes: every later page stays unscrollable until
a reload. That matches "renders correctly, buttons work, no vertical scroll" on the pages visited
after the interaction.

The second defect found in the same hook: every open overlay's `keydown` listener handled Escape,
so one Escape closed both a dialog and the drawer under it.

### Evidence

- Reproduced as a failing test before changing code:
  `restores page scrolling when a nested dialog closes with its parent` →
  `AssertionError: expected 'hidden' to be ''`. The same probe showed Escape calling both
  handlers. Both now pass.
- `grep` over `src/**/*.{ts,tsx,css}`: the only writes to `document.body.style.overflow` are in
  `Overlay.tsx`, and no rule sets `overflow: hidden` on `html`, `body`, `#root` or `main`.
  `index.html` uses `h-full` with no overflow rule. So the overlay hook is the only body-lock
  source in the app.
- Document-scroll check in the running app at 912×670 px on `/resumes` (before the session
  expired): `body.style.overflow` empty, computed `overflow: visible` on `html`, `body`, `#root`
  and `main`, `scrollingElement.scrollHeight === clientHeight` (content fit). Injecting a 1200 px
  probe made `scrollHeight` 1655 vs `clientHeight` 670 and `scrollTo(0, 400)` moved the document,
  so the document is the scroll container and the scaffold scrolls while unlocked.
- Mobile widths (320/390/768 px) were **not** measured: no viewport tool exists, and the iframe
  used for the probe rotated the refresh token and logged the app out. Reproduction at phone
  width is therefore unverified — see the manual checks in section 6.

### Exact fix (`src/components/ui/Overlay.tsx` only)

- Module-level `lockCount` + `savedOverflow`: the first overlay to open saves the previous inline
  value and locks; the last one to close restores it. Restoration happens exactly once.
- Module-level `openOverlays` entries `{ id, depth, sequence }`. `Modal` and `Drawer` provide a
  React context with `depth + 1` around their children, so a dialog inside a drawer is deeper;
  `sequence` breaks ties between sibling overlays. `Escape` and the Tab trap only run for the
  topmost entry.
- No page, CSS, layout-container or business-logic change. Board and tab horizontal scrolling is
  untouched (no `overflow-x` rule or scroll handler was edited), and no global overflow rule was
  added.

Intentional behaviour change: with two overlays open, Escape now closes only the topmost one
(previously both). Tab also stays in the topmost overlay.

### Validation

| Check | Command | Result |
|---|---|---|
| Types | `npm run typecheck` | pass |
| Tests | `npm test -- --run` | 4 files, 23 tests pass (18 previous + 5 new) |
| Build | `npm run build` | pass; JS 540.57 kB (pre-existing chunk-size warning) |

New tests in `Overlay.test.tsx`:

1. locks page scrolling while open and restores it on close;
2. restores the overflow value it found (`scroll`), not a hard-coded empty string;
3. keeps the lock while a nested dialog closes and its parent stays open;
4. restores scrolling when a nested dialog closes with its parent (the reported bug);
5. Escape reaches only the topmost dialog.

Not covered by a test: real page scroll height at 320/390/768 px (jsdom has no layout) and
horizontal board scrolling (no code path changed there; it is CSS `overflow-x: auto`).

## 6. Pending runtime verification

Not claimed as done. With the app and API running, check at 320, 360, 390, 430, 768, 820, 1024,
1280 and 1440 px:

1. Mobile nav: opens, traps focus, Escape closes, body does not scroll, focus returns to the menu
   button, route change closes it.
2. Tasks: all five tabs reachable at 320 px; row actions do not overlap the title; completion circle
   is tappable but visually unchanged.
3. Application drawer at 320 px: tabs scroll, footer stacks with the primary action first, dialog is
   announced by name.
4. Dashboard trend: counts readable on phones; screen reader announces each week.
5. Dialogs in landscape (e.g. 640×360): header and footer stay visible, only the body scrolls.
6. Toast text is not clipped at 320 px.
7. Touch targets measure ≥ 44 px on a coarse-pointer device; desktop sizes unchanged.
8. Applications table at 768 px and board snap behaviour at 390 px.
9. Scrolling after overlays: on each of Applications, Resumes and Interviews at 320/390/768 px,
   open a drawer, open its delete confirmation, confirm, then check
   `document.body.style.overflow` in the console — it must be `""` (it stayed `"hidden"` before
   this fix) and the page must scroll.
10. Board and tab rows still scroll sideways with a swipe/trackpad at the same widths.

To measure the reported symptom directly, in DevTools at a phone width set
`document.body.style.overflow = "hidden"` by hand: the page stops scrolling (the old state), and
`= ""` restores it. Then run steps 9–10.

## 7. Known risks and open items

- Visual verification is outstanding; the fixes above are class-level, not measured in a browser.
- The mobile-width reproduction of the scroll bug is unverified: the browser session was logged out
  while probing, so no phone-width measurement was taken. The shared defect itself is proven by
  test, and it is the only body-lock path in the app.
- Escape and Tab now belong to the topmost overlay only. A nested tooltip or popover implemented
  outside `useOverlay` would not change this, but any future overlay type must also use
  `useOverlay` to join the stack.
- The 44 px rule increases control height on touch devices (intended); a desktop regression pass is
  still required because shared primitives (`Tabs`, `SectionTitle`, `Modal`, `Drawer`) are used on
  every page.
- The build's >500 kB chunk warning is pre-existing and unrelated.
