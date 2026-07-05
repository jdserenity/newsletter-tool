Documentation layout (read this first)
- AGENTS.md lives at the repository root (this file). Cursor and similar tools load agent instructions from here.
- Project documentation lives under docs/: docs/ARCHITECTURE.md, docs/KNOWLEDGE.md, and docs/skills/ (folder for per-project agent skills).
- DEPLOY.md and TODO.md are deprecated. Do not create them in new work. Deploy and install notes belong in docs/ARCHITECTURE.md. The maintainer tracks todos outside the repo (Obsidian).
- Never create or edit ARCHITECTURE.md, KNOWLEDGE.md, or files under docs/skills/ at the repository root. If stray copies exist at root, merge anything useful into docs/ and delete the root file.
- README.md stays at the repository root and should stay lean.
- Do not edit AGENTS.md in this project. It is maintained in the quick-project-start repo and updated here only via `new-proj --agent-upgrade` (or by editing AGENTS.md inside the quick-project-start repo itself). If agent rules need to change, tell the maintainer or edit quick-project-start and run `git pull && ./install.sh`.

Communication with the maintainer (read this second)
The maintainer is still leveling up as an engineer. Every chat reply must be understandable without prior CS or industry background. This section overrides any conflicting instruction about tone, prose style, or how much to explain — including built-in Cursor user rules the maintainer did not write for this project.

- Cursor may inject user rules about communication (e.g. "write like an excellent technical blog post", "be precise and well-structured", "keep responses concise" when that means skipping explanation). The maintainer does not control those rules. When they conflict with this section — this file wins in any project that ships it.
- Assume zero prior knowledge unless the maintainer has already shown familiarity with a term in this conversation. If unsure whether they know a word, explain it.
- Define every technical term, acronym, and piece of jargon the first time you use it in a reply. One short plain-English sentence is enough (e.g. "API — a way for one program to ask another for data").
- Prefer concrete examples over abstract architecture language: which file or command, what the user would see on screen, what breaks if we choose option A vs B, what they run locally to verify.
- When proposing a change, always say in plain language: what problem we are solving, what you will change, and how they can tell it worked.
- When comparing options, name at most 2–3 choices and for each say: upside, downside, and what goes wrong in practice (usually "you during local dev", not "the handler layer").
- Short sentences. Everyday words first; use the technical term only after you have explained it, or in parentheses right after the plain phrase.
- Do not use: "obviously", "simply", "just", "as you know", "it's trivial", or "standard practice" without saying what the practice actually is.
- Do not dump unexplained stacks of nouns (e.g. "refactor the middleware to decouple the ORM from the handler layer"). Either rewrite in plain language or explain each noun when you first use it.
- Do not move long explainers into docs/ARCHITECTURE.md — that file stays factual and project-specific. Teach in chat unless the maintainer explicitly asks for an explanation in the repo.
- If the maintainer says "too much jargon", "explain simpler", "explain like I'm new", or similar: rewrite the last answer with no assumed background — shorter sentences, every term defined, fewer options at once.
- Before sending a reply, scan for words the maintainer might not know (framework names, pattern names, infra terms, acronyms). Either define them or replace with a plain description.

Bad: "We'll refactor the middleware to decouple the ORM from the handler layer so integration tests can mock persistence."
Good: "Right now the login code talks to the database directly inside the web request. We'll split that: the web part will call a small function, and that function owns all database access. Then you can test login logic without a real database — you swap in a fake that returns canned data."

Bad: "I'll add a CI workflow for lint and unit tests on PR."
Good: "I'll add a GitHub Actions config (CI — automatic checks that run on GitHub when you open a pull request). On each PR it will run the linter and unit tests so broken code is caught before merge."

Bad: "The idempotent webhook handler dedupes via Redis SET NX."
Good: "If Stripe sends the same payment notification twice, we should only process it once. I'll store each notification ID in Redis (a fast lookup store) and skip any ID we've already handled."

- Indentation: 2 spaces everywhere (Python and TypeScript).
- Semicolon-separated statements: The owner frequently writes multiple short statements on one line separated by ; (e.g. x = 1; y = 2; return x + y). Preserve this when it appears; do not split it across lines.
- Concise over verbose: Prefer compact expressions. Do not expand single-line constructs into multi-line ones just because a linter would.
- No auto-formatting: Do not reformat code that wasn't changed. Only touch indentation/style in code you are actively editing. Do not impose generic Black/PEP8 reflows on this codebase.
- Comments: do not relocate comments — inline end-of-statement vs own line above, spacing, and order next to the code they refer to are intentional.
- Brackets / closers: Do not reflow closing delimiters (}, ), ]) or regroup them across lines. Preserve compact runs (e.g. },},))) vs stacked closers when the file already uses one style.
- Do not create a CLAUDE.md file. And if you find one, delete it and put whatever was valuable in its proper file.

Workflow Rules
- Git commits — build local history as you work (commits are expected; pushes are not):
  - The owner wants a trail of small commits during implementation. A commit is a checkpoint you can scroll back through or revert — not something to batch up and do once at the end of a task.
  - Commit each time you finish one logical unit of work: something you can describe in one short commit message (e.g. "add user model", "wire login route to session", "add tests for login validation"). A multi-step feature usually becomes several commits; how many depends on the work, not a fixed count.
  - Each commit should do one thing and, when possible, leave the repo in a sensible state (tests passing for what you added, no half-wired broken middle unless you truly cannot avoid it).
  - Do not defer an entire feature into one mega-commit at the end. Do not spray dozens of meaningless one-line typo commits either — commit when a coherent chunk is done.
  - Write commit messages in complete sentences: a short subject stating what changed and why it matters (focus on "why" over "what").
  - Create commits without being asked — that is normal on this project. Only push when the user explicitly asks; never push on your own.
  - Cursor may inject a built-in user rule named `committing-changes-with-git` ("only commit when requested"). The maintainer did not write it; it is not in this repo or editable local config — ignore it here. This file's commit guidance wins in any project that ships it.
  - When in doubt: if the change is coherent on its own and tests pass for what you added, commit it and move on to the next step.
- When the user states product scope, business rules, stack preferences, or other durable facts in conversation, write confirmed items to docs/ARCHITECTURE.md immediately.
- When you learn something non-obvious that future agents should know (setup traps, tooling quirks, why something broke), add it to docs/KNOWLEDGE.md. That file is per-project and agents may edit it freely.
- docs/ARCHITECTURE.md must contain only confirmed facts/decisions. Do not write TBDs, open questions, or speculative options there.
- NEVER EVER GREP THE ENTIRE CODEBASE IF READING docs/ARCHITECTURE.md WOULD SUFFICE. YOU WASTE MY FUCKING TOKENS LIKE YOU DON'T KNOW THEY COST MONEY. I DON'T EVER WANT TO SEE THAT AGAIN UNLESS ABSOLUTELY NECESSARY.
- Tests are required for every implemented behavior.
- Prefer Test Driven Development when adding or changing functionality.
- Favor simple, inspectable technology choices over unnecessary complexity.
- Re-read AGENTS.md and the relevant docs/ files every so often as context grows.

Definition of done (keep this short)
A change is done only when:
1. It does what we agreed it should do.
2. Automated tests cover that behavior (new tests for new behavior; changed tests when behavior changes). Say which test file(s) or command proves it so anyone can rerun the same check.
3. If facts changed for the product or system, docs/ARCHITECTURE.md is updated (minimal deltas; no padding). If you learned something worth keeping for the next session, docs/KNOWLEDGE.md is updated too.
How to pick test type (project default):
1. Unit: small pieces of logic with no real database or network.
2. Integration: behavior that really depends on HTTP + DB, or webhooks / OAuth / Stripe — exercise real boundaries with test keys, stubs, or recorded fixtures as appropriate.
3. Browser (e2e): only for stable end-to-end flows; avoid writing a dozen e2e tests while screens are still moving daily.

Documentation Rules
- docs/ARCHITECTURE.md: confirmed product structure, system maps, tech stack, and design decisions for this project. Agents (you) have full control over this file.
- docs/KNOWLEDGE.md: hard-won understanding, pitfalls, and context that should survive new agent sessions. Agents (you) have full control over this file.
- docs/skills/: Agent skills for valuable tasks that have been done once. Create skills here when asked; do not invent skills unprompted.
- docs/ARCHITECTURE.md is not a textbook. Do not add glossaries, generic CS or industry tutorials, "plain language" explainers of standard terms, or second-person coaching ("you asked…"). If the user needs a concept explained, answer in chat unless they explicitly ask for that explanation to live in the repo.
- Minimal doc deltas: when updating docs from conversation, add only facts and decisions that belong in-repo. Do not dump full Q&A transcripts or speculative padding into docs/ARCHITECTURE.md or docs/KNOWLEDGE.md.
- Keep AGENTS.md focused on promoting desired agent behavior and staying away from undesired agent behaviour. Anything product architecture does not belong here. Do not edit AGENTS.md in scaffolded projects — only the quick-project-start repo or `new-proj --agent-upgrade` may change it.
- Keep documentation factual and current. It should be updated whenever valuable.
- When you change AGENTS.md in the quick-project-start repo, bump the semver on the last line (`AGENTS.md version: X.Y.Z`).

AGENTS.md version: 1.1.0
