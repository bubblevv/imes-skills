# Project Knowledge Layer

Keep reusable investigation mechanics in this personal skill and customer-specific facts in the active project. This separation improves speed without leaking one customer's schema or business semantics into another environment.

## Resolution Order

At the start of an investigation, resolve facts in this order:

1. The user's explicit customer, environment, SQL entry point, and document number.
2. The active project's `AGENTS.md`, including database-tool routing and write permissions.
3. The active project's human-readable handbook when `docs/imes/README.md` and `docs/imes/开发与排障手册.md` exist.
4. A project-local, verified IMES object map when one exists.
5. Read-only metadata and exact data from the confirmed target database.
6. One focused user question when the remaining ambiguity changes the route or fix.

The project handbook is the place for people to review terminology, workflow, scope boundaries, and current project conventions. It does not replace `AGENTS.md`, runtime source evidence, or target-database evidence.

Do not scan database configuration when project instructions already map the named environment to a fixed tool.

## Verified Project Map

A project map may record these customer-specific facts:

| Fact | Required evidence |
|---|---|
| Customer and environment | explicit project rule or user statement |
| Database tool and database | project routing plus identity query |
| Document type | exact `BDJB_PJLX` or dispatcher definition |
| Main/detail tables and keys | confirmed schema and rule SQL |
| Audit/cancel commands and order | active BDJB rows |
| UI label to returned column | form/query/procedure evidence |
| Returned column to stored field | confirmed SQL lineage |
| Effective approval status | target data and business definition |
| Terminal-process predicate | target route data and user/business confirmation |
| Aggregate grain and formula | audit/cancel rules plus split-document evidence |
| Last verification source | object definition, query, or dated project change |

Mark uncertain entries as unknown. Never promote a likely mapping to a verified mapping.

## Conflict Handling

- User-supplied exact evidence outranks a stale project map.
- Runtime identity and object definitions outrank folder names.
- A customer-specific marker, status value, or table relation must not be copied into this personal skill as a universal IMES rule.
- When a verified project fact changes, update the project knowledge source and record the evidence; add only the reusable diagnostic pattern to this skill.
