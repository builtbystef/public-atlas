# Public Atlas: build order

Everything from an empty folder to a recorded demo and a submitted
application, in order. Each phase ends with what says it is done. The design
is `product-and-tech-spec.md`. Code to port lives in
`../archived-public-atlas-v1` (v1 below); the base template is
`~/Code/personal/alloy`.

## Phase 0: scaffold

- [x] Copy current alloy into this folder, rename to `public_atlas` and `@public-atlas/*`.
- [x] In the first commit delete auth, workspaces, mail, rate limits and the CRM, on both server and web. Delete the web proxy route and replace it with a `rewrites` rule in `next.config.ts`.
- [x] Add `resources.py` with `build_resources(settings)` and make `main.py`, the worker and the test fixtures call it. Remove every import-time `get_settings()` and the module-level job app.
- [x] Set up compose with PostgreSQL and RustFS, the three server image targets (`server`, `agent`, `parse`) and CI, copied from v1 and trimmed.
- [x] Write `README.md` from the spec's sections 1 and 12, and `apps/server/.env.example`.
- [x] Move the glossary into `docs/glossary.md` so coding agents follow the naming rules.

**Done when** `vp run check` and `vp run test` pass on an app with only a health route, and a test can build resources against the test database without touching environment variables.

## Phase 1: schema and seeds

- [x] Write the models from spec section 4: the `entities` parent with joined-table inheritance for places, institutions, sources, domains and homepages; aliases, identifiers and metrics with the two-column link and check constraint; `institution_served_places`; webpages, snapshots, evidence, blocked attempts; the country tables; runs, assignments, review items, usage, agent run events, eval runs and scores.
- [x] Checked strings generated from each `StrEnum`, with a test that compares the constraints with the enums.
- [x] One initial Alembic migration. Partial unique index on assignments per subject and type while open. Trigram index on aliases.
- [x] The five country tables from spec section 4.4: `country_settings`, `administrative_levels`, `institution_types`, `source_types`, `country_institution_types`, with type names as primary keys and the two checklists as text arrays validated by the API.
- [x] Turn v1's `data/shared` and `data/canada` YAML into Python seed modules, `countries/seeds/shared.py` (global types, default expected sources) and `countries/seeds/canada.py` (settings and naming rules, levels with expected types, Canada's type rows, platforms, and the Ontario anchor as verified place, government and domains). Validated by the countries API's Pydantic models. No YAML.
- [x] `public-atlas seed canada`: idempotent, adds what is missing, never deletes.
- [x] The `CountryRules` object built from the country tables at the start of each assignment, so an edit takes effect on the next one: levels and ranks, expected types per level, expected sources per type for this country, naming forms, platforms.
- [x] The shared list loader in `imports/`: download and hash-check with a local cache, one text renderer per format (CSV and spreadsheet, JSON, HTML, PDF, ZIP member), store each source as a snapshot and an `official_lists` row, diff against the database, apply `PlaceEntry` and `InstitutionEntry` records with their citations as evidence. Idempotent by code then name under the same parent.
- [x] The entry models: `PlaceEntry`, `InstitutionEntry`, `Citation`, in memory only.
- [x] `imports/lists/ontario_places.py`: port v1's `generate.py` and `statcan.py` into `SOURCES` (census population table, census geography file, Ontario directory page), `OVERRIDES` and `entries()`. No generated files.
- [x] `public-atlas load-list <name>`: prints the diff, applies with `--apply`.
- [x] Port the rule test to call `entries()` on the cached files.
- [x] Countries API: list and edit country settings, administrative levels and their expected types, institution types, source types, and a country's type rows with their expected sources, with validation of every array against the type tables.

**Done when** seeding and loading Ontario produces 40 regions, 414 municipalities and 444 governments with codes and populations, a rerun changes nothing, and the rule test passes.

## Phase 2: port the stable pieces

- [x] Storage port (S3, memory) from v1; add an R2 configuration note.
- [x] Search port (Brave, memory) from v1, one request per call.
- [x] Parse port (Docling, memory) and the parse worker with its page ranges, memory trim, retire threshold and retry-with-one-page from v1.
- [x] Browser: rewrite v1's `integrations/browser` as an owned layer. One policy object (allowlist with subdomains, private addresses, robots, shared pacing, resource filtering), the twelve tools used, a capture hook that receives plain values. Drop CDP, auto-install, storage state, event-log tools, protocols file and the durability guard. Port `test_browser.py`.
- [x] Evidence: `quote_checks.py` (text normalization, mojibake repair, name-in-quote, link-in-HTML) and `capture.py` from v1, with the snapshot now holding bytes and text together and sharing text by hash.
- [x] Jobs: the Procrastinate wrapper, worker, stalled sweep and purge from alloy, taking resources as an argument.
- [x] Usage recording: one `usage` table and one `record_usage` function for model and search calls, priced from a prices data file.
- [x] Unit tests ported for quote checks, name matching, media detection, browser policy.

**Done when** a test drives real Chromium against the fixture site and every navigating tool produces a snapshot, a refused domain produces a blocked attempt and nothing else, and a PDF goes through `read_file` to text.

## Phase 3: graph, status changes and review

- [x] `graph/service.py`: create and find places and institutions, add aliases, duplicate search (trigram, designator rule, one row per entity, at most five), normalize URLs, candidate domain names.
- [x] `graph/status_changes.py`: trust a domain, reject a domain, verify a homepage (setting `trusted_path` when the homepage is on a platform), verify an institution, reject an institution, merge two entities. Each records `entered_by`, sets status once and returns what to spawn.
- [x] Review: raise (dedup per entity, fold into a kind when the rule has one), approve, reject, merge, decide a kind, settle open type items when the country tables change. Review API.
- [x] Merge fixed properly: check conflicts first, move aliases, evidence, sources, homepages and open assignments, set the government link and the homepage link.
- [x] Integration tests for every status change and every review action.

**Done when** every path that changes a status goes through `status_changes.py` (a grep for direct status writes finds nothing else) and the review tests pass.

## Phase 4: runs, assignments and the agent

- [x] Runs: create with filter and mode, pause, stop, release held. Pause as in spec section 7.1: the worker reads the run's status when it picks up a job and puts a paused run's job back with a short delay; jobs stay `queued`. `assignments/lifecycle.py` with the status and result columns and the allowed moves.
- [x] Spawning as a consequence of status changes, obeying the run's mode. No `ensure-items` command.
- [x] One descriptor per assignment type: subject kind, tools, finishing tool, goal text, checklist, budget, model choice (GPT-6 Luna at the efforts in spec section 8.4).
- [x] The runner from v1: sessions, half-window handoff, budgets, twenty sessions per job, requeue, finish as `failed` on the last attempt. Three ended signals collapsed into one.
- [x] `agent_run_events`: write the session's message list (prompt, text, tool calls, results) as rows when a session ends.
- [x] Video: `record_video` on the run turns on Playwright video for the browser context; store each file through the storage port and note it as a `video` event.
- [x] Purge jobs, scheduled daily: delete videos of assignments finished more than `video_keep_days` ago (default 7) from storage and mark their events as purged; delete the events of assignments finished more than `events_keep_days` ago (default 90). Both settings; findings, usage and the summary are never purged. Snapshots no evidence cites are pruned when the assignment finishes, as in spec section 8.2.
- [x] Findings as typed functions registered as tools through one adapter: `save_institution` (with parent and `procurement_handled_by`), `save_homepage`, `save_source` (a page under a platform homepage's `trusted_path` verifies like one on a trusted domain), `confirm_domain`, `reject_domain`, `domain_moved`, `status`, `request_review`, `finish`, `read_file`, `search`.
- [x] The merged `find_homepage` assignment: trusted-domain path, new-domain path, search path; `no_homepage` result with its review item.
- [x] `find_institutions` and `find_sources` with the checklist, refused short close, `complete_with_gaps` and its review item.
- [x] Briefing and prompts from v1, rewritten in the glossary's words and read from the country tables.
- [x] Integration tests with a scripted model for each type and each end state; port v1's findings tests.
- [x] CLI: `seed`, `load-list`, `run create [--video]|pause|stop|release`, `worker`.

**Done when** a step-mode run on one eval subject, released one assignment at a time, produces verified institutions, homepages and sources with checked quotes, and every end state in spec section 7.2 is reached by a test.

## Phase 5: evals

- [x] Port the dataset, its schema, validator and README. Add `parent` labels in place of relationship labels.
- [x] Port the scorer; score parent links from `parent_institution_id`.
- [x] The harness: an eval run is a run with `is_eval`, a separate graph database from the same settings object, seeds through the real loader with hold as a parameter, serves the queues in process, starts a parse worker, scores, prices, writes `eval_runs` and `eval_scores`.
- [x] `public-atlas eval run --subject ... --json` and `eval score`.
- [x] Unit tests for the scorer from v1.

**Done when** one full eval run over the twelve subjects finishes, its scores and cost are rows in the main database, and a second run appears beside it.

## Phase 6: console

- [x] Regenerate the API client from the new routes.
- [x] Runs list and detail: create, pause, stop, release held, progress by status, cost.
- [x] Assignments list and detail: filters, the event timeline, video playback, findings, spend, result.
- [x] Institutions table with search and filters; institution detail with aliases, parent, homepage, sources by type, evidence quotes linked to presigned snapshot downloads.
- [x] Review queue: items with snapshot and highlighted quote; approve, reject, merge; kinds decided together.
- [x] Countries pages: country settings, administrative levels, institution types, source types, a country's expected sources per type.
- [x] Evals page: runs over time, scores per type, cost.

**Done when** every page works against the live database and the eval database, and `vp run check` and `vp run test` pass.

## Phase 7: the Ontario pilot

- [x] Trust `gov.on.ca` in the Canada seed in place of `pas.gov.on.ca`. Every host under it is the Government of Ontario, and the allowlist takes subdomains, so the one entry covers the Public Appointments Secretariat, INFO-GO (`www.infogo.gov.on.ca`) and the ministries' legacy sites such as `www.mto.gov.on.ca`, all of which the eval dataset cites and the fence refuses today. Agency domains such as `supplyontario.ca` stay out: `find_homepage` verifies them like any other candidate.
- [x] Parse files lazily. The first eval run spent most of its wall clock in the parse worker on long text PDFs the agent opened to classify a source: a 395-page budget book and a 311-page strategy took twenty minutes each for the one chunk the agent read. The parse job converts only the first range of `parse_page_batch` pages and records the text as `partial`; `read_file` queues the next range when the agent asks for a chunk past what is parsed, waits for it within its ninety seconds, and answers "still parsing" past that. Page numbers and evidence locators do not change. OCR stays on, since scanned minutes exist. Table structure recognition is off and the tableformer model is gone from the parse image: the agent reads files to classify them and to quote a line of evidence, and neither needs a table's cells reconstructed; plain reading order is enough. The parse job logs the seconds each range took; read them per subject in the next eval run.
- [x] Trim the eval dataset so a run is fast enough to iterate on: the two ministry subjects dropped (zero by design until the agencies list below is loaded), and `eval run` works a quick set of five subjects (McGarry, Hawkesbury, Kitchener, Simcoe, Greater Sudbury) plus the places file by default, `--all` for the ten.
- [x] The fixes of the first eval run's review (`eval-run-1-review.md`): the scorer counts a trap only under the subject's place; a trusted link to any page on the candidate domain for the institution vouches for the domain; the discovery goal, the type descriptions and the sources goal carry the buying-power test, the exclusions and the pages that are not sources; the briefing lists the types already recorded under the place as counts, with "from an official list" where the loader wrote them; `find_institutions` has 250 requests and a stall rule that warns at 30 requests without a finding and ends the assignment at 60; and verifying a government's homepage on another domain rejects the directory's old candidate domain.
- [ ] `imports/lists/toronto_agencies.py`: Toronto's agencies and corporations page as `InstitutionEntry` records under the city, the same shape as `ontario_agencies` below. The first eval run spent a third of Toronto's discovery budget reading that page and saved eighteen arenas and community centres from it; a loader reads the whole list once, applies the buying-power rule as overrides, and leaves discovery the bodies no list names.
- [ ] Held until a rerun shows Toronto still overruns its 250 requests: splitting a discovery assignment by section (the design at the end of `eval-run-1-review.md`: a scoped assignment with a start URL, a `defer_section` tool, a briefing that names the page, uniqueness per subject, type and scope).
- [ ] `imports/lists/ontario_agencies.py`: the province's directory of its agencies (the Public Appointments Secretariat's, under `gov.on.ca`, with INFO-GO as the cross-check) as `InstitutionEntry` records of type `agency` under their ministry, with the homepage where the directory gives one, plus a rule test. This is where a ministry's bodies come from: `find_institutions` takes a place, and the first eval run showed why discovery should not stand in for the list (no assignment looked under a ministry, and the province-wide one spent its budget on universities, colleges and school boards). Then in the harness, load it held like the places list, so a ministry subject's agencies exist as loaded rows and are scored on `find_homepage` and `find_sources` rather than on `find_institutions`; decide the bodies the directory will not list (GO Transit and UP Express, divisions of Metrolinx): relabel them `out_of_scope` or keep them as explained misses.
- [ ] Load the live database: `seed canada`, then `load-list canada/ontario/places --apply` and `load-list canada/ontario/agencies --apply`.
- [ ] Run `find_homepage` for all 444 governments and the loaded agencies in auto mode. Read the review queue; fix rules where the queue shows a pattern.
- [ ] Run the eval twice. Fix by the largest miss bucket, re-run the touched subjects, repeat until the gates pass or every miss has a written reason.
- [ ] Release `find_institutions` and `find_sources` for the province in auto mode, sources first. Watch cost per assignment type; if `find_sources` dominates, try a cheaper model on it alone and keep it only if the eval's source recall gate still holds.
- [ ] Write `docs/eval-results.md`: recall and precision per type, the gates, cost per subject, the explained misses.
- [ ] Update the spec's pilot table with the numbers.

**Done when** the gates pass or are explained, Ontario's graph is in the live database, and the numbers are written down.

## Phase 8: demo and application

- [ ] A top section in the README for a reader who does not know the project: what it does, the verification idea in two sentences, the eval numbers, how it would scale to the United States, the known gaps.
- [ ] Record a three-minute demo: start a step-mode run on one city with video on and release an assignment; watch the assignment detail fill with events and play the video; open the institution page and click a quote through to its snapshot; decide a review item; show the eval page with two runs.
- [ ] Write the application: a short cover note that links the repository, the README section and the recording, and maps the project to the Data Mining Software Engineer posting (crawling and extraction, entity resolution, a verified graph, evals, cost control).

**Done when** the application is submitted.
