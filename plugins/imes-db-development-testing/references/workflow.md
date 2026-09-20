# Workflow

## Evidence-First Routing

Before calling a database tool, extract these items from the user's message without generalizing them:

- exact customer/environment;
- exact table, procedure, `BDJB_PJLX`, or SQL query supplied by the user;
- exact document number;
- symptom and expected field/status;
- requested action: diagnose, script, deploy, or repair.

Record them as a compact case card. The first investigation update should state the resolved target, the exact entry point being executed, the example document, and the one predicate or rule group currently being tested. Do not wait for a broad investigation to finish before telling the user what route is being followed.

The user's narrowest confirmed entry point is the first investigation route. Examples:

- `SELECT * FROM BDJB WHERE BDJB_PJLX='<用户给出的单据类型>'` means inspect those rows first;
- a procedure name means pull that definition and its exact input document first;
- a document number means trace that document, not a representative document;
- a stated source such as “目标单据审核脚本” outranks a generic search for every object touching the table.

For an existing dynamic-bill reference/filter-only request, the exact `IOYYGX` bill/operation row is the narrowest entry point. Read `references/reference-fast-path.md`, resolve only the source columns used by `IOYYGX_GLTJ`, and do not repeat the full dynamic-bill creation contract unless the route, metadata, lifecycle, or save behavior changes.

Do not begin with global schema enumeration, repository-wide guesses, another customer's logic, or broad `sys.sql_modules LIKE` searches when a narrower route exists.

When a `BDJB_PJLX` is known and no exact query has been supplied, use `scripts/generate_first_pass_sql.py` to generate the identity check and narrow BDJB query. When the user supplied the query, run it directly.

After exporting the relevant BDJB rows to JSON, CSV, or TSV, use `scripts/extract_bdjb_rules.py` when static extraction will reduce manual comparison. Its assignment modes and predicate fields are review candidates, not proof that a rule executed.

## Uncertainty Gate

Ask one focused question before proceeding when an unresolved choice would materially change the route or fix. Typical gates:

- more than one environment matches;
- a UI label could map to multiple columns;
- a marker might mean “关键工艺” or “末道工序”;
- a quantity might be current-document, cumulative approved quantity, or planned quantity;
- the user requested a write but production permissions or scope are unclear.

Do not ask when a safe read-only query can resolve the ambiguity. Run that query, show the conflicting evidence, then ask only if multiple meanings remain.

## Hypothesis Discipline

Keep one active hypothesis and one falsifying query. Use this loop:

1. State the observed fact.
2. State the narrow hypothesis it supports.
3. Run the smallest query that can disprove it.
4. If disproved, discard it explicitly before moving to the next hypothesis.
5. If proved, follow only the failing predicate or join one hop upstream.

After three confirmed hops without a root cause, summarize the evidence and ask for missing business context instead of widening into unbounded discovery.

## Determine The Target

Build a target record before using a database tool:

- database name;
- customer account or environment label, if known;
- production/test classification, or `unknown` when unconfirmed;
- server/tool environment selected from existing configuration;
- object name and exact error;
- example document number or input parameters;
- whether the requested action is read-only, deploy, or data repair.

Resolve it from explicit user input first, then the current SQL `USE` statement or qualified object names, repository rules/configuration, and configured database-tool environments. Treat file and folder names as supporting evidence, not authority when they conflict with SQL or the user's instruction.

Do not connect when the database is unknown, when multiple configured environments plausibly match, or when the configured default database conflicts with the confirmed target. Ask the user to disambiguate.

Read the active project's `AGENTS.md` before scanning connection configuration. Follow fixed project database-tool routing directly, then verify runtime identity. Use `project-knowledge-layer.md` to keep customer-specific object and status facts outside the reusable personal skill.

If production/test classification is unknown, use production-grade safety controls but keep the classification recorded as `unknown`.

## Connect Safely

Use the project's existing MCP, SQL client, or connection configuration. Resolve credentials only through its secure secret mechanism or process environment. Never copy credential values into SQL files, shell history, logs, or replies.

Use the least-privilege connection that can perform the current step. Do not use a deployment-capable account for initial read-only investigation when a read-only option exists.

Before investigation, verify the selected target with a read-only identity query such as:

```sql
SELECT DB_NAME() AS CurrentDatabase, @@SERVERNAME AS CurrentServer;
```

Stop if `CurrentDatabase` is not the confirmed database. When using `sqlcmd`, pass the discovered database through `-d`; do not rely on a connection's default database.

## Investigate

Gather concrete evidence before editing:

- procedure text: `sp_helptext` or `sys.sql_modules` joined to `sys.objects`;
- table columns: `sys.columns` or `INFORMATION_SCHEMA.COLUMNS`;
- dependencies: `sys.sql_expression_dependencies`, targeted module searches, and confirmed call chains;
- BDJB scripts: inspect active rows, ordering, conditions, command text, and returned result sets;
- business documents: query by the exact confirmed document, route, material, batch, or production number.

Do not guess columns. If a query reports an invalid column, inspect the target schema and retry with confirmed names.

For BDJB/audit/backfill issues, follow `bdjb-audit-fast-path.md`. The output of the first round must identify:

- which active rule should update the missing field;
- its execution order;
- every restrictive predicate;
- the exact predicate that matched zero rows or produced the wrong aggregate;
- whether audit and cancel-audit remain symmetric.

If a rule writes quantity or derived status, complete `audit-state-matrix.md`. A first-document success is not sufficient evidence: verify split audit, repeat audit, partial cancel, final cancel, and re-audit whenever the business flow permits them.

Do not trace generation/synchronization sources until the audit rule has been evaluated against the exact failing document. Source tracing begins at the first proven missing or incorrect predicate value.

## Change

Follow the repository's existing diagnostic-file convention. If the repository uses `diagnostics/`, prefer:

```text
diagnostics/<database>_<object>_<yyyymmdd>/<object>.after.sql
```

Derive `<database>` from the confirmed runtime target. Sanitize each generated path component and verify the resolved output path remains inside the repository's approved diagnostic directory.

A deploy script must be self-contained, select that same database, preserve the object's existing session options, and include a focused final query when updating configuration or BDJB rows. Treat all external values as untrusted:

- bind document numbers, codes, quantities, and other values as SQL parameters;
- validate identifiers against discovered metadata and quote them with `QUOTENAME` when dynamic SQL is unavoidable;
- never concatenate raw user text into SQL identifiers, predicates, connection arguments, or file paths.

Make the smallest compatible change. Preserve procedure parameters, output columns, business errors, transaction ownership, and the number and shape of result sets unless the user explicitly requests an interface change.

Before any destructive or data-repair execution:

1. Run the equivalent `SELECT` preview with the exact predicate.
2. Record and assert the expected affected-row count in the script.
3. Prepare rollback, restore, or compensating SQL and confirm required backups exist.
4. Reconfirm the database identity and obtain explicit authorization immediately before the write.

## Verify

Before claiming success:

1. Parse or compile the script without applying business data changes.
2. Deploy only to the confirmed database and only with user authorization.
3. Confirm object `modify_date`, deployed module text, or the exact affected configuration row.
4. Run a focused query proving the corrected condition or calculation.
5. Re-run the original failing command when safe.
6. Test write paths in this order: disposable clone, confirmed test environment, then live production only when explicitly authorized and no safer environment can reproduce the problem.

An outer transaction is not a sandbox: an unknown procedure may commit or roll it back. Before using rollback containment, inspect the full transaction contract and prove the procedure does not take ownership of the caller's transaction. For production, also require an expected-row assertion and a tested cleanup/restore plan.

Only after those preconditions are satisfied, use a clean dedicated session:

```sql
IF @@TRANCOUNT <> 0
    THROW 50000, N'Rollback verification requires a clean session.', 1;

BEGIN TRANSACTION;
BEGIN TRY
    EXEC dbo.<confirmed_save_procedure>;

    IF @@TRANCOUNT <> 1
        THROW 50001, N'The procedure changed transaction ownership; rollback containment is not reliable.', 1;

    ROLLBACK TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 AND @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT @@TRANCOUNT AS TranCountAfterRollback;
```

This wrapper detects transaction-contract violations but cannot undo data already committed by a misbehaving procedure. Never use it as the sole safety control for an unknown production write path. Use the SQL client's fail-on-error option, such as `sqlcmd -b`, so a thrown error produces a failed command.
