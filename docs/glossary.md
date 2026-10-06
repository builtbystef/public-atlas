# Glossary

The code uses one word per concept, from
[section 13 of the spec](product-and-tech-spec.md#13-glossary). That table is the source;
this page points at it so the rule is one link away from `CLAUDE.md` and the README.

Rules for naming, from [section 12.2](product-and-tech-spec.md#122-rules-for-the-code):

- One word per concept. No synonyms: `assignment`, not `item`, `task` or `work`; `homepage`, not `website` or `official webpage`; `finish`, not `complete`, `close` or `done`; `institution`, not `organization`, `entity` or `org`; `place`, not `jurisdiction` or `division`.
- `trusted` is a verified official domain; `allowed` is on the browser allowlist. They are not the same thing.
- `entered by` is `manual`, `script` or `agent`, never `verified_by` or `origin`.
- An `official list` is a published file the loader reads instead of the agent; a `register` is one with codes; an `entry` is one record a list module returns, in memory only.
- Table names are full words. The two type tables use the type's name as the primary key.
