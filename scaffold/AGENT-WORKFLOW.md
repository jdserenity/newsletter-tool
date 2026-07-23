# Code style

- Indentation: 2 spaces everywhere (Python and TypeScript).
- Semicolon-separated statements: The owner frequently writes multiple short statements on one line separated by ; (e.g. x = 1; y = 2; return x + y). Preserve this when it appears; do not split it across lines.
- Concise over verbose: Prefer compact expressions. Do not expand single-line constructs into multi-line ones just because a linter would.
- No auto-formatting: Do not reformat code that wasn't changed. Only touch indentation/style in code you are actively editing. Do not impose generic Black/PEP8 reflows on this codebase.
- Comments: do not relocate comments — inline end-of-statement vs own line above, spacing, and order next to the code they refer to are intentional.
- Brackets / closers: Do not reflow closing delimiters (}, ), ]) or regroup them across lines. Preserve compact runs (e.g. },},))) vs stacked closers when the file already uses one style.
- Do not create a CLAUDE.md file. And if you find one, delete it and put whatever was valuable in its proper file.

# Token Hygiene

- NEVER EVER GREP THE ENTIRE CODEBASE IF READING scaffold/ARCH-LLM.md WOULD SUFFICE. YOU WASTE MY FUCKING TOKENS LIKE YOU DON'T KNOW THEY COST MONEY. I DON'T EVER WANT TO SEE THAT AGAIN UNLESS ABSOLUTELY NECESSARY.
- Re-read scaffold/AGENT-COMMS.md, scaffold/AGENT-WORKFLOW.md, and the relevant scaffold/ files every so often as context grows.

# Test Driven Development

- Tests are required for every implemented behavior.
- Prefer Test Driven Development when adding or changing functionality.
- Favor simple, inspectable technology choices over unnecessary complexity.

# Definition of done

A change is done only when:
1. It does what we agreed it should do.
2. Automated tests cover that behavior (new tests for new behavior; changed tests when behavior changes).
3. If facts changed for the product or system, scaffold/ARCH-LLM.md is updated (minimal deltas; no padding). Update scaffold/ARCH-HUMAN.md when the maintainer needs a readable summary. Remember, ARCH-HUMAN is not an instruction manual for the app. It is strictly for understanding the *codebase*.
How to pick test type (project default):
4. Unit: small pieces of logic with no real database or network.
5. Integration: behavior that really depends on HTTP + DB, or webhooks / OAuth / Stripe — exercise real boundaries with test keys, stubs, or recorded fixtures as appropriate.
6. Browser (e2e): only for stable end-to-end flows; avoid writing a dozen e2e tests while screens are still moving daily.

scaffold version: 2.5.1
