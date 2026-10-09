# Public Atlas: product and technical specification

This is the design for the final rewrite of Public Atlas. Earlier versions live in
`../archived-public-atlas-v1` and `../archived-maplegraph-v2`; the lessons
from them are folded in here, and `todo.md` holds the build order.

**Contents**

1. [What Public Atlas is](#1-what-public-atlas-is)
2. [Design principles](#2-design-principles)
3. [Concepts and words](#3-concepts-and-words)
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

Public Atlas builds a map of the public sector for vendors who sell to
governments. For each public body it records what it is, where it is, which
body buys on its behalf, its official web page, and the web pages that carry
procurement signals: budgets, capital plans, council and board minutes,
procurement portals, open tenders, contract awards and strategic plans.

Selling to government needs three things in order: a map of institutions and
their signal sources, continuous collection of what those sources publish, and
analysis that turns the collected text into buying signals. Public Atlas is
the first of the three. It finds institutions and sources. It does not read
the sources' documents for their contents.

An AI agent does the finding by browsing official websites. The agent cannot
simply assert a fact. Every fact comes with a quote, the system keeps a stored
copy of the page, and code checks that the quote is really on it. Only then is
the fact marked verified. What the rules cannot decide goes to a human through
a review queue.

### 1.1 Goals

- **Complete coverage.** Every place and public institution in a country, measured against a hand-labelled dataset, not the agent's own sense of done.
- **Auditable trust.** Every verified fact has a chain of evidence back to an official register or a domain a person verified by hand.
- **Sources mapped to institutions.** Each signal source is linked to the body it belongs to and typed.
- **Controlled runs.** Work can be started, paused, stopped and filtered by place, level and type, in a careful step-by-step mode for development and a hands-off mode for an entire country, or part of a country.
- **Bounded cost.** The agent reaches only approved domains, within a budget per assignment, and every model and search call is priced.

### 1.2 Pilot

The pilot is Ontario: the province, its 444 municipal and regional
governments, the public bodies under them and their sources. Targets:

| Measure | Target | How it is measured |
| --- | --- | --- |
| Places against the official register | 100% | A unit test on the Ontario places list module |
| Homepage of each government correct | 99% or more | The homepage assignment scored on the 25-government eval file |
| Institution recall against the eval dataset | 95% or more | The scorer (agent eval) |
| Source recall for procurement, minutes and budgets | 90% or more | The scorer (agent eval) |

---

## 2. Design principles

1. **State lives in the database, not in the agent's context.** Any agent session can be thrown away and a new one picks up from the database.
2. **One assignment per session.** Each session works one bounded assignment from a short briefing. The backend creates follow-up work; the agent never creates work.
3. **General tools, hard fences.** The agent gets a few browsing tools and decides how to use them. The list of allowed domains is enforced in code.
4. **The agent proposes, rules verify.** Only code or a human marks something verified. The rules check two things: the quote is on a stored copy of the page, and the quote names the thing being saved.
5. **What a register already lists is not asked of the agent.** Places come from the statistics office. The agent is spent on what no list gives.
6. **Never drop a public body for want of a type.** A body with no matching type is saved as `other` and sent to review.
7. **Relationships are derived, not recorded.** The agent saves facts about one body at a time. Links between bodies come from foreign keys.
8. **Every state change goes through one door.** A domain becomes trusted, a homepage becomes verified, an institution is approved: each has one function, called by the rules, by the reviewer, by the loader and by the country reload alike.
9. **Plain names.** Code uses everyday words, one word per concept (`glossary.md`), even when the name gets longer.

---

## 3. Concepts and words

- **Place**: a unit of the administrative hierarchy: Canada, Ontario, York Region, Markham. Places nest. Each has an administrative level.
- **Institution**: a public body that exists and may buy things: a government, a ministry, a school board, a transit agency, a hospital.
- **Government institution**: the institution that is a place's own government: the City of Toronto for the place Toronto.
- **Source**: a web page that carries procurement signals for one institution, with a source type.
- **Homepage**: an institution's official starting page on the web. A claim, with a status, until verified.
- **Webpage**: any URL the browser visited. A log, not a claim.
- **Domain**: a website address such as `toronto.ca`. The unit of trust and of the browser allowlist.
- **Snapshot**: a stored copy of a page or file as fetched, plus its extracted text.
- **Evidence**: a quote from a snapshot that supports an entity.
- **Entity status**: `candidate`, `verified`, `rejected`, `needs_review`. Shared by places, institutions, sources, domains and homepages.
- **Trust**: a domain is trusted when its status is `verified` and its kind is `official`. A quote from a trusted domain verifies what it names.
- **Platform**: a domain anyone can publish on (YouTube, a tenders portal). Fetchable, never trusted.
- **Entered by**: how a row got here: `manual`, `script` or `agent`. On every entity and every evidence row.
- **Procurement handled by**: `self` or `parent`. Whether an institution buys on its own account or its parent buys for it.
- **Run**: a batch of work with a filter and a mode. The unit a person starts, pauses and stops.
- **Assignment**: one bounded piece of agent work on one subject, inside a run.
- **Review item**: a question a human must answer about one entity.
- **Official list**: a file an authority publishes that the loader reads instead of the agent: a census table of places, a directory of governments, a ministry's list of hospitals. A register is an official list with a code per row.
- **Anchor**: a place whose government and domains the seed created by hand, as verified. Discovery starts there. Not a table: the rows are ordinary places, institutions and domains with `entered_by = manual`.

---

## 4. Data model

Every id is a UUIDv7. Enumerations are checked strings: a text column with a
check constraint generated from the Python `StrEnum`, never free text or a
PostgreSQL enum type. Adding a value is a three-line migration, and a test
compares each constraint with its enum so the two cannot drift. Everything
below lives in one PostgreSQL database.

### 4.1 Entities

One parent table holds what every verifiable thing shares. Five tables extend
it with joined-table inheritance: a row in `entities` and a row in the child
table with the same id. In code each is one object.

| Table | Fields |
| --- | --- |
| `entities` | id, kind (`place`, `institution`, `source`, `domain`, `homepage`), status, entered_by, created_at |
| `places` | name, country_code, administrative_level, parent_place_id, government_institution_id |
| `institutions` | name, institution_type, suggested_type (text, when the type is `other`), place_id, parent_institution_id, procurement_handled_by, homepage_id (the verified one) |
| `sources` | institution_id, webpage_id, source_type, access (`public`, `login`); unique per webpage, institution and type |
| `domains` | name, kind (`official`, `platform`) |
| `homepages` | institution_id, webpage_id, found_on_webpage_id (the trusted page that linked to it, null for a search result or a directory link), rejected_reason (why the claim was rejected, for the briefing and the reviewer), trusted_path (set when a verified homepage sits on a platform: the URL prefix whose pages vouch for this institution, section 6.4) |

Rules the tables enforce: a place's government is an institution whose
`place_id` is that place. An institution's `homepage_id` points at a homepage
whose status is `verified`. Two institutions cannot both have a verified
homepage on the same webpage.

### 4.2 Attachments to places and institutions

These belong only to places and institutions. Each has two nullable columns,
`place_id` and `institution_id`, with a check that exactly one is set.

| Table | Fields |
| --- | --- |
| `aliases` | text, language (BCP 47), is_acronym, entered_by; unique per owner and text. Every name a body goes by, in any language. The trigram index for duplicate matching lives here |
| `identifiers` | scheme (`statcan_sgc`, `mamh`, `fips`, `gnis`, `census_gid`, `nces`, `ipeds`), value, official_list_id; one per owner and scheme, one owner per value |
| `metrics` | name (`population`), year, value, official_list_id |

`institution_served_places` (institution_id, place_id) records the places a
multi-place body serves, such as a conservation authority or a regional
police board. Filled by scripts and reviewers, never by the agent. Most
institutions have no rows here.

### 4.3 The web and the evidence

| Table | Fields |
| --- | --- |
| `webpages` | url (normalized), domain_id, redirects_to_url, first_seen_assignment_id. One row per URL the browser or `read_file` opened or was refused |
| `snapshots` | webpage_id, assignment_id, fetched_at, content_hash, media_type, size, filename, bytes_key, text_key, text_status (`ready`, `parsing`, `failed`), text_error (why extraction failed), page_count, pruned_at |
| `evidence` | entity_id, snapshot_id, kind (`appears_on`, `links_to`), quote, locator (page number), link_url, assignment_id, entered_by |
| `blocked_attempts` | url, reason, assignment_id, at. A URL the fence refused |
| `official_lists` | name, title, url, sha256, retrieval (`fetched`, `manual`), retrieved_at, snapshot_id. One row per source file a list module loaded (section 5.2), written by the loader, so an identifier or a metric can say which list it came from and whether that file was fetched or collected by hand |

A snapshot holds both the raw bytes and the extracted text. Identical bytes
fetched twice share one text, keyed by content hash.

### 4.4 Countries

What v1 kept in YAML and a JSON column is now five tables, so the console can
edit it with validation. Python seed modules fill them once (section 5.1).
Table names are full words. The two type tables use the type's name as the
primary key, so rows elsewhere read as words (`hospital`, `tender`) instead
of ids; a rename cascades.

| Table | Fields |
| --- | --- |
| `country_settings` | country_code (primary key), name, naming_rules (JSON: designators, connectors, leading words, and-words). Configuration only: Canada the place is a normal row in `places` |
| `administrative_levels` | country_code, name, rank (from the top), government_institution_type, expected_institution_types (text array). Key: country and name |
| `institution_types` | name (primary key), description (shown to the agent). Global: one `hospital` for every country |
| `source_types` | name (primary key), description (shown to the agent). Global |
| `country_institution_types` | country_code, institution_type, expected_source_types (text array), name_pattern (optional). Key: country and type. How this country uses a type: which sources to expect for it and what its names look like. The rows also say which types the country uses at all |

Why this shape:

- **Levels are per country, types are global, and a country's use of a type is per country.** So the level-to-type checklist is an array on the level row, and the type-to-source checklist is an array on the per-country type row. Canada's and the United States' hospitals expect different sources without there being two hospital types.
- **No parent table for levels.** A place's parent must have a lower rank than the place's own level. A municipality under a region or directly under the province both pass.
- **No anchors table.** An anchor is a place whose government and domains the seed created by hand, as verified with `entered_by = manual`. Discovery starts wherever a trusted domain exists.
- **Platforms are domain rows** with kind `platform`, created by the seed.
- **The arrays are validated by the API**, not by a foreign key, which is the one thing this shape gives up. If a type is renamed the arrays are updated in the same transaction.

The naming rules stay JSON because they are a rule set, not rows. When a
checklist changes, the next assignment reads the new rows. The loader's
record of which files it loaded (`official_lists`, section 5.2) is not country data
and sits with the import tables.

### 4.5 Work

| Table | Fields |
| --- | --- |
| `runs` | name, country_code, mode (`step`, `auto`), status (`active`, `paused`, `stopped`), filter (JSON: administrative levels, institution types, assignment types, subject ids), is_eval, record_video, created_at |
| `assignments` | run_id, type, subject_id (an entity), status, result, budget_requests, budget_tokens, requests_used, tokens_used, requests_since_finding (the stall rule's count, section 7.4), sessions, handoff_note, summary, types_not_found (JSON), last_error, parent_assignment_id |
| `review_items` | entity_id, rule, question (JSON: what the reviewer sees), kind (the shared question, when there is one), status (`open`, `approved`, `rejected`, `merged`), raised_by_assignment_id, decided_at, note |
| `usage` | assignment_id, kind (`model`, `search`), provider, purpose, units (tokens or requests), cached_units, cost, at |
| `agent_run_events` | assignment_id, session, position, kind (`prompt`, `text`, `tool_call`, `tool_result`, `video`), tool, content (JSON: the prompt, the model's words, the arguments, the result, or a storage key), at. Everything the agent saw, said and did, in order, written from the session's message list when it ends |
| `eval_runs` | run_id, dataset_version, model, settings (JSON), cost, started_at, finished_at, gates (JSON) |
| `eval_scores` | eval_run_id, subject, assignment_type, recall, precision, hits (JSON), misses (JSON), false_positives (JSON) |

Assignment `status` is the lifecycle: `held`, `queued`, `running`, `finished`,
`cancelled`. `result` says how a finished one ended: `complete`,
`complete_with_gaps`, `out_of_budget`, `needs_review`, `no_homepage`,
`failed`. The two are separate so "is it still going" and "how did it go" are
never mixed.

---

## 5. How data enters the graph

Three doors, in the order a country is built.

### 5.1 Seeds (manual, once)

The seeds are Python modules, not data files. `countries/seeds/shared.py` holds
the global institution types and source types, and the default list of
expected sources per type that a country starts from. `countries/seeds/canada.py`
holds Canada's settings row and naming rules, its administrative levels with
the types expected at each, its `country_institution_types` rows (which
types Canada uses, with any change to the default sources and its name
patterns), its platforms, and its anchors: Canada and each province and
territory with its government institution and domains, all created verified
with `entered_by = manual`. Each is a plain dictionary validated by the same
Pydantic models the countries API uses, so the schema lives in one place.
`public-atlas seed canada` fills the tables. From then on the tables are the
truth and the console edits them. Re-seeding adds what is missing and never
deletes.

### 5.2 Official lists (scripted)

Where an official list exists, the agent is not asked to find what it holds.
A statistics office lists every place with a code; a province's directory
lists each municipal government's name and website; a ministry lists its hospitals.
Loading a list is two parts: a shared loader written once, and one small
module per list.

**The shared loader** (`modules/imports/`) never changes when a list is
added. It downloads each source file, checks its hash and caches it; turns
the file into lines of text (a CSV or spreadsheet is one line per row with
the header first, JSON is one line per record, a web page is its visible
text, a PDF goes through the parser; a ZIP names the member file to use);
stores the file and its text as a snapshot so a quote can be checked against
it; compares the entries the module produces with what the database holds
and prints what would be added, changed or removed; and, with `--apply`,
writes the rows. A rerun changes nothing the second time.

**One module per list** (`modules/imports/lists/<country>/<region>/<list>.py`,
named by that path: `canada/ontario/places`) is the only code written to add a
list. It holds `SOURCES`, the files it reads (`ListFile`), each fetched from
its URL with its hash pinned or obtained by hand by the steps the module spells
out; `OVERRIDES`, a dictionary of hand corrections for the rows the official
files get wrong; and `entries()`, one function that receives the opened files
(rows for a CSV, the parsed object for JSON, text lines for a page or PDF),
joins them, applies the corrections and returns plain records. The module
knows everything about its list and nothing about the database. `public-atlas
lists manifest` prints every list's files, the from-scratch checklist.

The records are Pydantic models that exist only while the loader runs:

| Record | Holds | Becomes |
| --- | --- | --- |
| `PlaceEntry` | name, level, parent, government name, code, population, homepage URL, a citation per fact | A verified `places` row, its government `institutions` row, an `identifiers` row, a `metrics` row, a candidate `homepages` row |
| `InstitutionEntry` | name, type, place (with its level and parent when the name alone does not say which), parent institution, homepage URL, served places, a citation per fact | A verified `institutions` row, `institution_served_places` rows, a candidate `homepages` row |
| `Citation` | which source and which line a fact came from | An `evidence` row quoting that line, `entered_by = script` |

The first module is `lists/canada/ontario/places.py`: three sources (the
census population table and geography file, shared with every province
through `lists/canada/statcan.py`, and the Ontario municipal directory), about
twenty overrides, and an `entries()` that returns 454 `PlaceEntry` records.
`public-atlas load-list canada/ontario/places` shows the diff; `--apply` loads
it. The second, `lists/canada/ontario/agencies.py`, reads the Treasury Board's
list of the province's agencies and returns `InstitutionEntry` records, each
agency under its ministry; the same command loads it. `fippa_bodies.py`
(hospitals, colleges and universities) and `school_boards.py` are the same
again, attaching each body to the municipality of its address; `libraries.py`,
`conservation_authorities.py`, `service_managers.py` (the district social services
boards) and `health_units.py` follow, the last two with the places each body serves. The
United States starts the same way: `lists/us/states_counties.py` and `lists/us/municipalities.py`
read the Census Bureau's population estimates and code files through `lists/us/census.py`
and return the 3,197 states and county equivalents and the 35,643 municipalities as
`PlaceEntry` records, each with its FIPS code and 2025 population. `lists/us/government_units.py`
returns those places again from the Census of Governments' list of government units and the
`.gov` registry, each with its government's legal name, its Census of Governments id and its
website as a candidate homepage: a `PlaceEntry` for a place already loaded is found by its code
and adds only what is new. `lists/us/school_districts.py` (the NCES directory of local education
agencies, each with its NCES id) and `lists/us/special_districts.py` (the Census of Governments'
special districts, typed by function) return `InstitutionEntry` records under the county of
each body's office. `lists/us/federal.py` (the Federal Register's agencies, kept to those that
published in 2023 to 2025 or hold a `.gov` domain in their own name, each under its parent at
the country), `lists/us/universities.py` (IPEDS' public campuses, each with its IPEDS id at
its county) and `lists/us/transit.py` (the National Transit Database's public reporters, one
body per agency, at the government it serves or the city of its address) do the same.
Canada continues with `lists/canada/federal.py` (the Treasury Board's inventory of federal
organizations, each under the department heading its portfolio at Canada) and
`lists/canada/quebec/places.py` (the census joined to the province's municipal directory by
code: the 87 MRCs as regions, each with the directory's `mamh` code and, for the 81 the census
counts as divisions, the division's code; the municipalities under the MRC the directory names;
and the communautés métropolitaines and the Kativik administration as `regional_government`
institutions with served places).


This is also where the bodies under a body come from. `find_institutions`
takes a place and finds the types its level expects; it is never pointed at a
ministry or a department, because a government that has agencies publishes
the list of them, and a list beats a discovery that starts from one homepage.
A hierarchy below a place is loaded from the list its authority publishes, or
it waits until there is one.

A rule test per list (`tests/unit/imports/lists/canada/ontario/test_places.py`) calls
`entries()` on the cached files and checks every record: a numeric code, a
population, a government name the naming rules give, a lower tier inside its
upper tier, the overrides applied, and the expected counts.

### 5.3 Agent assignments (everything else)

Three assignment types (section 7) find homepages, institutions and sources.
Each saves findings with quotes through tools; the rules in section 6 decide
their status.

---

## 6. How data is verified

### 6.1 The chain of trust

A domain is trusted only if a person listed it as an anchor, a reviewer
approved it, or a homepage assignment verified it. Anything quoted from a
trusted domain, where the quote names the thing saved, is verified.

1. Anchors and registers are trusted from the start.
2. The agent browses trusted domains and saves what it finds with a quote. The backend checks the quote and verifies the finding.
3. When a trusted page links to a page on a new domain, the agent saves it as a candidate homepage. The domain becomes a candidate and the institution gets a homepage assignment.
4. That assignment opens the candidate domain, the only assignment allowed to, and quotes its pages. Four checks pass and the domain is trusted.
5. Trust spreads: the new domain's pages now verify what they name.

### 6.2 The quote check

A quote must exist word for word in the stored copy of the page, be at least
twelve characters, and, for a place, institution or homepage, contain a name
or acronym of the thing saved. Comparison folds case, collapses whitespace,
evens out typographic punctuation and repairs mojibake, then tries once more
with no whitespace at all. An HTML page is checked in its rendered text and
then in its stored HTML. A refused quote returns the closest passage on the
page, so the agent can copy the page's own words. A page never opened cannot
vouch for anything.

### 6.3 The domain checks

Before a candidate domain becomes trusted:

- a trusted page links the institution to the candidate domain, to the homepage or to any other page on it, and the link is in the stored copy of that page, or the claim came from a search and a reviewer must approve;
- every quote the agent gives exists in the candidate's own stored pages;
- at least one quote names the institution, allowing the opening words of a recorded name or the place name with another designator;
- no other verified institution owns that homepage.

A redirect from the candidate to another domain, on record in the browser,
moves the claim to the new domain. A dead site is rejected. A site that
belongs to another public body withdraws this institution's claim only.
Disagreement between the agent and the checks goes to review, never to
`rejected`. When a homepage is verified, the institution's other open claims
are superseded, and a superseded claim's candidate domain (the directory's
old address of a government that moved) is rejected with it unless another
institution still claims a page there.

### 6.4 Third-party platforms

A platform is fetchable but never trusted. A page on one becomes a source
only when a trusted page links to it and the page names the institution. The
link is recorded as evidence against the trusted page.

One exception, scoped to a path. When an institution's verified homepage is
itself on a platform, verifying it sets `trusted_path` on the homepage row to
the homepage's URL prefix. Pages under that prefix verify what they name for
that one institution, exactly as a trusted domain's pages do, so its sources
do not each need a reviewer. Pages elsewhere on the platform still need the
normal rule, and the platform itself stays untrusted.

### 6.5 The review queue

A review item is raised when the agent is unsure, a check fails in a way the
agent cannot fix, a duplicate match is uncertain, a body has no type or sits
at an unexpected level, a name misses its type's pattern, or an assignment
ends with gaps. Raising an item sets the entity to `needs_review`. A reviewer
approves, rejects or merges. Approval runs the same function the rules run,
so nothing bypasses it. Items that ask one shared question ("may a library
sit under a region") carry a `kind`: the queue lists them as one row and they
are decided together.

### 6.6 One door per state change

`graph/status_changes.py` holds one function per transition: a domain
trusted, a domain rejected, a homepage verified, an institution verified, an
institution rejected, two entities merged. Each sets the status, records who
did it, and tells the assignments module what to spawn. The rules, the
reviewer, the place loader and the country reload all call these functions
and nothing else changes a status.

---

## 7. Runs and assignments

### 7.1 Runs

A run is how a person controls work. It has a filter (country, administrative levels,
institution types, assignment types, or an explicit list of subjects) and a
mode.

- **Step mode.** Assignments the run spawns are created `held`. A person releases them from the console or the CLI, a few at a time. For development and testing.
- **Auto mode.** Spawned assignments are queued at once. For a whole province.

Pause stops the worker from starting the run's assignments; running ones
finish their session. The worker reads the run's status when it picks up a
job and, if the run is paused, puts the job back with a short delay. Paused
jobs stay `queued`: `held` means step mode and nothing else, so resume has
nothing to undo. Stop cancels everything held or queued. Every
assignment belongs to a run, and the console shows a run's progress and cost.

### 7.2 Assignment types

| Type | One per | Finds | Ends `complete` when |
| --- | --- | --- | --- |
| `find_homepage` | Institution without a verified homepage | The institution's official page, verifying its domain if new | The homepage is verified (or sent to a reviewer when no trusted page links to it) |
| `find_institutions` | Place | The public bodies under the place, with their candidate homepages | Every institution type expected at the place's level is saved or named in `types_not_found` |
| `find_sources` | Institution with a verified homepage | The institution's sources | Every source type listed for the institution's type is saved or named in `types_not_found` |

Other results, for every type: `out_of_budget` when the budget runs out;
`needs_review` when the agent and the checks disagree; `failed` when the job
crashed past its retries. For the two discovery types,
`complete_with_gaps` when the agent has crawled the available pages and types
are still missing, with a review item so a person can mark the gaps as "does
not exist here" or add leads. For `find_homepage`, `no_homepage` when the
searches found nothing, with a review item so a person can add the address.

`find_homepage` has three paths in one assignment. A candidate on an already
trusted domain: open it and quote it. A candidate on a new domain: verify the
domain with the checks in section 6.3. No candidate: search the web (five
searches), open the results, and save and verify the one that is the
institution's own. Two institutions claiming the same new domain are fine:
the first verifies it and the second finds it trusted.

### 7.3 Spawning

The backend creates follow-up work; the agent cannot. One function inserts
the assignment and queues or holds it according to the run's mode.

- A place loaded with a candidate homepage, or a government with none: `find_homepage` for its government.
- A homepage verified: `find_sources` for the institution; and `find_institutions` for the place when the institution is its government.
- `find_institutions` finished: `find_homepage` for every institution it saved that has no verified homepage and no decision pending.
- A domain rejected: `find_homepage` again for every institution that claimed it.
- A reviewer approving an institution or a domain: whatever the rule path would spawn.

An assignment is unique per subject and type while held, queued or running,
enforced by a partial unique index, so concurrent workers cannot queue
duplicates.

### 7.4 Budgets and sessions

Each assignment has a request budget and a token budget, set per type. A
session runs until the agent calls its finishing tool, the budget runs out,
the context passes half the model's window, or the assignment stalls. At half
full the agent writes a handoff note and a fresh session starts from the
database and the note. A discovery assignment stalls when it keeps making
requests without saving a finding: at thirty requests since the last finding,
counted across sessions, the next tool result tells the agent to finish unless
it has a concrete page left to open; at sixty the runner ends the assignment
`complete` with a summary the handoff model writes. One job runs at most
twenty sessions, then requeues itself. A job that fails five times finishes
the assignment as `failed`. Work spawned on finish runs for every result
except `failed`.

---

## 8. The agent

A worker on the `assignment` queue picks up an assignment and runs a Pydantic
AI agent. The briefing is the standing instructions for the type, the
country's levels, types and descriptions, the subject, the checklist of
types still to account for, the types already recorded under the place as
counts (with "from an official list" where the loader wrote them, so the agent
skips the directories that list a loaded type), the pages already visited, and
the last handoff note. Never the old transcript.

### 8.1 Tools

| Tool | Does |
| --- | --- |
| `navigate`, `snapshot`, `click`, `type_text`, `press_key`, `select_option`, `hover`, `scroll`, `wait_for`, `go_back`, `go_forward`, `tabs`, `get_text`, `screenshot` | Browse a real Chromium page on an allowed domain |
| `read_file(url, chunk)` | Download a PDF, spreadsheet or other file, store it, parse it to text on the parse queue, return one chunk |
| `search(query, domains)` | `find_homepage` only. Web search, results' sites join the session's allowlist, five per assignment |
| `save_institution` | Save a body with its type, parent, procurement_handled_by, quote and page. Returns likely duplicates |
| `save_homepage` | Save an institution's homepage with the link quote from a trusted page, or the page's own quote on a trusted domain |
| `save_source` | Save a source with its type, quote and page |
| `confirm_domain`, `reject_domain`, `domain_moved` | `find_homepage` only. End the domain decision; the checks run before any status changes |
| `status` | What this assignment has saved, the checklist, the files parsing |
| `request_review` | Raise a review item |
| `finish(summary, types_not_found)` | End a discovery assignment. Refused once if the checklist is short (a body saved under a place above the subject counts for its type); a second short close ends `complete_with_gaps` |

Tools are the findings functions registered directly with Pydantic AI through
one adapter. There is no wrapper layer. Each tool returns a typed result that
is rendered to text at the edge.

### 8.2 The fence and page capture

The session's allowlist is every trusted domain plus every platform, with
subdomains; a `find_homepage` session adds its candidate domain and the sites
its searches return. A route guard refuses every other request before the
browser moves and records a blocked attempt. Robots rules, three seconds
between loads on one host shared across sessions, and a current Chrome user
agent are applied in the same place. Images, fonts and media are not fetched.

Every page the agent lands on is captured without the agent doing anything:
after the page goes quiet, the HTML with its frames' links and the rendered
text are stored as a snapshot and a webpage row is written. The capture hook
receives plain values (URL, title, HTML, text, links), so the evidence module
never touches the browser. When an assignment finishes, snapshots no evidence
cites are pruned to their hash and metadata.

When the run has `record_video`, the browser context records a video of
every page, and at session end each file is stored through the storage port
and noted as a `video` event. Off for long runs, on for watching one
assignment. A daily purge job deletes videos after `video_keep_days` and
events after `events_keep_days`, both settings. Findings, usage and the
assignment's summary are never purged.

### 8.3 Files

PDFs and spreadsheets go through `read_file`. The type is detected from the
bytes, the original is stored, structured text (CSV, JSON, XML) is its own
text, and everything else is parsed by Docling on the `parse` queue in ranges
of ten pages with the memory guards from v1. A file is parsed only as far as
the agent reads it: the first range when it is fetched, and the next each time
`read_file` is asked for a chunk past the parsed pages, so a 400-page budget
book the agent opens to classify costs one range, not forty. Its text is
`partial` in between and the agent is told how far it goes. OCR stays on for
scanned minutes; table structure recognition is off, since the agent reads a
file to classify it and to quote a line, and neither needs a table's cells
reconstructed. A file already parsed by any assignment shares its text, as far
as it goes. `read_file` waits up to ninety seconds and then tells the agent to
check `status` later.

### 8.4 Model

The model and its reasoning effort are set per assignment type, carried over
from v1: GPT-6 Luna throughout, at `xhigh` for `find_institutions`, `find_sources` and `find_homepage`, and `medium` for handoff notes and summaries.

---

## 9. Derived relationships

There is no relationship table and no relationship tool. Links between bodies
are read from what is already stored:

- `institution.parent_institution_id`: the body it sits under. Set by the agent from the page that says so, or defaulted to the place's government.
- `institution.procurement_handled_by`: `self` or `parent`. When `parent`, the parent is the buyer for this body.
- `place.government_institution_id`: the government of a place; every other institution under that place is related to it.
- `institution_served_places`: the places a multi-place body serves, from scripts and reviewers.

The console renders these as a tree and the eval scores parent links.

---

## 10. Evaluation

The dataset is ten hand-labelled Ontario municipalities with every
institution, parent link, homepage and source each should yield, plus a list
of 25 governments scored on `find_homepage` alone, and three United States
subjects (a city, a county, a school district). Each file names its country,
and a run works one country's files against that country's seed. An eval run
works a quick set of five Ontario subjects and the list by default, chosen for
coverage over size so a run finishes in an hour or two, and every subject with
`--all`.
It is ported from v1 with its labelling rules, as YAML files: hand-labelled data edited over time is the one place a data file beats a table, and these are the only YAML files in the project.

An eval run is a run with `is_eval` set. It uses a separate database for the
graph it builds, built from the same settings object with a different
database URL, and it writes its results to `eval_runs` and `eval_scores` in
the main database so history survives a reset. The runner resets the eval
database, seeds the country with every assignment held, seeds each subject's
place, government, trusted domains and homepage, queues the subject's
`find_sources` and, for a place subject, its `find_institutions`, serves the
queues in its own process, then scores and prices.
Recall and precision per assignment type, the bucket of every miss, and the
cost per subject are stored and shown in the console.

---

## 11. Console

A Next.js app on the alloy base, without authentication. Pages, in build
order:

1. **Runs**: list and detail. Start a run with a filter and a mode, pause, stop, release held assignments, see progress and cost.
2. **Assignments**: list with filters, detail with the events in order (prompt, the model's words, tool calls and results), the videos when recorded, findings, spend and result.
3. **Institutions**: a table with search, filters by place, level, type and status; and a detail page with aliases, type, parent, homepage, sources by type, and every evidence quote linked to its snapshot.
4. **Review queue**: one table, searchable and filtered by status, reason, entity, country and size; an item is a row of its own, and the items of one kind share a row that expands to them and takes one decision for all; each item opens as its question in a sentence, its entity set beside the entities the question names (a duplicate beside its matches, each with a merge into it), why it was raised, its history from the raising assignment to the work started since the decision, and its evidence with snapshot and highlighted quote; approve, reject, merge, then on to the next open item.
5. **Countries**: country settings, administrative levels with their expected types, institution types, source types, and each country's use of a type with its expected sources, editable with validation.
6. **Evals**: runs over time with their scores and cost.

---

## 12. Tech stack and code layout

| Layer | Choice |
| --- | --- |
| Base | The alloy template, with auth, workspaces, mail, rate limits and the CRM removed |
| API | Python 3.14, FastAPI |
| Database | PostgreSQL, SQLAlchemy 2 async, Alembic, `pg_trgm` for duplicate matching |
| Jobs | Procrastinate on the same database. Queues: `assignment`, `parse`, `default` |
| Agent | Pydantic AI; model and reasoning effort set per assignment type (section 8.4) |
| Browser | Playwright Chromium, an owned layer of about 700 lines |
| Parsing | Docling on the `parse` worker image only |
| Storage | S3-compatible port: RustFS locally, Cloudflare R2 hosted |
| Search | Brave Search behind a port, off unless configured |
| Console | Next.js 16, shadcn/ui, TanStack Query, Form and Table, a generated API client |
| Tracing | Logfire when configured; cost always from the `usage` table |

### 12.1 Server layout

```
apps/server/src/public_atlas/
  main.py                 FastAPI app; calls build_resources once
  resources.py            build_resources(settings): database, store, searcher, model, jobs
  config.py               Settings: deployment values only, no product data
  db/                     base, session
  integrations/           storage, search, parse, browser, ai: one port each
  jobs/                   Procrastinate wrapper, worker, stalled sweep, purge
  modules/
    countries/            the five country tables, seeds, naming rules, the CountryRules object
    graph/                places, institutions, sources, domains, homepages, webpages,
                          aliases, identifiers, metrics, duplicate search, status_changes.py
    evidence/             snapshots, evidence, quote_checks.py, capture.py, parse jobs
    review/               review items, kinds, approve, reject, merge
    assignments/          runs, assignments, spawning, budgets, the run_assignment job
    agent/                briefing, tools (the findings), runner, prompts
    imports/              the shared list loader, and lists/<name>.py per official list
    evals/                dataset, harness, scorer, eval runs
  shared/                 errors, logs, pagination, text helpers
```

Every function that needs the database, the store or the model receives it as
an argument. Nothing reads settings at import time. Tests and the eval runner
call `build_resources` with their own settings.

### 12.2 Rules for the code

- One word per concept, from `glossary.md`. No synonyms (`assignment`, not `item` or `work`; `homepage`, not `official webpage`; `finish`, not `complete` or `close`).
- A status changes only in `status_changes.py`. An assignment changes status only in `assignments/lifecycle.py`.
- Tool results and refusals are typed values; prose is rendered at the tool edge.
- A module imports another only through its `service.py` and `models.py`. No imports after `TYPE_CHECKING` blocks to dodge cycles; a cycle means two things are one module.
- Product data (city names, prices, model names) lives in tables or data files, never in `Settings`.
