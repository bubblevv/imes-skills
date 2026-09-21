# BDJB Audit Fast Path

Use this path whenever the user mentions BDJB, audit/cancel-audit, reporting backfill, completion/status not updating, or supplies a `BDJB_PJLX` query.

## 第一原则：审核与取消审核是互逆的一对

**审核 = 单据生效**，把本单影响写入下游；**取消审核 = 单据失效**，把审核写过的东西**原样撒回**。`cancel(audit(x)) == x`。

- 判断取消审核该写什么，看审核写了什么，**逐项反过来**：置 1 的置回 0、写的值还原、清的值恢复。
- 审核写的是**本单的值**，取消审核就撒回本单的值——不要“重算”、不要“取最新一张单的值”、不要“查还有没有别的单据再决定”。
- 只有在审核本身写的就是**派生聚合值**（按所有生效单据求和）时，取消审核才需要重算；那属于 `audit-state-matrix.md` 的数量矩阵范畴，不是默认写法。
- 互逆是否安全，看**审核的校验是否已排除多张单据同时生效**。有这条不变式就简单互逆；没有就先补校验，别用重算去兜歧义。
- 执行顺序是前提：`QZJC=0`（置 `SHBZ`）排在 `QZJC=1`（业务）之前，所以取消审核的业务规则运行时本单 `SHBZ` 已是 0，不会把自己算进“已审核单据”。

验证时断言**互逆性**而不是固定值：记录基线 → 审核 → 取消审核 → **断言回到基线** → 再审核 → 断言幂等。

详细规则见 `references/audit-state-matrix.md` 的「第一原则」。

## Mandatory First Round

Run these read-only steps before broad discovery:

1. Verify database identity:

```sql
SELECT DB_NAME() AS CurrentDatabase, @@SERVERNAME AS CurrentServer;
```

2. Execute the user's BDJB entry query in its narrow form. Preserve `SELECT *` initially if the schema is not confirmed; do not add guessed columns or ordering:

```sql
SELECT *
FROM dbo.BDJB
WHERE BDJB_PJLX = @BillType;
```

If the user supplied this query, run it directly. Otherwise generate the first-round script with:

```powershell
python scripts/generate_first_pass_sql.py --bill-type "<exact type>" --document-no "<exact document>" --expected-database "<confirmed database>"
```

3. From the returned rows, select active rules for the relevant command and record:

```text
BDJB_ID | command | order | purpose | target fields | predicates
```

4. Query the exact failing document in the tables named by those rules. Do not search unrelated modules yet.

The first status update to the user should name the target environment, exact entry query, rules that should perform the backfill, and predicates being tested.

When several returned scripts update related fields, export only those rows and run `scripts/extract_bdjb_rules.py`. Use its matrix to accelerate comparison, then validate every reported target, predicate, and assignment mode against the live rule text and exact document.

```powershell
python scripts/extract_bdjb_rules.py --input <rules.json> --sql-field <confirmed SQL column>
```

Use `--input - --input-format json` when passing a normalized JSON export through standard input.

## Predicate Matrix

Turn each candidate rule into a matrix before forming a root-cause claim:

| Rule | Target | Predicate | Actual value | Match |
|---|---|---|---|---|
| audit rule | header quantity | approval status | confirmed value | yes/no |
| audit rule | header quantity | final-process marker | confirmed value | yes/no |
| audit rule | completion flag | next-process condition | confirmed value | yes/no |

Use a focused `SELECT` or `CASE` expression to test predicates. Do not infer that a rule ran merely because an earlier/later rule produced data.

## Trace The First Failure

When a predicate fails:

1. Confirm the field value in the exact detail row.
2. Find the insert/update statement that populated that field.
3. Confirm its source field and source value.
4. Stop if the business meaning is still ambiguous; ask whether the source marker or a derived predicate is authoritative.

Do not jump directly from a null marker to a synchronization-procedure defect. First prove that the null marker is the predicate preventing the BDJB rule from matching.

## Questions That Must Not Be Guessed

Ask or prove these before changing SQL:

- Which database column backs the UI label?
- Does “完成/状态” mean detail flag, batch flag, work-order quantity, order status, or sync status?
- Does a marker mean key process, final process, or another customer-specific classification?
- Is the correct quantity the current document's quantity or the sum of all approved documents?
- Can one process be reported in multiple documents?
- On cancel-audit, should the value become zero or be recalculated from remaining approved documents?

## Quantity And State Gate

When any candidate rule writes a quantity, completion flag, generation state, or work-order state, read and complete `audit-state-matrix.md` before proposing a fix.

For every audit target field, locate all active cancel-audit or reverse-event rules that write the same field. Compare:

- grouping key and target grain;
- effective approval filters;
- terminal-process filters;
- current-document overwrite, incremental delta, aggregate recalculation, or constant reset;
- behavior for split documents, repeat audit, partial cancel, final cancel, and re-audit.

Direct overwrite in audit plus unconditional zero/null in cancel-audit is a mandatory cumulative-semantics warning, not a complete root-cause conclusion. Prove whether multiple effective documents can share the target and ask when the business contract remains ambiguous.

## Broadening Rules

Broaden to `sys.sql_modules`, schema-wide searches, generation procedures, or synchronization sources only when a specific question requires it, such as:

- which confirmed object writes the failed predicate field;
- which procedure calls the confirmed audit dispatcher;
- which source field is copied into the confirmed target column.

State that question before running the broader search. Do not scan first and invent a direction from incidental matches.

## Fix And Historical Repair

Before editing BDJB:

1. Check both audit and cancel-audit rows.
2. Check all other active rows using the same obsolete predicate.
3. Complete the applicable audit/cancel state transitions, including repeat and partial cancel.
4. Separate future-rule correction from historical-data repair.
5. Preview exact affected counts for detail rows, batches, and work orders.
6. Create backup/rollback artifacts before the repair script.

Verification must include the original document plus an aggregate case. A fix that works only when one final report exists is incomplete if split reporting is present.

## Stop Conditions

Stop and ask the user instead of guessing when:

- the environment is unresolved;
- two fields plausibly represent the requested status;
- multiple terminal-process definitions exist and data does not identify the authoritative one;
- changing overwrite to aggregation would alter business semantics not confirmed by data or user intent;
- a proposed repair scope cannot be bounded with exact predicates and counts.
