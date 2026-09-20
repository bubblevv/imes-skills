# IMES Database Object Development

Use this workflow for new or changed business tables, views, indexes, constraints, functions, triggers, and supporting procedures. The outcome is a compatible database change with explicit assumptions, reviewable deployment artifacts, and evidence from the correct environment.

## Establish The Contract

1. Resolve the customer, database, and production/test classification. Verify `DB_NAME()`, `@@SERVERNAME`, database compatibility level, and the SQL Server version before using version-dependent syntax.
2. Record the business object, lifecycle, expected volume, retention, client/report consumers, integration keys, and whether the request includes only database objects or also a visible iMES client form. Read the supplied ER/cardinality evidence before counting tables: one requested form may require a header plus detail table, while two requested objects may require three or more physical tables.
3. Inspect the nearest related IMES objects. Confirm local conventions for object and column names, document numbers, header/detail relationships, account or tenant isolation, status fields, quantities and money precision, operator/time audit fields, soft deletion, defaults, indexes, triggers, and extended properties. Do not invent a universal IMES schema convention.
4. Identify ownership of identifiers and state transitions. Specify which layer generates keys, which fields are immutable, and which operation owns each status or aggregate update.

Classify the intended client route before DDL:

- `IOJCBDZD_BTYPE=1` is a generic single-table lookup form.
- `BTYPE=2/UForm2` is a category tree or directory on the left and one filtered detail dataset on the right. Its `LBTABLE/LBNAME` and `TABLE/MC` are separate metadata sets; it is not one document save unit.
- `IOBDZD` is the true business-bill contract: one visible bill name, one document number, `SYS_TbColumn.PO=1` header and `PO=2/3/...` line tabs, plus lifecycle scripts when required.

Choose by runtime behavior, not merely by physical table count. A form requiring a header with multiple lines, unified save/delete, audit/cancel-audit, references, or upstream/downstream documents must use `IOBDZD`. Stop and correct the model when ER evidence says header/detail but the proposed design contains only an isolated header or a `BTYPE=2` directory layout.

## Design Review

Document confirmed conventions separately from proposed choices. For every table, define:

- primary key and business uniqueness;
- foreign keys and delete/update behavior;
- data types, lengths, precision/scale, nullability, defaults, and valid ranges;
- header/detail cardinality and ordering where applicable;
- account/customer isolation fields when confirmed by the target schema;
- indexes derived from actual query and join patterns, including key order and included columns;
- concurrency and idempotency behavior for imports, PDA retries, audit/cancel-audit, and synchronization;
- expected result-set columns or client data contract.

Avoid generic audit columns, identity keys, cascade deletes, soft-delete flags, rowversion columns, and duplicate indexes unless the related IMES objects and business contract justify them.

## Migration Artifacts

Follow the repository's existing migration naming and storage convention. When none exists, provide three clearly named scripts: forward deployment, rollback, and verification.

The forward script should:

- fail closed when incompatible objects or columns already exist;
- use `SET XACT_ABORT ON` and an explicit transaction when every included DDL/DML operation is transaction-safe;
- schema-qualify objects and safely quote identifiers;
- create tables before dependent constraints, indexes, views, or procedures;
- preserve existing data during alterations and separate large backfills when one transaction would be unsafe;
- avoid swallowing errors or reporting success after partial failure.

The rollback script should reverse only objects introduced by the change, guard against data loss, and state when rollback requires a backup or is intentionally unavailable. Never write a rollback that silently drops populated business data.

The verification script must be read-only and check exact definitions, column metadata, constraints, indexes, dependencies, and representative query shapes. Include expected assertions rather than relying only on visual inspection.

## Test Matrix

Use a confirmed test environment or disposable clone for writes. Obtain explicit authorization before executing DDL or test DML. Test at least:

- valid minimal and full rows;
- nullability, length, range, uniqueness, and referential failures;
- header/detail insert, update, delete, and lifecycle transitions;
- duplicate submissions and retry/idempotency behavior where relevant;
- representative joins, filters, sorting, and estimated/actual plans for expected volume;
- transaction rollback on a deliberate mid-operation failure;
- forward migration preconditions, post-deploy verification, and rollback behavior;
- the exact result-set or field contract consumed by iMES clients, reports, PDA, or integrations.

Report the tested environment, scripts produced, writes actually executed, passed assertions, performance evidence, rollback result, and any client-form work that remains outside the database change.

## Client Form Boundary

Creating database tables does not create a visible iMES form. A complete client form may additionally require MFC C++ classes, `.rc` dialog resources, resource IDs, navigation/menu registration, `SYSWSPACE` metadata and role permissions, field metadata, validation, command routing, and packaging. Treat those as a separate client implementation scope and inspect the active client project's own rules before changing them.
