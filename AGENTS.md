Documentation layout (read this first)
- AGENTS.md lives at the repository root (this file). Cursor and similar tools load agent instructions from here.
- Project documentation lives only under docs/: docs/ARCHITECTURE.md, docs/TODO.md, docs/DEPLOY.md.
- Never create or edit ARCHITECTURE.md, TODO.md, or DEPLOY.md at the repository root. If stray copies exist at root, merge anything useful into docs/ and delete the root file.
- README.md stays at the repository root and should stay lean.

- Indentation: 2 spaces everywhere (Python and TypeScript).
- Semicolon-separated statements: The owner frequently writes multiple short statements on one line separated by ; (e.g. x = 1; y = 2; return x + y). Preserve this when it appears; do not split it across lines.
- Concise over verbose: Prefer compact expressions. Do not expand single-line constructs into multi-line ones just because a linter would.
- No auto-formatting: Do not reformat code that wasn't changed. Only touch indentation/style in code you are actively editing. Do not impose generic Black/PEP8 reflows on this codebase.
- Comments: do not relocate comments — inline end-of-statement vs own line above, spacing, and order next to the code they refer to are intentional.
- Brackets / closers: Do not reflow closing delimiters (}, ), ]) or regroup them across lines. Preserve compact runs (e.g. },},))) vs stacked closers when the file already uses one style.
- Do not create a CLAUDE.md file. And if you find one, delete it and put whatever was valuable in its proper file.

Workflow Rules
- When the user states product scope, business rules, stack preferences, or other durable facts in conversation, write them to the right doc immediately: product and system intent go in docs/ARCHITECTURE.md; unresolved work and decisions go in docs/TODO.md (resolved items checked with agent name and date). Do not park product specification in AGENTS.md.
- docs/ARCHITECTURE.md must contain only confirmed facts/decisions. Do not write TBDs, open questions, or speculative options there; put all undecided items in docs/TODO.md only.
- NEVER EVER GREP THE ENTIRE CODEBASE IF READING docs/ARCHITECTURE.md WOULD SUFFICE. YOU WASTE MY FUCKING TOKENS LIKE YOU DON'T KNOW THEY COST MONEY. I DON'T EVER WANT TO SEE THAT AGAIN UNLESS ABSOLUTELY NECESSARY.
- Tests are required for every implemented behavior.
- Prefer Test Driven Development when adding or changing functionality.
- Favor simple, inspectable technology choices over unnecessary complexity.
- Re-read AGENTS.md and the relevant docs/ files every so often as context grows.

Definition of done (keep this short)
A change is done only when:
1. It does what we agreed it should do.
2. Automated tests cover that behavior (new tests for new behavior; changed tests when behavior changes). Say which test file(s) or command proves it so anyone can rerun the same check.
3. If facts changed for the product or system, docs/ARCHITECTURE.md and docs/TODO.md are updated (minimal deltas; no padding).
How to pick test type (project default):
1. Unit: small pieces of logic with no real database or network.
2. Integration: behavior that really depends on HTTP + DB, or webhooks / OAuth / Stripe — exercise real boundaries with test keys, stubs, or recorded fixtures as appropriate.
3. Browser (e2e): only for stable end-to-end flows; avoid writing a dozen e2e tests while screens are still moving daily.

Communication with the maintainer
The maintainer is still leveling up as an engineer. In chat, explain tradeoffs in plain language and concrete examples (what lives in one repo vs many, what breaks when, what they run locally). Do not assume expert jargon is understood. Do not move long explainers into docs/ARCHITECTURE.md; that file stays factual and project-specific.

Documentation Rules
- Put project structure, system maps, product specification, tech stack, and design reasoning in docs/ARCHITECTURE.md.
- docs/ARCHITECTURE.md is not a textbook. Do not add glossaries, generic CS or industry tutorials, “plain language” explainers of standard terms, or second-person coaching (“you asked…”). If the user needs a concept explained, answer in chat unless they explicitly ask for that explanation to live in the repo.
- Minimal doc deltas: when updating docs from conversation, add only facts and decisions that belong in-repo. Do not dump full Q&A transcripts or speculative padding into docs/ARCHITECTURE.md or docs/TODO.md.
- Keep AGENTS.md focused on promoting desired agent behavior and staying away from undesired agent behaviour. Anything product architecture does not belong here.
- Never add items to docs/TODO.md without explicit approval from the owner.
- Do not delete items from docs/TODO.md. When an item in docs/TODO.md is resolved, check it off and include the agent name and timestamp.
- Items in docs/TODO.md should be added in *reverse-chronological order*, meaning that new items will be added to the *top* of the file, not the bottom.
- Update AGENTS.md whenever the user specifies a repeated agent behavior that should persist.
- Keep documentation factual and current.
- Separate confirmed decisions from open questions clearly.
