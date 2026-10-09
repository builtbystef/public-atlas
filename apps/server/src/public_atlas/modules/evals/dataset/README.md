# The eval dataset

The hand-labelled dataset of spec section 10: what a perfect run should yield
for ten Ontario municipalities, and the homepages and domains of 25 Ontario
municipal governments. Every prompt, tool or model change re-runs the agent
against it and scores recall and precision per assignment type. `eval run`
works the quick set by default, five subjects chosen for coverage over size
(`QUICK_SUBJECTS` in `__init__.py`) plus the places file; `--all` works every
file. These YAML files are the only YAML in the project: hand-labelled data
edited over time is the one place a data file beats a table.

Started in the `public-atlas-gold` repository, moved into v1 with its work item
types, and ported here in the words of `docs/glossary.md`. Run from
`apps/server`:

```sh
uv run public-atlas eval validate                 # schema and cross-reference checks against the Canada seed
uv run public-atlas eval evidence                 # fetch each evidence URL and check the quote is on the page
uv run public-atlas eval score                    # score the main database against the dataset
uv run public-atlas eval score --evals            # score the eval database a run left, and record it on that run
uv run public-atlas eval run --subject mcgarry    # reset and seed the eval database, work it, score it (model key, Chromium)
uv run public-atlas eval run --json scores.json   # the quick set and the places file, with the numbers written as JSON
uv run public-atlas eval run --all                # every subject and the places file
```

## Layout

| Path                                 | Holds                                                                                                                                                                                                                                                                   | Scores                                                                                                                                                                 |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `../../countries/seeds/`             | The country's rules (spec section 4.4): levels with their expected types, the types with their expected sources, the platforms, the naming rules, the anchor. The validator reads them through `rules_from_seed`, so the dataset and the agent never disagree on a type | Nothing                                                                                                                                                                |
| `places/ontario-municipalities.yaml` | 25 of the 444 municipalities on the official provincial list: the ten subject municipalities and fifteen whose listed website is dead, parked, hijacked, moved, wrong or missing, with tier, parent, homepage and the candidate domains of each government              | `find_homepage` for each government: its homepage and its domain decisions. The places themselves come from `imports/lists/ontario_places.py`, checked by its own test |
| `subjects/<slug>.yaml`               | One subject: its government, every in-scope institution with its parent, homepage and candidate domains, and its sources                                                                                                                                                | `find_institutions`, `find_homepage`, `find_sources`                                                                                                                   |

### Subjects

The quick set is marked; the rest run with `--all`.

| Slug                 | Subject                           | Level                                 | Quick | Why it is here                                                             |
| -------------------- | --------------------------------- | ------------------------------------- | ----- | -------------------------------------------------------------------------- |
| `toronto`            | City of Toronto                   | municipality (single-tier)            |       | Largest; many agencies, boards and corporations on their own domains       |
| `ottawa`             | City of Ottawa                    | municipality (single-tier)            |       | Officially bilingual: English and French names and pages                   |
| `greater-sudbury`    | City of Greater Sudbury           | municipality (single-tier)            | yes   | Bilingual names, mid-size, own utility                                     |
| `kingston`           | City of Kingston                  | municipality (single-tier, separated) |       | Separated city; Utilities Kingston                                         |
| `region-of-waterloo` | Regional Municipality of Waterloo | region (upper-tier)                   |       | Upper-tier with transit and police                                         |
| `county-of-simcoe`   | County of Simcoe                  | region (upper-tier)                   | yes   | A county as the `region` level                                             |
| `kitchener`          | City of Kitchener                 | municipality (lower-tier)             | yes   | Lower-tier inside Waterloo; shared bodies                                  |
| `oakville`           | Town of Oakville                  | municipality (lower-tier)             |       | Lower-tier inside Halton; own transit and hydro                            |
| `hawkesbury`         | Town of Hawkesbury                | municipality (lower-tier)             | yes   | French-majority; pages mostly in French                                    |
| `mcgarry`            | Township of McGarry               | municipality (single-tier)            | yes   | 579 people; site built by a municipal web vendor, tenders only on Biddingo |

The two ministry subjects of the first full run (Transportation, and Public and
Business Service Delivery and Procurement) were dropped on 2026-10-09: a
ministry's agencies are an official list's to load, not the agent's to find,
so until the provincial agency directory is loaded (`ontario_agencies`, a
Phase 7 item) they scored zero by design and only muddied the numbers. The
files are in the history before that date, and the harness still seeds an
institution subject should one return.

## Labelling rules

The dataset is only useful if two labellers would write the same file. When a
case is not covered here, decide, write the reason in `notes`, and add the rule
here.

### Scope

1. **Only the seed's types.** An institution is in scope when its type is in
   `countries/seeds/shared.py` and the country uses it. The level's
   `expected_institution_types` say where it is expected, as a floor, not a
   ceiling. Municipality: `municipal_government`, `transit_agency`,
   `police_service`, `fire_service`, `public_utility`, `library`, and the three
   below. Region: `regional_government`, `transit_agency`, `police_service`,
   `public_utility`, and the three below. Both levels: `conservation_authority`,
   `public_health_unit` and `municipal_corporation` (a corporation, authority or
   board the municipality owns or controls that runs a business of its own:
   community housing, real estate, parking, an airport, a venue, a zoo, economic
   development). Ministry (province): `ministry`, `agency`, `crown_corporation`,
   and the other province types. A known type at a level the seed does not list
   it under (a regional library, a county library) goes in `institutions` with
   `expected: review`. The agent should save it with that type and it should
   land in review, where a human confirms it or adds the level. It is not a
   precision trap. `validate` requires `expected: review` on such rows and
   rejects it on any other.
2. **Everything else plausible goes in `out_of_scope`** with a reason, so it
   doubles as a precision trap and as feedback on the seed. Examples: school
   boards and hospitals (province-level types, scored under Ontario, not the
   city), business improvement areas, council committees and tribunals
   (Committee of Adjustment, an advisory committee: they spend little and buy
   through the municipality), paramedic services and long-term care homes
   (departments of their municipality, which buys and budgets for them), a body
   of the upper tier met on a lower tier's site (Halton Region's paramedics on
   Oakville's), a not-for-profit the municipality only funds, and the OPP where
   it polices a town under contract.
3. **What gets its own institution row.** Either (a) a separately constituted
   body the place controls or owns (a board, commission or corporation), or (b)
   an internal division whose work matches a type and that presents itself
   under its own name (Toronto Fire Services, OC Transpo). A division that
   matches no type (Parks, Planning) is not an institution. A subsidiary gets
   its own row only when it runs its own procurement.
4. **Shared bodies.** A body owned or governed jointly by several municipalities
   (a utility with several municipal shareholders, a conservation authority)
   gets one row, in the subject where it is headquartered (or, when that
   municipality is not a subject, in the first subject that meets it). Which
   places it serves is `institution_served_places`, filled by scripts and
   reviewers, never by the agent (spec section 4.2), so membership is not
   labelled; say it in `notes`.
5. **Police boards fold into the police service.** A police service and the
   board that governs it are one `police_service` row; the board's names go in
   `names`, its meeting page is the service's `board_meeting` source, and its
   domain (e.g. `tpsb.ca`) is a `confirm` candidate for the service. The same
   holds for transit and library boards. An OPP detachment board is
   `out_of_scope` (it governs the OPP, which is provincial).
6. **Utilities behind a holding company.** The row goes to the operating
   utility: the brand the municipality links to and the public deals with
   (Oakville Hydro, Greater Sudbury Hydro, Enova Power, Hydro Ottawa). The
   holding company goes in `out_of_scope`, or in `names` when the utility's own
   pages use it. A holding company or subsidiary gets a row of its own only when
   it runs procurement separately from the operating utility.
7. **Delegated administrative authorities** (TSSA, ESA, OMVIC, Tarion and the
   rest) are `out_of_scope` for now: they are not provincial agencies and the
   seed has no type for them.
8. **Utility divisions.** A department that runs water, wastewater or waste gets
   a `public_utility` row only when it presents under its own name (Toronto
   Water). A service area of a department, with no name or site of its own, is
   `out_of_scope` (Region of Waterloo Water and Wastewater Services). Both
   follow from rule 3(b).

### Institutions

- `key`: kebab-case and unique in the file, the institution's English name
  slugified (`toronto-transit-commission`). The subject's own institution is its
  full official name (`city-of-kitchener`, `regional-municipality-of-waterloo`,
  `ministry-of-transportation`). Refer to another file's institution as
  `slug:key`, e.g. `region-of-waterloo:regional-municipality-of-waterloo`.
- `names`: every name and acronym the institution's own pages use, one entry
  each, with a BCP 47 `lang` (`en`, `fr`) and `is_acronym: true` for acronyms.
  "City of Greater Sudbury" and "Ville du Grand Sudbury" are two names of one
  institution.
- `homepage`: the institution's official starting page as it serves (scheme,
  `www` or not, trailing path for a section on a shared domain, such as
  `https://www.ontario.ca/page/ministry-transportation`).
- `homepage_alternates`: other URLs of the same homepage an agent may save, such
  as the French twin on a bilingual site.
- `homepage_host`:
  - `trusted_domain`: on a domain already in `trusted_at_start`, so the agent
    quotes the page itself. A municipal government's own domain is always this:
    the loader recorded its candidate homepage from the directory's link, and
    the harness verifies it, so it is scored from the places file (see "Place
    lists").
  - `own_domain`: a new domain. Add it to `candidate_domains` with
    `expected: confirm`; `find_homepage` verifies it (spec section 6.3).
  - `platform`: on a third-party platform (spec section 6.4).
  - `none`: no homepage of its own. `find_homepage` should end `no_homepage`.
- `evidence`: a verbatim quote from a **trusted** page (see `trusted_at_start`)
  that names the institution. Where the trusted page links to its own domain,
  use `kind: links_to` with `link_target`.
- `parent`: the body it sits under (spec section 9), scored from
  `parent_institution_id`. Record one only when a page says it: a city and its
  transit agency, a ministry and its agency, a division inside a government.
  `institution` is the parent's key, `label` the page's own words ("agency of",
  "a division of", "wholly owned by"), `evidence` the quote. Leave it out when
  no page says it; the agent's default (the place's government) is then not
  judged.

### Sources

- **The page, not the files.** A source is the landing page that lists the
  budgets, minutes or bids. It is not an individual PDF or tender. Tenders
  churn; landing pages don't.
- **Every source type of the institution's type is accounted for.** Either at
  least one `sources` entry, or an `absent_sources` entry with a note on what
  was searched (site search, sitemap, navigation). `validate` enforces this
  against the country's `expected_source_types` for the type.
- **The type's list is a floor.** A page of any source type is a real source
  even when the institution's type does not list it (a library's strategic
  plan). Record it when you meet it; the agent keeps such pages. The scorer
  reports these off-list sources in their own buckets and leaves them out of
  recall and precision, since the agent is not asked for them, so a file need
  not hunt for every one.
- `alternates`: other URLs for the same content that an agent may save and
  still be right, such as a redirect target, a French twin, or the page one
  click up that only links to it. A genuinely different page of the same type
  (the city's council page and its eSCRIBE portal) is a separate entry.
- `platform`: set whenever the URL is on one of the seed's platforms (`validate`
  enforces this), or on another shared platform (name it and say so in `notes`:
  that is a candidate for the platform list).
- `access: login` for pages behind sign-in. Record only the public entry page.
- **Bought or budgeted through someone else.** A division, board or ministry
  whose procurement, tenders, budget or capital plan run through another
  institution (Kingston Fire through the City, LINX through the County, a
  ministry through the government-wide Ontario Tenders Portal) gets an
  `absent_sources` entry with `covered_by: <that institution>`, and the source
  is recorded once, under that institution. The scorer accepts either the
  absence reported, or that institution's page saved for this one. A page that
  has a section of its own per body (Toronto's budget notes page, with one note
  per agency) is a real source for each body, not `covered_by`.
- **Government-wide Ontario pages** (the Ontario Tenders Portal, "Doing business
  with the Government of Ontario", INFO-GO) are sources of the ministry or
  agency that runs them. Other ministries record them through `covered_by`,
  with a cross-file ref.
- **One URL may be several source types** (a published plan that is both the
  `strategic_plan` and the org chart for `leadership`).
- **Asset management plans count as `capital_plan`.** When an institution has no
  capital plan or capital budget page of its own, its multi-year asset
  management plan or long-term capital forecast is the `capital_plan` source
  (Kingston, Oakville, Hawkesbury, Waterloo). Say so in `notes`.
- **A section of a general page counts** when no dedicated page exists (OC
  Transpo's procurement and five-year roadmap on its About us page). Say so in
  `notes`; a reviewer may prefer the absence.
- **Shared platform pages.** A platform page that lists many bodies' items (the
  bare eSCRIBE portal) may be an alternate under each body it serves.

### Candidate domains

Only the anchor's domains are trusted at the start: `ontario.ca`, and
`pas.gov.on.ca`, the provincial agency directory. Any other Ontario government
host (`infogo.gov.on.ca`, an old ministry domain) is a candidate like any other,
`expected: confirm` for the Government of Ontario or the ministry it serves. A
domain on the seed's platforms is never a candidate: it is fetchable already. A
trap domain that belongs to no institution is attached to the institution whose
page links to it.

List every new domain that discovery should surface for the subject, with the
expected outcome: `confirm` for the institution's own domain, `reject` for a
domain that is not the institution's, and `review` for a platform that is not
yet on the list. Include a few realistic traps (a BIA site, a campaign
microsite, a lookalike) with `reject`, and give the reason.

### Place lists

A `places/*.yaml` file lists children of one place as the official list gives
them. The loader makes the places from the list module (`ontario_places.py`),
so the agent is scored on each listed government's homepage and the file can be
a sample: Ontario's is 25 of 444, the subject municipalities and the hardest
domain cases. Each municipality carries its government's homepage the same way
an institution does:

- `homepage` and `homepage_host` (`own_domain`, `platform` or `none`) as above.
  There is no `trusted_domain` here: the government's domain is exactly what
  this file verifies.
- `listed_homepage`: the URL as the official list links it, only when the
  scoring rule would not match it to `homepage` (another registrable domain, or
  a path the served page is not under). The loader records what the list links
  as a candidate, so either URL counts as correct there.
- `candidate_domains`: omitted, it means the `homepage` domain alone with
  `expected: confirm`. Given, it is the whole list, as under "Candidate
  domains": `confirm` for the served domain, and one entry for the list's domain
  when that differs. A listed domain that no longer serves a page of its own
  (dead, parked, a default server page, or a bare redirect to another domain)
  is `reject`: the agent has nothing on it to quote, and the domain it redirects
  to is the one to confirm. Give the reason and the date checked.

### Subjects

- A place subject names itself in `place`; its `institution` is its government.
- An institution subject (a ministry; none shipped at present) names its place
  (`Ontario`) and its `government_homepage`, the homepage of the place's
  government: the harness seeds it verified so the ministry's page sits under a
  verified government. Only the ministry's `find_sources` is queued. Its
  agencies are an official list's to load (the provincial agency directory,
  `ontario_agencies` in the Phase 7 plan), not the agent's to find, so until
  that list is loaded such a file's agencies score as misses with that reason.

### Evidence quotes

- **Verbatim, from the raw page.** Fetch it (`curl -A "<Chrome UA>" URL`) and
  copy the text; never paraphrase and never quote a tool's summary of the page.
  `public-atlas eval evidence` re-checks every quote.
- Keep quotes short (one sentence or link text plus a few words around it).
- For a PDF, give the PDF URL and a `locator` ("page 3").
- Pages the script cannot read (bot walls such as ottawa.ca's, JS-only portals,
  PDFs) show as `missing`, `error` or `unchecked`. Confirm the quote in a real
  browser or with `pdftotext`, then set `manual_check` on the evidence ("browser
  2026-09-29"); the checker reports those as `manual`.
- A PDF locator gives the PDF page, and the printed page too when they differ
  ("pdf page 38 (printed 36)").
- Quote any YAML string that contains `: `.

### Provenance

`status: draft` until a human has checked the file end to end. Then set
`status: reviewed` and `reviewed_at`. Only reviewed files should gate the pilot.

## Scoring (the harness)

An eval run resets the eval database, seeds the country through the real seed
and loader with every assignment held, seeds each subject's place, government,
trusted domains and homepage, queues the subject's `find_sources` and, for a
place subject, its `find_institutions`, serves the queues in its own process,
then scores and prices. For a places file the seed is the loader's alone, so the run is
scored on each government's `find_homepage`. A homepage matches when it is on
the same registrable domain and its path starts with the dataset's path. The
rules below are code in `../scorer/`; `public-atlas eval score` applies them to
a database and `public-atlas eval run` seeds, works and scores the eval database
(`../harness.py`). One measure per assignment type:

| Measure             | Dataset                                                                                                                                      | Match rule                                                                                                                                                                                                   | Recall / precision over                                                                                                                                                                                  |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `find_institutions` | `institutions` minus the government; each `parent`                                                                                           | Homepage first, then any `names` entry; type must match. A row with `expected: review` matches only when saved as `needs_review`. A parent matches when `parent_institution_id` is the labelled parent's row | Institutions, grouped by type; saved institutions matching `out_of_scope` count as false positives. Parent links are the group `parent`, left out of the institution gate                                |
| `find_homepage`     | `homepage`, `homepage_alternates`, `candidate_domains` in subject files; `homepage`, `candidate_domains` (or its default) in `places/*.yaml` | Homepage matches; a domain's outcome equals `expected`                                                                                                                                                       | Institutions with a homepage (the group `homepage`) and candidate domains (the group `domain`)                                                                                                           |
| `find_sources`      | `sources`, `absent_sources`                                                                                                                  | Same institution and `source_type`, and URL equal to `url` or an `alternates` entry after normalizing scheme, `www`, trailing slash and query                                                                | Sources, grouped by source type; `finish` naming a type in `types_not_found` or in the summary counts as correct for an `absent_sources` entry, and so does saving the `covered_by` institution's source |

### Reading the report

Recall is hits over hits plus misses: how much of the dataset was found.
Precision is hits over hits plus false positives: how much of what the file
labels wrong was saved anyway. A false positive is an `out_of_scope` entry
saved as an institution, a source of an institution in the dataset that the
file does not list, or a decision that went the other way (a `reject` domain
confirmed, a wrong homepage, a wrong parent); the last kind is a miss too,
since the right decision is missing. A saved row the file says nothing about is
`unlabelled`, counted in neither, and listed under `--details` so the labeller
can promote it or add it to `out_of_scope`; a second row of an institution in
the dataset is flagged `duplicate`. A ministry's file labels its own slice of
the province, so its unlabelled rows are not reported. A source of a type the
country does not list for its institution's type is off-list: `extra, found` or
`extra, not found` when the file records it, `extra, not in dataset` when it
does not, counted in neither recall nor precision either way.

Each line of the report carries its buckets: `found (needs_review)` is a hit
whose row waits on a human, `candidate, not verified` a homepage claimed but
not yet verified, `not surfaced` a `confirm` or `review` candidate domain no
page linked to (a miss), `trap not met` a `reject` candidate no page linked to
(counted in neither: nothing was decided wrongly), `absence reported` an
`absent_sources` entry the finish named, `covered` one whose `covered_by` page
was saved for the institution, `wrong parent` a body saved under another parent
than the page says. `--json` writes the same numbers, with the per-entity lines,
for diffing two runs; the totals end with the gates of the pilot (spec section
1.2) the set can judge: homepages on the places file at 99%, institutions at
95%, and procurement, meeting and budget sources at 90%.

Each eval run is a row in `eval_runs` in the main database, with one
`eval_scores` row per subject and assignment type: recall, precision, and the
bucket of every miss and false positive. The eval database itself is reset by
the next run.
