# Audit Quantity And State Matrix

Use this matrix whenever an audit or cancel-audit rule writes a quantity, completion flag, generated status, work-order status, or another derived header value.

## 第一原则：审核与取消审核是互逆的一对

**审核 = 单据生效**：把这张单据的影响写入下游。
**取消审核 = 单据失效**：把这张单据审核时写过的东西**原样撤回**。

取消审核不是"重算当前状态"，也不是"根据现状推断应该是什么"。它是**这一张单据的逆操作**：
`cancel(audit(x)) == x`。判断取消审核写什么，看审核写了什么，逐项反过来即可。

- 审核置了 A、写了 B、清了 C → 取消审核必须还原 A、还原 B、恢复 C。
- 审核写的是**本单的值**（如使用人取本单的借用人），取消审核就撤回本单的值，不要"取最新一张单的值"。
- 审核把某标志置 1 → 取消审核置回 0；审核插入行 → 取消审核删除行；审核累加 → 取消审核减回。

只有在**审核本身写的就是派生聚合值**（例如按所有生效单据求和）时，取消审核才需要重算——
因为此时"撤销本单影响"等价于"用剩余单据重新求和"。这种情况属于本文件后半部分的
数量/状态矩阵范畴，不是默认写法。

**不要自创"重算"逻辑**：若审核写的是单值覆盖，取消审核却去查"还有没有别的单据"再决定，
就破坏了互逆性——一旦不变式被历史数据或人工改库破坏，结果会与审核前不一致。

### 判定互逆是否安全：先找审核的不变式

审核的校验往往已经排除了"多张单据同时生效"的场景。找到那条校验，就能确认简单互逆是安全的：

```sql
-- 例：借用审核校验「同一资产不能重复借出」
IF EXISTS (SELECT 1 FROM 明细 b JOIN 头 h ON ... AND h.SHBZ=1
           WHERE b.资产=b.当前单资产 AND b.未归还=0 AND b.单号<>'@SJDH')
    RAISERROR(N'资产存在未归还借用记录，不能重复借出。',16,1);
```

该不变式成立 => 任一资产最多一条活跃单据 => 取消审核时不存在"还要保留别的单据"的情况 =>
**简单互逆即可**。若审核没有这类校验，先补校验，再谈互逆；不要用重算去兜住本可由校验避免的歧义。

### 执行顺序是互逆成立的前提

BDJB 按 `BDJB_CMD`、`BDJB_QZJC`、`BDJB_ORDER` 升序执行，且 `QZJC=0`（改单据自身状态）
排在 `QZJC=1`（校验与业务）之前。所以：

```
审核：     QZJC=0 先置 SHBZ=1  →  QZJC=1 校验与业务
取消审核： QZJC=0 先置 SHBZ=0  →  QZJC=1 校验与业务
```

取消审核的业务规则执行时，**本单 `SHBZ` 已经是 0**。任何依赖"已审核单据"的判断都天然
不会把自己算进去——这一点让互逆逻辑成立。若把业务规则挪到 `QZJC=1` 之前，或改成在
`SHBZ` 置 0 前执行，互逆会被破坏。

### 验证方式：验证互逆性，而不是验证固定值

对每一对审核/取消审核，按顺序执行并断言：

```
1. 记录基线（审核之前的状态）
2. 执行审核       -> 断言状态变为"生效态"
3. 执行取消审核   -> 断言状态回到第 1 步的基线（逐字段相等，含 NULL）
4. 再次执行审核   -> 断言与第 2 步完全一致（幂等）
```

第 3 步是互逆性的核心断言。不要只断言"取消审核后等于某个期望值"——那可能是巧合，
也可能掩盖了非互逆的实现。第 4 步保证重复审核不会叠加。


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
