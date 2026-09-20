# Audit Quantity And State Matrix

Use this matrix whenever an audit or cancel-audit rule writes a quantity, completion flag, generated status, work-order status, or another derived header value.

## Define The Authoritative Set

Before judging the update formula, record:

- target grain: report detail, production batch, work order, route, or another header;
- source table and grouping key;
- effective approval condition, including voided or deleted rows;
- confirmed terminal-process or route predicate;
- quantity field and unit conversion;
- duplicate, rework, reject, and null handling;
- whether the contract is current-document, delta, or all-effective-document recalculation.

Do not accept the current audit document as the source set merely because the rule receives its document number.

## Mandatory Transitions

Build expected values for every applicable transition before changing the rule:

| Transition | Effective source set after event | Quantity expectation | Status expectation | Invariant |
|---|---|---|---|---|
| First audit | first effective report | authoritative aggregate | derived from aggregate | baseline |
| Split report audit | all effective reports for the same target | cumulative aggregate | remains consistent | order independence |
| Repeat audit | unchanged effective set | unchanged | unchanged | idempotency |
| Partial cancel-audit | remaining effective reports | remaining aggregate | must not clear prematurely | audit/cancel symmetry |
| Final cancel-audit | empty effective set | zero or confirmed empty value | reset by contract | no stale state |
| Re-audit after cancel | restored effective set | recalculated aggregate | recalculated | no double counting |
| Unrelated process event | unchanged terminal source set | unchanged | unchanged | route isolation |

If any row is not applicable, record the business reason instead of silently skipping it.

## Formula Review

Prefer recalculation from all effective source rows when the value is derived state:

```sql
WITH EffectiveSource AS
(
    SELECT
        <target_key>,
        SUM(<effective_quantity>) AS ExpectedQuantity
    FROM <confirmed_source_table>
    WHERE <effective_status_predicate>
      AND <terminal_process_predicate>
    GROUP BY <target_key>
)
SELECT
    H.<target_key>,
    H.<stored_quantity> AS ActualQuantity,
    ISNULL(E.ExpectedQuantity, 0) AS ExpectedQuantity
FROM <confirmed_target_table> AS H
LEFT JOIN EffectiveSource AS E
    ON E.<target_key> = H.<target_key>
WHERE ISNULL(H.<stored_quantity>, 0) <> ISNULL(E.ExpectedQuantity, 0);
```

Adapt the placeholders only after confirming target schema and status meanings. Preserve the deployment's existing JOIN style in final scripts.

## Mandatory Warnings

Treat these pairs as a signal to stop and test the complete matrix:

- audit directly overwrites a header with the current document quantity;
- cancel-audit assigns zero or null unconditionally;
- audit increments a stored value without proving repeat-audit idempotency;
- audit and cancel-audit use different effective-status or terminal-process predicates;
- batch and work-order quantities aggregate at different grains;
- a completion flag is updated separately from the quantity that should drive it.

Static SQL analysis identifies candidates only. Prove the source rows, expected totals, matched row counts, and transition results against the exact target database.
