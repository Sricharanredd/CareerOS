# Stage 1 — Responsive Audit (Phase A)

Audit only. No application file was modified. This document is the only new file.

- Baseline: `faafe74` on `main`, working tree clean, tag `stage0-baseline` present.
- Scope: `frontend/` (React 19 + TypeScript + Vite 6 + Tailwind CSS v4).
- Method: static reading of every route, layout, shared UI primitive, drawer, modal and form. No
  dev server was started; no runtime or visual verification was performed.
- Breakpoints in use are Tailwind v4 defaults: `sm 640`, `md 768`, `lg 1024`, `xl 1280`, `2xl 1536`.
  There is no custom breakpoint theme (`index.css` defines colors, fonts and radii only).

---

## 1. Routes and pages inspected

| Route | File | Purpose |
|---|---|---|
| `/login` | `src/pages/LoginPage.tsx` | Owner sign-in, split marketing panel |
| `/` | `src/pages/DashboardPage.tsx` | KPI cards, pipeline, conversion, trend, interviews, activity |
| `/applications` | `src/pages/ApplicationsPage.tsx` | List (table) + board views, filters, pagination |
| `/job-descriptions` | `src/pages/JobDescriptionsPage.tsx` | Card grid, search, company filter |
| `/resumes` | `src/pages/ResumesPage.tsx` | Card grid, search, archive toggle |
| `/analyzer` | `src/pages/AnalyzerPage.tsx` | Submit form, score dial, findings, history |
| `/tasks` | `src/pages/TasksPage.tsx` | Quick add, 5 tabs, task rows, timer, time log |
| `/interviews` | `src/pages/InterviewsPage.tsx` | 3 tabs, interview cards, schedule/outcome modals |
| `/analytics` | `src/pages/AnalyticsPage.tsx` | KPI grid, conversion, charts, distributions |
| `/settings` | `src/pages/SettingsPage.tsx` | Profile, theme, sessions, password, data, danger zone |
| `*` | `src/pages/NotFoundPage.tsx` | 404 |
| guard | `src/layout/RequireAuth.tsx` | Session restore / redirect |

## 2. Shared components inspected

- Shell: `src/layout/AppShell.tsx` (sidebar, mobile drawer, header, user menu, theme control).
- Layout: `src/components/ui/Layout.tsx` (`PageHeader`, `Card`, `SectionTitle`).
- Overlays: `src/components/ui/Overlay.tsx` (`Modal`, `Drawer`, `ConfirmDialog`, `useOverlay`).
- Controls: `src/components/ui/Button.tsx` (`Button`, `IconButton`), `Form.tsx` (`Field`, `Input`,
  `Textarea`, `Select`, `Checkbox`, `Toggle`), `Tabs.tsx` (`Tabs`, `SegmentedControl`).
- Feedback: `Feedback.tsx` (loading/empty/error/alert), `Toast.tsx`, `Badge.tsx`, `Avatar.tsx`.
- Feature surfaces: `features/applications/ApplicationDrawer.tsx`,
  `features/applications/ApplicationFormModal.tsx`, `features/jobDescriptions/*`,
  `features/resumes/*`, `features/companies/CompanyPicker.tsx`.
- Global: `src/index.css`, `index.html` (viewport meta), `src/main.tsx`.

## 3. Existing responsive behavior to preserve

These are already correct and should not be redesigned:

1. **Shell breakpoint.** Sidebar is `hidden lg:flex`; below `lg` the content is full width and a
   drawer is used (`AppShell.tsx:227,238,258`). Desktop layout must stay as it is.
2. **Page header stacking.** Title/actions go from column to row at `sm` (`Layout.tsx:13`).
3. **Grid progression.** KPI cards `sm:grid-cols-2 xl:grid-cols-4`; entity grids
   `sm:grid-cols-2 xl:grid-cols-3` (`DashboardPage.tsx:465`, `AnalyticsPage.tsx:250`,
   `ResumesPage.tsx:166`, `JobDescriptionsPage.tsx:205`).
4. **Applications list.** Real table from `sm`, dedicated stacked card list below `sm`, and table
   wrapper already has `overflow-x-auto` (`ApplicationsPage.tsx:87,142`).
5. **Board.** Fixed 256px columns inside a horizontal scroll container
   (`ApplicationsPage.tsx:207`). This is the correct pattern for a kanban; only touch affordances
   need review.
6. **Dialogs.** `Modal` is full width with `max-w-*` cap, content scrolls at `max-h-[70vh]`;
   `Drawer` is `w-full` capped by `max-w-*` (`Overlay.tsx:55,79,123`).
7. **Login.** Marketing panel is `hidden lg:flex`; the form column is the only content on small
   screens (`LoginPage.tsx:73,133`).
8. **Charts are fluid.** No SVG/fixed pixel chart; bars are `flex-1` divs that resize
   (`AnalyticsPage.tsx:128-142`, `DashboardPage.tsx:181-196`).
9. **Motion and focus.** `prefers-reduced-motion` reset and `:focus-visible` outline exist globally
   (`index.css:123,168`).
10. **Viewport meta is correct** (`index.html:5`), `color-scheme` is declared.

---

## 4. Issues identified

Severity: **Critical** = content or control unreachable at 320–430px; **High** = usable but
significantly degraded or an accessibility failure on touch; **Medium** = noticeable friction;
**Low** = polish.

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| R1 | Critical | **Tasks tabs overflow and are clipped.** `Tabs` is a non-wrapping `flex` with no scroll container; six px-3 labels (5 tabs) need ~434px at 320–430px viewports. The parent `Card` is `overflow-hidden`, so "Completed" (and part of "All open") cannot be reached at all. | `Tabs.tsx:16-31`; `TasksPage.tsx:470-477` |
| R2 | High | **Drawer tabs overflow.** Application drawer has 3 tabs with count badges (~306px) inside 272px of usable width; the drawer body only sets `overflow-y-auto`, so it becomes a narrow horizontal scroller with no affordance. | `ApplicationDrawer.tsx:321-333`; `Overlay.tsx:136` |
| R3 | High | **Mobile navigation is not a real dialog.** The drawer is hand-rolled: no `role="dialog"`, no `aria-modal`, no focus trap, no initial focus, no focus return, no Escape handling, no body scroll lock. The shared `useOverlay` already implements Escape, scroll lock and focus return but is not used here. | `AppShell.tsx:237-256` vs `Overlay.tsx:9-31` |
| R4 | High | **Touch targets below 44px.** `IconButton` is 32×32; `Button size="sm"` is 32px tall; nav links are ~36px tall; icon-only row actions are 28–32px. These are the primary actions on phones (open nav, delete task, start timer, close dialog). | `Button.tsx:22,77`; `AppShell.tsx:84`; `TasksPage.tsx:176-191,557`; `AnalyzerPage.tsx:276-283` |
| R5 | High | **Task row control density.** One row holds a 20px checkbox plus three 32px icon buttons; at 320px the title column is left with roughly 100–120px, so titles and the application link wrap or truncate aggressively. | `TasksPage.tsx:110-192` |
| R6 | High | **Dashboard trend values are hover-only.** Bar counts appear only on `group-hover` (`opacity-0` → `opacity-100`) and carry no `title`/`aria-label`; touch users can never read a weekly count and screen readers get nothing. The Analytics chart already does this correctly. | `DashboardPage.tsx:181-196` vs `AnalyticsPage.tsx:131-139` |
| R7 | Medium | **Toast is wider than the viewport below 400px.** `fixed bottom-4 right-4 w-full max-w-sm`: at 320px the box is 100vw wide with `right:16px`, so its left edge sits 16px off-screen and text is clipped. | `Toast.tsx:81` |
| R8 | Medium | **Dialog height is not viewport-aware.** The panel has no `max-h`/`dvh` constraint; only the body is capped at 70vh. In landscape (e.g. 640×360) header + capped body + footer exceed the viewport, so both the outer overlay and the inner body scroll, and header/footer drift off-screen. | `Overlay.tsx:55,79` |
| R9 | Medium | **Application drawer footer does not fit.** Two ghost actions (Delete, Archive) and "Edit details" need ~350px including padding; at 320px they wrap into an awkward multi-row split under `justify-between`. | `ApplicationDrawer.tsx:273-305`; `Overlay.tsx:138` |
| R10 | Medium | **Bespoke delete dialog in the analyzer.** Re-implements `Modal` without Escape, focus return, scroll lock or shared padding, and duplicates confirmation markup. | `AnalyzerPage.tsx:618-663` |
| R11 | Medium | **Interview card actions squeeze the content.** The action block is `shrink-0` (a ~130px button plus a 32px delete) beside a `min-w-0` text column; at 320px the description/prep text is confined to ~100px before wrapping. | `InterviewsPage.tsx:84,142-154` |
| R12 | Medium | **Analyzer history row is overloaded.** Score badge (36px) + truncating text + relative time + 28px delete in one non-wrapping row; on 320px the resume/JD names are reduced to a few characters. | `AnalyzerPage.tsx:246-284` |
| R13 | Medium | **Settings section header with action is squeezed.** `SectionTitle` is `justify-between`; "Active sessions" + hint competes with a ~130px "Sign out others" button, leaving ~110px for the text at 320px. | `SettingsPage.tsx:317-331`; `Layout.tsx:43-48` |
| R14 | Medium | **Small check/toggle hit areas.** Checkbox is 16×16 and the switch is 20×36; the label is clickable for the checkbox, but the switch label is a sibling inside the button (acceptable) yet still visually small on touch. | `Form.tsx:161,192-204` |
| R15 | Low | **Salary row is four columns from `sm`.** Inside a `max-w-xl` modal at 640–767px each of min/max/currency/period gets ~110–120px, so currency and period controls are cramped. | `ApplicationFormModal.tsx:415` |
| R16 | Low | **Dashboard date fallback uses UTC.** When the trend array is empty the label falls back to `new Date().toISOString()` (UTC date), which can show the wrong day near midnight in positive offsets. | `DashboardPage.tsx:199` |
| R17 | Low | **Fixed filter width.** Job descriptions company filter is a fixed `w-44`; it fits at 320px today but has no shrink behaviour if labels grow. | `JobDescriptionsPage.tsx:149` |
| R18 | Low | **Dashboard pipeline labels.** Fixed `w-28` label + `w-8` count leaves ~100px for the bar at 320px; readable but tight for the longest status. | `DashboardPage.tsx:97,116` |
| R19 | Low | **Board has no scroll affordance.** Horizontal scroll works, but there is no snap, edge fade or "more" hint, so touch users may not realise more columns exist. | `ApplicationsPage.tsx:207-263` |
| R20 | Low | **No page-level overflow guard.** Nothing prevents a future single fixed-width child from causing body-level horizontal scrolling; there is no `overflow-x` assertion in the shell. (Do not mask real bugs with `overflow-x-hidden`; fix the causes first.) | `AppShell.tsx:226-282` |

### Checked and found acceptable (no change proposed)

- Applications table → card switch at `sm`, with `overflow-x-auto` on the table wrapper.
- All other list pages use cards/rows, not tables (grep for `<table` returns only
  `ApplicationsPage.tsx`).
- Charts are fluid divs; no clipping, no fixed widths, no canvas.
- Search inputs and selects are full width or `min-w-48` inside stacked/flex-wrap containers.
- Forms use stacked `grid gap-4 sm:grid-cols-2`; no horizontal overflow found.
- Login page has no overflow; the hero panel is correctly hidden below `lg`.
- `Drawer` and `Modal` are full width with `max-w` caps; close buttons exist and are labelled.
- Theme switching remains available on phones through Settings → Appearance even though the
  header control is hidden below `sm` (`AppShell.tsx:270`). This is intentional and preserved.
- Nav has `aria-label="Main"`, active states are textual + colour, links are real `<Link>`s.
- Dialog close buttons and the mobile menu button have `aria-label`s.

---

## 5. Recommended implementation approach (Phases B–F, for approval)

Order is chosen so the shared shell and primitives are fixed once, then pages inherit the fix.

**Phase B — Foundation (small, shared)**
- Keep Tailwind defaults; no new breakpoints.
- Add one touch-target rule: interactive icon-only controls and `Button size="sm"` get a minimum
  44×44px hit area on touch (`@media (pointer: coarse)` or a `min-h-11 min-w-11` utility), keeping
  desktop density unchanged.
- No new dependency. No design-token changes.

**Phase C — Shell**
- Turn the mobile drawer into a real overlay by reusing `useOverlay` (export it or add a single
  `MobileNav` wrapper in `Overlay.tsx`): `role="dialog"`, `aria-modal`, labelled, Escape closes,
  focus trapped and returned, body scroll locked. Keep `w-72`, backdrop and animation-free
  behaviour; close on route change already exists.
- Desktop sidebar, header and user menu remain untouched except target sizes.
- Keep the title truncation and the `sm` theme-control hiding.

**Phase D — Pages, in priority order**
1. `Tabs`: give the tablist `overflow-x-auto` + `shrink-0` items (and `scroll-area`), so no tab is
   ever clipped; keep the underline style. Fixes R1 and R2 in one place.
2. `Toast`: `max-w-[calc(100vw-2rem)]` with `left`/`right` inset so it never leaves the viewport.
3. `Modal`: cap the panel at `max-h-[calc(100dvh-2rem)]`, make it a flex column, header/footer
   fixed, body `overflow-y-auto`. `Drawer` footer stacks its action groups at `<sm`.
4. Dashboard trend: mirror the Analytics chart's `role="img"` + `aria-label`/`title` per bar and
   show the latest value without hover; fix the UTC fallback date.
5. Task rows: keep the row, move the three actions into a 2-row layout below `sm` (or a single
   overflow menu) and enlarge the completion control.
6. Interview cards: let the action block wrap to its own full-width row below `sm`.
7. Analyzer history: stack the relative time under the title below `sm`; replace the bespoke
   delete dialog with `ConfirmDialog`.
8. Settings: allow `SectionTitle` to stack its action below the text at `<sm`.
9. Applications: keep table/card split; add scroll snap and a subtle edge affordance to the board.

**Phase E — Accessibility pass**
- Verify target sizes, focus visibility, Escape/backdrop behaviour, focus return, and that no
  value is hover-only.
- Ensure dialogs have accessible names (string titles already map to `aria-label`; ReactNode
  titles need an explicit label).

**Phase F — Validation**
- `npm run typecheck`, `npm test`, `npm run build`.
- Runtime matrix pending approval: 320, 360, 390, 430, 768, 820, 1024, 1280, 1440.

## 6. Files likely to require modification

| File | Reason |
|---|---|
| `src/layout/AppShell.tsx` | Mobile drawer semantics, nav target sizes |
| `src/components/ui/Overlay.tsx` | Export reusable overlay hook, dialog height, drawer footer |
| `src/components/ui/Tabs.tsx` | Scrollable tablist (R1, R2) |
| `src/components/ui/Button.tsx` | Touch targets for `IconButton` / `sm` |
| `src/components/ui/Toast.tsx` | Viewport-safe width (R7) |
| `src/components/ui/Form.tsx` | Checkbox/switch hit areas (R14) |
| `src/components/ui/Layout.tsx` | `SectionTitle` stacking (R13) |
| `src/pages/TasksPage.tsx` | Row density and actions (R5) |
| `src/pages/InterviewsPage.tsx` | Card action layout (R11) |
| `src/pages/DashboardPage.tsx` | Chart labels, UTC fallback (R6, R16) |
| `src/pages/AnalyzerPage.tsx` | History row, shared confirm dialog (R10, R12) |
| `src/pages/SettingsPage.tsx` | Section header with action (R13) |
| `src/features/applications/ApplicationDrawer.tsx` | Footer stacking (R9) |
| `src/index.css` | Only if a shared touch-target utility is added |

`ApplicationsPage.tsx` and `JobDescriptionsPage.tsx` need at most small polish (R17, R19) and are
otherwise already correct.

## 7. Risks and constraints

- Avoid CSS that hides overflow globally; it would mask, not fix, R1/R2.
- The 44px target rule must not change desktop rendering; scope it to coarse pointers or only
  icon-only controls.
- No visual verification yet: every sizing estimate above is computed from class values, not from
  a rendered page. Runtime confirmation is required before calling any finding resolved.

## 8. Validation performed for this audit

| Check | Result |
|---|---|
| Git state | `main`, HEAD `faafe74`, clean tree, `stage0-baseline` → `5215e1b` |
| App files modified | none |
| Server started | no |
| Runtime/visual test | not performed (pending approval) |
