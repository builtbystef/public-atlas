# Eval run 1: review and fix plan

Written 2026-10-09 after reading the scores of the first full eval run (`docs/eval-results.md`,
eval run `01a1141b-4d75-7043-8e7a-19263a57d60e`), the rows in `eval_scores`, the graph the run
left in the eval database, and the code paths behind each kind of loss.

## The task

Three questions were asked of the run:

1. What can be done to raise precision and recall in the evals?
2. The discovery agent saves every body it meets, including very small ones with no buying
   power, such as The 519 community centre in Toronto. What can be done about that?
3. What else about the system would you change, looking at the eval?

## The numbers

| Measure                                        | Recall         | Precision | Gate      |
| ---------------------------------------------- | -------------- | --------- | --------- |
| `find_institutions` on the subject files       | 81% (120/149)  | 66%       | 95%: fail |
| `find_homepage`, homepages on the places file  | 96% (23/24)    | 100%      | 99%: fail |
| `find_sources`, the four gated types           | 59% (150/255)  | 81%       | 90%: fail |

Cost $6.78 for 222 assignments. Toronto's discovery ran out of its 150 requests; Waterloo's
stopped at 46 with three bodies unfound.

## Findings

Four causes account for most of the loss.

### 1. The scorer counts bodies saved under the right place as false positives

24 of the 61 institution false positives are rows the agent saved under a place other than
the subject, which is what the prompt tells it to do:

- 16 under Ontario: nine school boards, two universities, a college, Hydro One (counted twice,
  once for Kingston and once for McGarry), the OPP and the Ontario Clean Water Agency.
- 5 under a region: Grand River Transit, Waterloo Regional Police and Region of Waterloo
  Public Health under Waterloo region (the Kitchener file labels them as that file's bodies),
  Halton Regional Police under Halton, the old Timiskaming Health Unit under Timiskaming.
- 3 governments of their own places: Barrie, Orillia and Frontenac, loaded from the places
  list, not saved by the agent at all.

The trap check in `evals/scorer/subjects.py` (`_score_traps`) matches an `out_of_scope` name
against every row in the graph whatever place it sits under. Precision without these is about
76%, with no change to the agent.

### 2. The trusted-link check is stricter than the data

14 domains the dataset expects confirmed went to review with "no trusted page links to it",
and 17 homepages were claimed but never verified. Two shapes:

- Oakville's site links to a deep page on `oakvillehydro.com`. That claim carries the link.
  The agent then confirmed the root page, which has no link of its own, so
  `_linking_failures` in `agent/findings/domains.py` failed and the domain went to a human.
- Kingston Police, the Kingston library, Ottawa Police and Ottawa Community Housing were
  saved by discovery without `homepage_url`, so no link was recorded. The homepage search
  then used the web rather than the city's boards page, and a search result cannot be
  verified by code.

A homepage in review never spawns `find_sources`, so each of these bodies also lost every
source: the 38 "no summary" source misses and a good part of the 91 "not found" ones.

### 3. The agent is never told the labelling rules for small bodies

The dataset README excludes single-facility boards of management, non-profits the city only
funds, holding companies, subsidiaries that buy through a parent, and boards that invest or
grant city money. The prompt names none of these, and pushes the other way: "never drop a body
for want of a type", the level's types are "a floor, not a ceiling", and a finish that leaves
a type out is refused. So the agent read Toronto's own agencies page, saw The 519 and
seventeen other arenas and community centres listed as city agencies, and saved them all,
spending a third of Toronto's budget on them. The genuine false positives after the scorer
fix:

| Kind                                                   | Count |
| ------------------------------------------------------ | ----- |
| Single-facility boards (arenas, community centres, one street) | 19 |
| Non-profits the city funds but does not control        | 5     |
| Holding companies and subsidiaries covered by a parent | 4     |
| Investment boards, granting funds, a heritage agency   | 4     |
| Partnerships the city does not control, contractors    | 5     |

McGarry (579 people) scored 40% precision for the same reason seen from the other side: the
checklist pushed the agent to fill the transit, utility and health slots with Hydro One, a
provincial contractor and the old health unit.

### 4. Sources: the parent's page saved as the child's, and the wrong page on a platform

The agent saved Toronto's city budget page as the budget of the TTC, Public Health and Fire,
and Ottawa's procurement page as OC Transpo's. The dataset wants the type named as absent with
the parent covering it. Those count as both a miss and a false positive. On platforms it saved
one eScribe meeting, one tender, a MERX search URL and the Biddingo root instead of the
standing page. The goal text already says "not one agenda"; it says nothing about search pages
or platform roots.

### Smaller findings

- **Budget use is uneven.** Toronto hit 150 requests; Waterloo finished at 46 with three
  misses. There is no rule that ends an assignment that has stopped finding things.
- **Bot-blocked sites.** `phsd.ca`, `eohu.ca`, `utilitieskingston.com` and `cecilcentre.ca`
  were blocked by Cloudflare or `robots.txt`, so their domains could not be verified.
- **Places file.** 25 of the 28 domain misses are the directory's old domains left undecided
  after the agent found the new site; nothing rejects the old candidate.
- **Recall misses in discovery** (Kingston Hydro, two airports, two theatres, a regional
  library, a housing corporation) are all bodies the municipality's consolidated financial
  statements list as owned entities. The agent did not use that page as a source.
- **Province-wide discovery** spent its budget on universities, colleges and school boards.
  Already decided: those come from an official list, not the agent.

## Decisions made

1. **What counts as an institution.** A body gets a row only when it buys on its own account:
   its own procurement page, its own budget, or its own board that approves spending. One
   facility, one street or one program is not an institution; neither is a body the
   municipality funds but does not control, a holding company above a utility, a subsidiary
   that buys through its parent, or a board that invests or grants city money. The city's
   consolidated financial statements are the control test: a body not consolidated there is
   not the city's. This matches the dataset README, so no relabelling.
2. **Bot-blocked sites stay in review.** A trusted link alone does not verify a site the
   browser cannot open.
3. **No section split for now.** Big directories (Toronto's agencies and corporations page)
   are better handled by a loader, like the province's agencies. The design is kept below in
   case Toronto still overruns after the rules land.
4. **Discovery cap from 150 to 250 requests**, with a stall rule so a bigger cap is not spent
   on nothing.
5. **Prompt, not code, for bad source URLs.** URL patterns per platform are brittle and
   open-ended. The goal text names the cases instead.
6. **The "already recorded" line in the briefing names types with counts, never bodies.** A
   list of names does not scale to Toronto; a line of types does. Say "from an official
   list", not the list's name, which the agent cannot know.
7. **No eval rerun yet.**

## What to do

In the order to do it.

- [x] **Scorer.** In `_score_traps`, match a trap only against rows whose `place_id` is the
      subject's place. A trap row under another place is ignored, not counted.
- [x] **Domain check.** In `_trusted_link`, accept a `links_to` evidence row from a trusted
      page to any URL on the candidate domain for the same institution, not only one that
      targets the exact homepage URL. The redirect rule stays for links to other domains.
- [x] **Discovery goal and type descriptions** (`assignments/descriptors.py`,
      `countries/seeds/shared.py`): the buying-power test and the exclusions from decision 1;
      a line that most small municipalities have only a fire service and a library and that
      naming the rest in `types_not_found` is the right answer; the consolidated financial
      statements as the page that lists every body the municipality owns; pass `homepage_url`
      as the href from the snapshot's link list whenever the page links to the body.
- [x] **Briefing** (`agent/briefing.py`): next to "Types still to account for", a line
      "Already recorded under this place: municipal_corporation (41, from an official list),
      library (1), ..." and the instruction that a type with a count from an official list is
      done, so skip the directory pages that list that type.
- [x] **Sources goal**: one line that a platform root, a single meeting or tender, and a
      search results page are not sources, and that the parent's page is never saved as the
      child's: name the type in `types_not_found` and say the parent covers it.
- [x] **Budget**: `find_institutions` to 250 requests in `descriptors.py`.
- [x] **Stall rule** in `agent/runner.py`: count requests since the last saved finding. At 30,
      the next tool result carries "30 moves without a finding; finish with a summary unless
      you have a concrete page left to open." At 60 the backend ends the assignment as
      `complete` with the handoff note as the summary. Tune the numbers on the next run.
      Landed with the count on the assignment row (`requests_since_finding`), so it runs
      across sessions; the numbers are `STALL_WARNING_REQUESTS` and `STALL_END_REQUESTS` in
      `agent/context.py`; the notice is said once per session; discovery types only.
- [x] **Places file**: when a government's homepage is verified on another domain, reject the
      directory's old candidate domain in the same status change. Landed in `verify_homepage`:
      a superseded claim's candidate official domain is rejected unless another institution
      still has an open claim on it.
- [x] **Todo items** in `docs/todo.md`: a loader for Toronto's agencies and corporations page
      (same shape as `ontario_agencies`); the section-split design below, held until a rerun
      shows Toronto still overruns.
- [ ] **Rerun the quick set** when the above lands, then Toronto alone, and write the numbers
      to `docs/eval-results.md`. Everything above landed on 2026-10-09; the rerun is next. The
      type descriptions changed in the seed, which only a fresh seed reads (the eval database
      is reset each run; the live database keeps its edited rows), so edit them on the
      countries page or re-seed a reset live database before the pilot runs.

Expected effect: institution precision near 76% from the scorer fix alone, most of the way to
95% with the prompt changes; source recall well above 59% once the 14 domains verify and
spawn their source searches.

## Held design: splitting a discovery assignment by section

For a subject whose own site lists more bodies than one assignment can work.

- A nullable scope on the assignment row: a start URL and a short label. A scoped discovery
  works that page and what it links to, saving under the same place. Uniqueness becomes
  subject, type and scope.
- A tool, `defer_section(url, stated_count)`, the agent calls when it meets a list too long
  to finish. The backend creates the scoped assignment; the agent never creates work itself.
- The scoped session's briefing names its page and label and the types already recorded
  under the place. Duplicate matching across the place resolves overlaps as it does now.
- The checklist stays on the unscoped parent; scoped children save what their page lists and
  finish.

Cost: a migration, a tool, a briefing change, a spawn rule. Not built because a loader for a
known directory is cheaper and complete, and the scope rules alone may bring Toronto under the
cap.
