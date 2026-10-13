# Public Atlas: product and technical specification

How Public Atlas works and why it is built this way. The [README](../README.md) is the short
version; the words the code uses are in [glossary.md](glossary.md).

**Contents**

1. [What Public Atlas is](#1-what-public-atlas-is)
2. [Design principles](#2-design-principles)
3. [Concepts](#3-concepts)
4. [Data model](#4-data-model)
5. [How data enters the graph](#5-how-data-enters-the-graph)
6. [How data is verified](#6-how-data-is-verified)
7. [Runs and assignments](#7-runs-and-assignments)
8. [The agent](#8-the-agent)
9. [Derived relationships](#9-derived-relationships)
10. [Evaluation](#10-evaluation)
11. [Console](#11-console)
12. [Tech stack and code layout](#12-tech-stack-and-code-layout)

---

## 1. What Public Atlas is

Public Atlas builds a map of the public sector for vendors who sell to governments. For each
public body it records what it is, where it is, which body buys on its behalf, its official
homepage, and the web pages that carry procurement signals: budgets, capital plans, council and
board minutes, procurement portals, open tenders, contract awards and strategic plans.

Selling to government takes three things in order: a map of institutions and their signal
sources, continuous collection of what those sources publish, and analysis that turns the
collected text into buying signals. Public Atlas is the first of the three. It finds
institutions and sources. It does not read the sources' documents for their contents.

Official lists provide most of the map. An AI agent fills in the rest by browsing official
websites. The agent cannot simply assert a fact: every fact comes with a quote, the system keeps
a stored copy of the page, and code checks that the quote is really on it. Only then is the fact
verified. What the rules cannot decide goes to a person through a review queue.

### 1.1 Goals

- **Complete coverage.** Every place and public institution in a country, measured against a hand-labelled dataset, not the agent's own sense of done.
- **Auditable trust.** Every verified fact has a chain of evidence back to an official list or a domain a person verified by hand.
- **Sources mapped to institutions.** Each signal source is typed and linked to the body it belongs to.
- **Controlled runs.** Work can be started, paused, stopped and filtered by place, level and type, step by step during development or hands-off for a whole country.
- **Bounded cost.** The agent reaches only approved domains, within a budget per assignment, and every model and search call is priced.

### 1.2 Targets

The pilot is Ontario: the province, its 444 municipal and regional governments, the public
bodies under them and their sources. The eval gates (section 10) encode the targets:

| Measure | Target | Measured by |
| --- | --- | --- |
| Places against the official list | 100% | The rule test on `canada/ontario/places` |
| Homepage of each government | 99% recall | `find_homepage` on the 25-government eval file |
| Institutions under a place | 95% recall | `find_institutions` on the eval subjects |
| Procurement, meeting and budget sources | 90% recall | `find_sources` on the eval subjects |

---

## 2. Design principles

1. **State lives in the database, not in the agent's context.** Any agent session can be thrown away and a new one picks up from the database.
2. **One assignment per session.** Each session works one bounded assignment from a short briefing. The backend creates follow-up work; the agent never does.
3. **General tools, hard fences.** The agent gets a few browsing tools and decides how to use them. Which domains it may reach is enforced in code.
4. **The agent proposes, rules verify.** Only code or a person marks something verified. The rules check that the quote is on a stored copy of the page and that it names the thing being saved.
5. **Don't ask the agent for what a list already gives.** Places come from the statistics office, agencies from the government's own list. The agent is spent on what no list gives.
6. **Never drop a public body for want of a type.** A body with no matching type is saved as `other` and sent to review.
7. **Relationships are derived, not recorded.** The agent saves facts about one body at a time. Links between bodies come from foreign keys.
8. **Every state change goes through one door.** Each transition (a domain trusted, a homepage verified, an institution approved) is one function, called alike by the rules, the reviewer, the list loader and the country seed.
9. **Plain names.** One everyday word per concept ([glossary.md](glossary.md)), even when the name gets longer.

---

## 3. Concepts

- **Place**: a unit of the administrative hierarchy: Canada, Ontario, York Region, Markham. Places nest, and each has an administrative level.
- **Institution**: a public body that exists and may buy things: a government, a ministry, a school board, a transit agency, a hospital.
- **Government**: the institution that is a place's own government: the City of Toronto for the place Toronto.
- **Source**: a web page that carries procurement signals for one institution, with a source type.
- **Homepage**: an institution's official starting page. A claim with a status until verified.
- **Webpage**: any URL the system opened. A log, not a claim.
- **Domain**: a website address such as `toronto.ca`. The unit of trust and of the browser allowlist.
- **Snapshot**: a stored copy of a page or file as fetched, with its extracted text.
- **Evidence**: a quote from a snapshot that supports an entity.
- **Status**: `candidate`, `verified`, `rejected` or `needs_review`, shared by places, institutions, sources, domains and homepages.
- **Trusted domain**: a domain whose status is `verified` and whose kind is `official`. A quote from one verifies what it names.
- **Platform**: a domain anyone can publish on (YouTube, a tenders portal). Fetchable, never trusted.
- **Entered by**: how a row got here: `manual`, `script` or `agent`. On every entity and every evidence row.
- **Procurement handled by**: `self` or `parent`: whether an institution buys on its own account or its parent buys for it.
- **Official list**: a file an authority publishes that a loader reads instead of sending the agent: a census table, a directory of governments, a ministry's list of agencies.
- **Anchor**: a place whose government and domains a seed created by hand, as verified. Discovery starts there. Not a table: the rows are ordinary places, institutions and domains with `entered_by = manual`.
- **Run**: a batch of work with a filter and a mode. The unit a person starts, pauses and stops.
- **Assignment**: one bounded piece of agent work on one subject, inside a run.
- **Session**: one agent context inside an assignment. A long assignment hands off between sessions.
- **Review item**: a question a person must answer about one entity.

---

## 4. Data model

Everything lives in one PostgreSQL database, alongside Procrastinate's job tables. Every id is a
UUIDv7. Enumerations are checked strings: a text column with a check constraint generated from
the Python `StrEnum`, never free text or a PostgreSQL enum type. Adding a value is a migration
that recreates the constraint, and a test compares every constraint, in the models and in the
migrated database, with its enum so the two cannot drift.

### 4.1 Entities

One parent table holds what every verifiable thing shares. Five tables extend it with
joined-table inheritance: a row in `entities` and a row in the child table with the same id. In
code each is one object.

| Table | Fields |
| --- | --- |
| `entities` | id, kind (`place`, `institution`, `source`, `domain`, `homepage`), status, entered_by, created_at |
| `places` | name, country_code, administrative_level, parent_place_id, government_institution_id |
| `institutions` | name, institution_type, suggested_type (when the type is `other`), place_id, parent_institution_id, procurement_handled_by, homepage_id (the verified one) |
| `sources` | institution_id, webpage_id, source_type, access (`public`, `login`); unique per webpage, institution and type |
| `domains` | name (unique), kind (`official`, `platform`) |
| `homepages` | institution_id, webpage_id, found_on_webpage_id (the trusted page that linked to it; null for a search result), rejected_reason (shown to the next session and the reviewer), trusted_path (section 6.4) |

Composite foreign keys enforce that a place's government is an institution in that place, that
an institution's homepage is one of its own homepages, and that a place's level is one of its
country's levels. The rules that depend on status (an institution's `homepage_id` is verified;
no two institutions have a verified homepage on the same webpage) are enforced in
`status_changes.py`, because status lives on `entities` where a constraint cannot reach it.

### 4.2 Attachments to places and institutions

Each of these has a nullable `place_id` and `institution_id`, with a check that exactly one is
set.

| Table | Fields |
| --- | --- |
| `aliases` | text, language (BCP 47), is_acronym, entered_by; unique per owner and text. Every name a body goes by, in any language. Holds the trigram index for duplicate matching |
| `identifiers` | scheme (`statcan_sgc`, `mamh`, `fips`, `gnis`, `census_gid`, `nces`, `ipeds`), value, official_list_id; one per owner and scheme, one owner per value |
| `metrics` | name (`population`), year, value, official_list_id; one per owner, name and year |

`institution_served_places` (institution_id, place_id) records the places a multi-place body
serves, such as a conservation authority or a health unit. Lists and reviewers fill it, never
the agent.

### 4.3 The web and the evidence

| Table | Fields |
| --- | --- |
| `webpages` | url (normalized, unique), domain_id, redirects_to_url, first_seen_assignment_id. One row per URL the browser or `read_file` opened, or list file the loader read |
| `snapshots` | webpage_id, assignment_id, fetched_at, content_hash, media_type, size, filename, bytes_key, text_key, text_status (`ready`, `partial`, `parsing`, `failed`), text_error, page_count, parsed_pages, pruned_at |
| `evidence` | entity_id, snapshot_id, kind (`appears_on`, `links_to`), quote, locator (a file's page or a list file's line), link_url, assignment_id, entered_by |
| `blocked_attempts` | url, reason, assignment_id, at. A URL the fence refused; it gets no webpage row |
| `official_lists` | name, title, url, sha256, retrieval (`fetched`, `manual`), retrieved_at, snapshot_id; unique per name and hash. One row per file a list loaded, so an identifier or a metric can say where it came from |

A snapshot holds the raw bytes and the extracted text in object storage. Identical bytes fetched
twice share one text, keyed by content hash.

### 4.4 Countries

Country configuration is five tables, so the console can edit it with validation. Seeds fill
them once (section 5.1). The two type tables use the type's name as the primary key, so rows
elsewhere read as words (`hospital`, `tender`), and a rename cascades.

| Table | Fields |
| --- | --- |
| `country_settings` | country_code (key), name, naming_rules (JSON: designators, connectors, leading words, and-words). Configuration only: Canada the place is a row in `places` |
| `administrative_levels` | country_code, name, rank (from the top), government_institution_type, expected_institution_types (array). Key: country and name |
| `institution_types` | name (key), description (shown to the agent). Global |
| `source_types` | name (key), description (shown to the agent). Global |
| `country_institution_types` | country_code, institution_type, expected_source_types (array), name_pattern (optional). Which types a country uses, the sources it expects of each, and what their names look like |

Levels are per country and types are global, so Canada's and the United States' hospitals can
expect different sources without two hospital types. A place's parent must rank above the
place's level, so a municipality under a region or directly under the province both pass. The
arrays are validated by the API rather than by foreign keys, and a type rename updates them in
the same transaction. Platforms are domain rows with kind `platform`, created by the seed. When
a checklist changes, the next assignment reads the new rows.

### 4.5 Work

| Table | Fields |
| --- | --- |
| `runs` | name, country_code, mode (`step`, `auto`), status (`active`, `paused`, `stopped`), filter (JSON: levels, institution types, assignment types, subject ids), is_eval, record_video, created_at |
| `assignments` | run_id, type, subject_id, status, result, budget_requests, budget_tokens, requests_used, tokens_used, requests_since_finding, sessions, handoff_note, summary, types_not_found, last_error, parent_assignment_id, created_at, started_at, finished_at |
| `review_items` | entity_id, rule, question (JSON: what the reviewer sees), kind (the shared question, when there is one), status (`open`, `approved`, `rejected`, `merged`), raised_by_assignment_id, decided_at, note |
| `usage` | assignment_id, kind (`model`, `search`), provider, purpose, units (tokens or requests), cached_units, cost, at |
| `agent_run_events` | assignment_id, session, position, kind (`prompt`, `text`, `tool_call`, `tool_result`, `video`), tool, content (JSON), at. Everything the agent saw, said and did, in order |
| `eval_runs` | run_id, dataset_version, model, settings, cost, started_at, finished_at, gates |
| `eval_scores` | eval_run_id, subject, assignment_type, recall, precision, hits, misses, false_positives |

An assignment's `status` is its lifecycle: `held`, `queued`, `running`, `finished`,
`cancelled`. Its `result` says how a finished one ended: `complete`, `complete_with_gaps`,
`out_of_budget`, `needs_review`, `no_homepage`, `failed`. Keeping them apart means "is it still
going" and "how did it go" are never mixed. A partial unique index allows one held, queued or
running assignment per subject and type.

---

## 5. How data enters the graph

Three ways, in the order a country is built.

### 5.1 Seeds

The seeds are Python modules, not data files. `countries/seeds/shared.py` holds the global
institution and source types and the sources each type is expected to have by default.
`canada.py` and `united_states.py` each hold the country's settings and naming rules, its
levels and the types expected at each, the types it uses with their name patterns, its
platforms, and its anchors: the country and each province and territory (each state, the District
of Columbia and Puerto Rico) with its government and domains, created verified with
`entered_by = manual`. Each is a plain dictionary validated by the same Pydantic models as the
countries API.

`public-atlas seed canada` fills the tables. From then on the tables are the source of truth
and the console edits them. Re-seeding adds what is missing and never deletes rows, but it does
reset the naming rules to the seed's.

### 5.2 Official lists

Where an official list exists, the agent is not asked to find what it holds. Loading a list
takes two parts: a shared loader written once, and one small module per list.

**The shared loader** (`modules/imports/`) never changes when a list is added. It downloads
each file, checks its pinned hash and caches it, or reads a file collected by hand. It turns the
file into lines of text: a CSV or spreadsheet is one line per row (each named sheet in turn), a
JSON file one line per record, a web page its visible text, a PDF goes through the parser, and a
ZIP names the member to use. It stores the file and its text as a snapshot, so a quote can be
checked against it. It then compares the module's entries with the database and prints what
would be added or changed, and what the list no longer has. `--apply` writes the rows. A dry
run rolls back, and a second apply changes nothing.

**One module per list** (`modules/imports/lists/<country>/<region>/<list>.py`, named by its
path, such as `canada/ontario/places`) is the only code written to add a list. It declares:

- `COUNTRY`, the country it loads into;
- `SOURCES`, the files it reads (`ListFile`): each fetched from a URL with its hash pinned, or obtained by hand by steps the module spells out;
- `OVERRIDES` (optional), hand corrections for rows the official files get wrong;
- `entries(opened, rules)`, which receives the opened files and the country's rules, joins them, applies the corrections and returns plain records.

The module knows everything about its list and nothing about the database. The records exist
only while the loader runs:

| Record | Holds | Becomes |
| --- | --- | --- |
| `PlaceEntry` | name, aliases, level, parent, government name, codes, figures (population), homepage URL, a citation per fact | A verified place, its government, identifiers, metrics, a candidate homepage. A place already loaded is found by its code and only gains what is new |
| `InstitutionEntry` | name, aliases, type, place, parent institution, codes, homepage URL, served places, a citation per fact | A verified institution, its served places, a candidate homepage |
| `Citation` | which file and which line a fact came from | An `evidence` row quoting that line, `entered_by = script` |

Every list has a rule test that calls `entries()` on the cached files and checks every record:
codes, populations, names the naming rules give, lower tiers inside upper tiers, overrides
applied, and the expected counts. The 28 lists today:

| Country | Lists |
| --- | --- |
| Canada, federal | `canada/federal`: the Treasury Board's inventory of federal organizations, each under the department heading its portfolio |
| Canada, places | `<province>/places` for all ten provinces and `territories/places`. Each joins the 2021 Census (read through `canada/statcan.py`) to the province's own directory for governments' legal names and websites. Ontario has 40 regions and 414 municipalities; Quebec has 87 MRCs as regions, its municipalities, and its metropolitan communities and the Kativik administration as regional governments with served places |
| Ontario, institutions | `agencies` (provincial agencies under their ministries), `fippa_bodies` (hospitals, colleges and universities), `school_boards`, `libraries`, `conservation_authorities`, `service_managers` (district social services boards), `health_units` and `police_boards`. Bodies listed by city are placed through `communities.py` |
| United States, places | `us/states_counties` (3,197 states and county equivalents) and `us/municipalities` (35,643), from Census population estimates with FIPS codes; `us/government_units` adds each government's legal name, Census of Governments id and `.gov` website |
| United States, institutions | `us/school_districts` (NCES), `us/special_districts` (Census of Governments, typed by function), `us/federal` (Federal Register agencies that published in 2023–2025 or hold a `.gov` domain), `us/universities` (IPEDS public campuses) and `us/transit` (National Transit Database reporters) |

`public-atlas lists manifest` prints every list's files, the checklist for building from
scratch. `lists fetch` and `lists pack` download the fetchable files and bundle the hand-collected
ones.

Lists are also where the bodies under a body come from. `find_institutions` takes a place and
looks for the types its level expects. It is never pointed at a ministry or a department,
because a government that has agencies publishes the list of them, and a list beats a discovery
that starts from one homepage. A hierarchy below a place is loaded from its authority's list, or
it waits until there is one.

The loader creates no assignments, because it has no run. A run finds the work that is due
when it starts (section 7.3).

### 5.3 Agent assignments

Everything else is found by the three assignment types in section 7. Each saves findings with
quotes through tools, and the rules in section 6 decide their status.

---

## 6. How data is verified

### 6.1 The chain of trust

A domain is trusted only if a seed listed it as an anchor, a reviewer approved it, or a homepage
assignment verified it. Anything quoted from a trusted domain, where the quote names the thing
saved, is verified.

1. Anchors and official lists are trusted from the start.
2. The agent browses trusted domains and saves what it finds with a quote. The backend checks the quote and verifies the finding.
3. When a trusted page links to a page on a new domain, the agent saves it as a candidate homepage. The domain becomes a candidate and the institution gets a `find_homepage` assignment.
4. That assignment, the only kind allowed to open a candidate domain, quotes the domain's pages. If the domain checks pass, the domain is trusted.
5. Trust spreads: the new domain's pages now verify what they name.

### 6.2 The quote check

A quote must appear word for word in the newest stored copy of the page, start and end on word
boundaries, be at least twelve characters long, and, for a place, institution or homepage,
contain a name or acronym of the thing saved. The comparison folds case, collapses whitespace,
evens out typographic punctuation and repairs mojibake, then tries once more with no whitespace
at all. A file's text is searched page by page. An HTML page is checked in its rendered text and
then in its stored HTML. A refused quote returns the closest passage on the page, so the agent
can copy the page's own words. A page never opened cannot vouch for anything.

### 6.3 The domain checks

Before a candidate domain becomes trusted:

- a trusted page links the institution to the candidate domain and the link is in the stored copy of that page, or the claim came from a search and a reviewer must approve it;
- every quote the agent gives is in the candidate domain's own stored pages;
- at least one quote names the institution, allowing the opening words of a recorded name or the place name with another designator;
- no other verified institution owns that homepage.

A check the agent can fix is sent back to it, up to three times. Disagreement between the agent
and the checks goes to review, never to `rejected`. A dead site is rejected. A site that
belongs to another public body withdraws only this institution's claim.

A redirect from the candidate to another domain, on record in the browser, rejects the old
domain and moves the claim to the new one. Other institutions that claimed the old domain get a
new `find_homepage`. If the new domain is trusted, the homepage is verified. If it is a
platform, or another institution's verified homepage, the claim goes to review.

When a homepage is verified, the institution's other open claims are superseded. A superseded
claim's candidate domain (often the old address of a government that moved) is rejected with it,
unless another institution still claims a page there.

### 6.4 Third-party platforms

A platform is fetchable but never trusted. A page on one becomes a verified source only when a
trusted page links to it and the page names the institution. The link is recorded as evidence
against the trusted page. A platform page that fails this is saved as a candidate and sent to
review.

One exception is scoped to a path. When an institution's verified homepage is itself on a
platform, verifying it sets `trusted_path` to the homepage's URL prefix. Pages under that prefix
verify what they name for that one institution, as a trusted domain's pages do. The rest of the
platform stays untrusted.

### 6.5 The review queue

A review item records the rule that raised it:

| Rule | Raised when |
| --- | --- |
| `type_level` | A known type is saved at a level the country does not expect it under |
| `new_type` | A body is saved as `other`, with the type the agent would have given it |
| `name_pattern` | A name misses its type's pattern |
| `duplicate` | The duplicate search left the agent unsure |
| `domain_checks` | The domain checks failed in a way the agent cannot fix |
| `domain_moved` | A candidate homepage redirected somewhere the rules cannot follow |
| `no_homepage` | The searches found no homepage |
| `gaps` | A discovery assignment finished with expected types missing |
| `platform_source`, `platform_homepage` | A source or homepage on a platform that no trusted page links to |
| `agent` | The agent asked |

Raising an item sets a candidate entity to `needs_review`. A verified or rejected entity keeps
its status. An entity has at most one open item; a second reason is added to it. A reviewer
approves, rejects or merges, and each decision runs the same function the rules run, so nothing
bypasses them. The work a decision spawns goes into the run that raised the item, or the
country's newest run.

`type_level` and `new_type` items ask a shared question ("may a library sit under a region"),
so they carry a `kind`. The queue shows each kind as one row, decided once for every item in
it, and these items settle on their own when the country's tables change to answer them.

### 6.6 One door per state change

`graph/status_changes.py` holds one function per transition: verify or reject a place,
institution, source, homepage or domain; mark a domain moved; send an entity to review; merge
two entities. Each sets the status, records who did it, and returns the follow-up work for the
caller to spawn. The agent's findings, the reviewer, the list loader, the country seed and the
eval harness all call these functions, and nothing else changes a status.

---

## 7. Runs and assignments

### 7.1 Runs

A run is how a person controls work. It has a filter (a country plus any of levels, institution
types, assignment types or an explicit list of subjects) and a mode.

- **Step mode.** Assignments are created `held`. A person releases them from the console or the CLI, a few at a time. For development and testing.
- **Auto mode.** Assignments are queued at once. For a whole province.

Pausing stops the worker from starting the run's assignments. When the worker picks up a job of
a paused run, it puts the job back with a 30-second delay, so paused work stays `queued`
(`held` means step mode and nothing else) and resuming has nothing to undo. A running session
finishes first. Stopping cancels everything held or queued; a running assignment is cancelled
when its session ends. Work spawned outside the run's filter, or into a stopped run, is dropped.

### 7.2 Assignment types

| Type | One per | Finds | Ends `complete` when | Budget |
| --- | --- | --- | --- | --- |
| `find_homepage` | Institution without a verified homepage | Its official homepage, verifying the domain if new | The homepage is verified, or sent to review when no trusted page links to it | 60 requests, 4M tokens |
| `find_institutions` | Place | The public bodies under it, with candidate homepages | Every type expected at the place's level is saved or named in `types_not_found` | 250 requests, 20M tokens |
| `find_sources` | Institution with a verified homepage | Its sources | Every source type expected for its institution type is saved or named in `types_not_found` | 120 requests, 10M tokens |

Other results, for every type: `out_of_budget` when the budget runs out, `needs_review` when the
agent and the checks disagree or the agent sends its candidate to review, and `failed` when the
job crashed past its retries or the subject no longer exists. A discovery assignment whose
finish is refused for missing types, and which then finishes short again, ends
`complete_with_gaps` with a `gaps` review item, so a person can confirm the types do not exist
there or add leads. A `find_homepage` whose searches found nothing ends `no_homepage` with a
review item, so a person can add the address.

`find_homepage` has three paths. A candidate on an already trusted domain: open it and quote it.
A candidate on a new domain: verify the domain with the checks in section 6.3. No candidate:
search the web, open the results, and save and verify the one that is the institution's own. Two
institutions claiming the same new domain is fine: the first verifies it and the second finds it
trusted.

### 7.3 Spawning

The backend creates follow-up work; the agent cannot. One function inserts each assignment and
queues or holds it according to the run's mode.

- **A run starts:** `find_homepage` for every institution in its filter without a verified homepage or a claim in review, and `find_sources` or `find_institutions` wherever those are due.
- **A homepage verified:** `find_sources` for the institution, and `find_institutions` for the place when the institution is its government.
- **An assignment finished:** `find_homepage` for every other institution it recorded evidence on that has no verified homepage and no decision pending. This runs for every result except `failed`.
- **A domain rejected:** `find_homepage` again for every institution that claimed it.
- **A reviewer approves:** whatever the rule path would have spawned.

The partial unique index on open assignments (section 4.5) means concurrent workers cannot
queue the same work twice.

### 7.4 Sessions

A session runs until the agent calls its finishing tool, the budget runs out, the
context passes half the model's window, or the assignment stalls. At half full, the agent writes
a handoff note and a fresh session starts from the database and the note.

A discovery assignment stalls when it keeps making requests without saving anything. At thirty
requests since the last finding, counted across sessions, the next tool result tells the agent
to finish unless it has a specific page left to open. At sixty, the runner ends the assignment
`complete` with a summary written by the handoff model.

One job runs at most twenty sessions, then requeues itself. A job that fails five times
finishes the assignment as `failed`. A worker whose heartbeat stops has its jobs requeued by a
sweep that runs every ten minutes.

---

## 8. The agent

A worker on the `assignment` queue picks up an assignment and runs a Pydantic AI agent on it.
The briefing has the standing instructions for the type; the country's levels and types with
their descriptions; the subject; the checklist of types still to account for; counts of the
types already recorded under the place, marked "from an official list" where a loader wrote
them so the agent skips directories that only repeat them; where a body may be saved; earlier
homepage claims and why they were rejected; the pages already visited; and the last handoff
note. It never includes the old transcript.

### 8.1 Tools

| Tool | Types | Does |
| --- | --- | --- |
| `navigate`, `snapshot`, `click`, `type_text`, `press_key`, `select_option`, `hover`, `scroll`, `wait_for`, `go_back`, `go_forward`, `tabs`, `get_text`, `screenshot` | all | Browse a real Chromium page on an allowed domain |
| `read_file(url, chunk)` | all | Download a PDF, spreadsheet or other file, store it, parse it, return one chunk of text |
| `status` | all | What this assignment has saved, the checklist, the files parsing |
| `request_review` | all | Raise a review item |
| `save_institution` | all | Save a body with its type, parent, procurement_handled_by, quote and page. Returns likely duplicates |
| `save_homepage` | all | Save a homepage with the link quote from a trusted page, or the page's own quote on a trusted domain |
| `save_source` | `find_sources` | Save a source with its type, quote and page |
| `search(query, domains)` | `find_homepage` | Web search, up to three domains per query. The results' sites join the session's allowlist. Five per assignment, and only when a search provider is configured |
| `confirm_domain`, `reject_domain`, `domain_moved` | `find_homepage` | End the domain decision. The checks run before any status changes |
| `finish(summary, types_not_found)` | all | End the assignment. Refused once if the checklist is short; a second short finish ends `complete_with_gaps` |

The tools are the findings functions, registered with Pydantic AI through one adapter. Each
returns a typed result that is rendered to text only at that adapter.

### 8.2 The fence and page capture

The session's allowlist is every trusted domain and every platform, with subdomains. A
`find_homepage` session adds its candidate domain and the sites its searches return. A route
guard refuses any other navigation or script request before it leaves the browser and records a
blocked attempt. Private and link-local addresses are always refused. The same policy applies
`robots.txt` (including `Crawl-delay`, capped at 60 seconds), three seconds between loads on one
host within a worker, a 120-second rest for a host that answers 429, and a current Chrome user
agent. Images, fonts and media are not fetched.

Every page the agent lands on is captured without the agent doing anything. Once the page goes
quiet, its HTML (with its frames' links) and its rendered text are stored as a snapshot, and a
webpage row is written. The capture hook receives plain values (URL, title, HTML, text, links),
so the evidence module never touches the browser. When an assignment finishes, snapshots that no
evidence cites are pruned to their hash and metadata.

When a run has `record_video` set, the browser records every page, and each session's video is
stored and noted as a `video` event. It is meant for watching a single assignment and is left
off for long runs. Daily jobs delete videos after `video_keep_days` (7) and events after
`events_keep_days` (90). Findings, usage and summaries are never purged.

### 8.3 Files

PDFs and spreadsheets go through `read_file`. The type is detected from the bytes and the
original is stored. Structured text (CSV, JSON, XML) is its own text; everything else is parsed
by Docling on the `parse` queue, ten pages at a time. A file is parsed only as far as the agent
reads it: the first range when it is fetched, and the next each time the agent asks for a chunk
past the parsed pages. A 400-page budget book the agent opens to classify costs one range, not
forty. In between, its text is `partial`, and the agent is told how far it goes. A file already
parsed for any assignment shares its text.

OCR is on, for scanned minutes. Table structure recognition is off, because the agent reads a
file only to classify it and to quote a line. The exception is an official list whose records
are a PDF table's rows: its `ListFile` asks for tables, so each row becomes a line a citation can
name.

Limits, all settings: a file over 500 pages is not parsed, a range that takes over three minutes
fails, and a parse worker whose memory passes 4 GB retires after its job. `read_file` waits up to
ninety seconds for the parse queue, then tells the agent to check `status` later.

### 8.4 Model

The model and reasoning effort are set per assignment type in `assignments/descriptors.py`, and
prices are in `assignments/prices.toml`. Today all three types use `gpt-6-luna` at `xhigh`, and
handoff notes and summaries use it at `medium`.

---

## 9. Derived relationships

There is no relationship table and no relationship tool. Links between bodies are read from what
is already stored:

- `institution.parent_institution_id`: the body it sits under, set from the page that says so or defaulted to the place's government.
- `institution.procurement_handled_by`: when `parent`, the parent buys for this body.
- `place.government_institution_id`: the government of a place, to which every other institution under the place is related.
- `institution_served_places`: the places a multi-place body serves.

The console draws these as a graph and the evals score parent links.

---

## 10. Evaluation

The dataset (`modules/evals/dataset/`, the project's only YAML) is thirteen hand-labelled
subjects, each listing every institution, parent link, homepage and source it should yield: ten
Ontario municipalities and three United States subjects (a city, a county and a school
district). There is also a file of 25 Ontario governments scored on `find_homepage` alone. Each
file names its country, and a run works one country's files against that country's seed. The
dataset's own README holds the labelling rules.

`public-atlas eval run` works a quick set of five Ontario subjects and the homepage file, chosen
for coverage over size so it finishes in an hour or two; `--all` works every subject. An eval run
is a run with `is_eval` set, built in a separate database (`public_atlas_evals`) from the same
settings with a different URL. The harness resets that database, seeds the country with every
assignment held, seeds each subject's place, government, trusted domains and homepage, then
queues the subject's `find_sources` and, for a place, its `find_institutions`. It serves the
queues in its own process (the parse worker in a child process), then scores and prices the
results. Scores go to `eval_runs` and `eval_scores` in the main database, so history survives a
reset.

The scorer reports recall and precision per assignment type, the reason for every miss, and the
cost per subject, and checks three gates:

| Gate | Assignment type | Recall |
| --- | --- | --- |
| homepages | `find_homepage`, on the homepage file | 0.99 |
| institutions | `find_institutions`, excluding parent links | 0.95 |
| sources | `find_sources`, over procurement, council meetings, board meetings and budgets | 0.90 |

Without running the agent, `eval validate` checks the dataset files, `eval evidence` fetches each
evidence URL and checks its quote is on the page, and `eval score` scores an existing database.

---

## 11. Console

A Next.js app with no authentication: it is an operator's tool. A sidebar groups the pages:

- **Data**
  - **Saved lists** (the home page): institution queries saved in the browser, per database.
  - **Institutions**: a table filtered by place, country, level, type, status and population, and a detail page with aliases, type, parent, homepage, the bodies under it, sources by type, and every evidence quote linked to its snapshot.
  - **Places**: the same for places.
  - **Graph**: places and the institutions under them as a force-directed graph, centred on any place.
- **Pipeline**
  - **Runs**: list, detail and a new-run form. Start a run with a filter and a mode; pause, stop and release held assignments; see progress and cost.
  - **Assignments**: a list with filters, and a detail page with the session's events in order (prompt, the model's words, tool calls and results), the video when recorded, findings, spend and result.
  - **Review queue**: one table, searched and filtered by status, rule, entity, country and size, where the items of one kind share a row. An item opens as its question in a sentence, with its entity beside the ones the question names (a duplicate beside its matches), why it was raised, its history, and its evidence with the quote highlighted. Approve, reject or merge, then move to the next open item.
- **Quality**
  - **Evals**: eval runs over time, with scores against the gates by type and subject, and cost.
- **Country config**: settings, levels with their expected types, institution and source types, and each country's use of a type, editable with validation.
- **Settings**: theme, and a switch between the main and the eval database.

---

## 12. Tech stack and code layout

| Layer | Choice |
| --- | --- |
| API | Python 3.14, FastAPI |
| Database | PostgreSQL, SQLAlchemy 2 async, Alembic, `pg_trgm` for duplicate matching |
| Jobs | Procrastinate on the same database. Queues: `assignment`, `parse`, `default` |
| Agent | Pydantic AI; model and reasoning effort per assignment type |
| Browser | Playwright Chromium, behind one policy object (`integrations/browser/`) |
| Parsing | Docling, installed only on the parse worker (the `parse-cpu` or `parse-cu130` group) |
| Storage | S3-compatible: RustFS locally, Cloudflare R2 hosted |
| Search | Brave Search, off unless configured |
| Console | Next.js 16, shadcn/ui on Base UI, TanStack Query, Form and Table, a client generated from the API's OpenAPI schema |
| Tracing | Logfire when configured; cost always comes from the `usage` table |

Settings come from `PUBLIC_ATLAS_*` environment variables, documented in
`apps/server/.env.example`. There are five processes (the API, a `default`-queue worker, an
`assignment` worker, a `parse` worker and the console) built into four images (`server` runs the
API and the default worker), which GitHub Actions publishes after CI passes on `main`.

### 12.1 Server layout

```
apps/server/src/public_atlas/
  main.py, asgi.py        the FastAPI app; calls build_resources once
  resources.py            build_resources(settings): database, store, searcher, model, jobs
  config.py               Settings: deployment values only, no product data
  cli.py                  public-atlas: seed, load-list, lists, run, eval, worker
  db/                     base, session, checked strings, migrations
  integrations/           storage, search, parse, browser, ai: one port each
  jobs/                   Procrastinate wrapper, worker, stalled sweep, queue purge
  modules/
    countries/            the five country tables, seeds, naming rules, CountryRules
    graph/                places, institutions, sources, domains, homepages, webpages, aliases,
                          identifiers, metrics, duplicate search, subgraph, status_changes.py
    evidence/             snapshots, evidence, quote_checks.py, capture.py, files, parse jobs
    review/               review items, kinds, approve, reject, merge
    assignments/          runs, assignments, lifecycle, spawning, budgets, prices, the run job
    agent/                briefing, tools, findings, runner, prompts, events, video
    imports/              the shared list loader, and lists/ with one module per official list
    evals/                dataset, harness, scorer
    health/               health checks for the API, database and storage
  shared/                 exceptions, logs, middleware, pagination, telemetry, text helpers
```

Every function that needs the database, the store or the model receives it as an argument.
Nothing reads settings at import time. Tests and the eval harness call `build_resources` with
their own settings.

### 12.2 Rules for the code

- One word per concept, from [glossary.md](glossary.md). No synonyms: `assignment`, not `item` or `task`; `homepage`, not `website`; `finish`, not `complete` or `close`.
- A status changes only in `status_changes.py`. An assignment's status changes only in `assignments/lifecycle.py`.
- Tool results and refusals are typed values; prose is rendered at the tool edge.
- A module uses another through its public files (`service.py`, `models.py`, and its schemas and rules), never its internals. A cycle means two things are one module.
- Product data (place names, prices, model names) lives in tables, seeds or data files, never in `Settings`.
