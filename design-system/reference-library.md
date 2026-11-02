# Reference library UI

Scope: the vanilla `/references/` application. Source: `nora/references/web/app.css`, `app.js`, and `index.html`. This documents the existing visual system; it does not introduce a framework or change the studio.

- Typography: Inter/Segoe UI/Arial for controls and body; Georgia for page and section headings.
- Colors: existing `--accent: #314e42`, `--muted: #68695e`, `--line: #d7d3c8`, page `#f4f1e9`, cards `#fffdf8`. Main text is `#292823`. Accent and muted text on cards exceed WCAG AA normal-text contrast (verified from the actual sRGB values).
- Controls: native buttons, anchors, checkboxes, selects, dialogs, and expandable details. Focus uses the existing 3px `#9c6c33` outline. Set cards are anchors with fragment URLs; browser back/forward restores the set or landing page.
- Layout: all active sets on entry, category buttons including a merged logical head filter, optional archive checkbox. Set cards show a contained cover, title, filled count and candidate status. A set detail contains angle cards and upload placeholders; no cropping or fabricated angle filling.
- Export: whole-set PNG/ZIP uses ordered membership, independent of custom selection. Eight photos with four columns produce two rows. Partial sets export available photos; videos are ZIP-only. The custom builder remains an explicitly expanded native details panel below the library.
- Responsive behavior: four/three/two set columns, compact horizontal cards under 420px; individual references retain the existing two-column mobile grid. Whole-set actions stack on narrow screens.
- Feedback: library and export status are live regions; existing dialogs retain their busy, retry, replace and delete handling. Candidate labels remain attached to individual media and set counts; selection does not imply approval.

No Tailwind lint rules apply to this isolated plain CSS/JavaScript route. The existing page uses Russian strings directly and has no translation framework.

## Verification

Run the dependency-free contract regressions with `node nora/tests/referenceSets.test.js` (six cases). `nora/tests/referenceSets.browser.mjs` exports `verifyReferenceSets(page)` for a Playwright page and also runs standalone when Playwright is resolvable. Example with the installed CLI package: `NODE_PATH=/usr/lib/node_modules/@playwright/cli/node_modules node nora/tests/referenceSets.browser.mjs`.

The browser regression was exercised through the exposed Playwright MCP runner after the CLI daemon could not start in the sandbox. It routes the current HTML/CSS/JS and isolated API/media fixtures, then verifies 14 navigation/export/responsive checks. It checks exact PNG and ZIP request membership, not actual backend file encoding or authentication. Desktop was visually inspected at 1440×1000; overflow was checked at 390×844. Backend, upload/remove/replace integration and production media remain separate integration checks.

Both PNG and ZIP currently accept at most 16 originals. Whole-set actions honor this API contract; larger free LoRA sets direct the user to the custom selection builder. Videos remain ZIP-only.
