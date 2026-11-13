# 元数据 JOIN / 帮助路由缺陷：报错原文 → 规则 → 定位

## 适用范围

用户报「表单打不开」「标题栏初始化失败」「某某列名无效」「对象 X 和 X 具有相同的表现名称」，
且报错来自客户端生成的 SQL 而非存储过程时，**先用本文件**，不要逐条试改元数据。

典型事故形态：一个字段配错，牵动几十张表单同时报错，改一处又冒出新报错。
本文件的目标是**一次性把全部缺陷扫出来**，再按同一份清单修完，避免来回试。

不适用于：缺物理列、物理表不存在、权限/菜单缺失、BDJB 逻辑错误。

## 第 0 步：先跑全库扫描，不要先看单张表单

`scripts/scan_metadata_defects.sql` 一次查出七类缺陷。**先跑它，再动手。**

```text
sqlcmd -S <server> -d <db> -b -f 65001 -i scripts/scan_metadata_defects.sql
```

七类缺陷（按危险度排序）：

| # | 缺陷 | 后果 |
| --- | --- | --- |
| 1 | 同一 `IOJCBDZD_Vkey` 有两行以上 `TOP=1` | 字段行被放大，重复 JOIN → **1013** |
| 2 | 同一 `(表名, PO)` 内多字段引用同一 `GLZD` 且 `LMark` 都为空 | 生成两条同名 JOIN → **1013** |
| 3 | `帮助` 值在 `IOJCBDZD_BZBH` 中查不到，但能查到 `IOJCBDZD_BZMC` | 帮助窗口拼出空表名 → **'with' 语法错** |
| 4 | `切换=1` 但 `GLZD` 为空 | 投影成 `, as [显示名],` → **'from' 语法错** |
| 5 | `GLZD` 非空但在 `IOJCBDZD` 里没有 `TOP=1` 路由 | 投影/`JOIN` 缺一半 → **156 / 'as' 语法错** |
| 6 | `SYS_TbColumn.字段名` 在物理表里不存在 | **207 列名无效** |
| 7 | `IOJCBDZD_Filter` 不以 `AND`/`SELECT` 开头，或引用了目标表没有的列 | **102 / 207** |

## 报错原文 → 规则对照

这一节是核心。**先按报错原文定位规则，再改数据**，不要凭症状猜。

### `关键字 'from' 附近有语法错误`

客户端生成了空列名。**用 `select  from <表>` 复现确认。**

规则：`SYS_TbColumn.切换=1` 时，`GetDataField` 投影用 `IOJCBDZD_VKEY` 而非 `字段名`
（`SGSoft.cpp` 的 `case when 切换=1 then IOJCBDZD_VKEY else 字段名 end as 字段名1`）。
`GLZD` 为空 → `v_tbcolumn` 关联不到 `IOJCBDZD` → `VKEY` 为 `NULL` → 拼成
`select EAMZCLX_ID as [FID], as [资产类别], ... from EAMZCLX`。

只读定位：

```sql
SELECT 表名, PO, 字段名, 显示名, 切换, GLZD
FROM SYS_TbColumn
WHERE 切换 = 1 AND ISNULL(GLZD, N'') = N'';
```

修法：**补 `GLZD`**（指向该字段要翻译的字典表键列）。**不要改成 `切换=0`**——
那会让显示值变成编号本身，丢掉翻译。

### `关键字 'with' 附近有语法错误`（附「前一个语句必须以分号结尾」）

客户端把空的表名拼进了 `from  with(nolock)`。**用 `from  with(nolock)` 复现。**

规则：`SYS_TbColumn.帮助` 必须填 **`IOJCBDZD_BZBH` 的编码**，不是 `IOJCBDZD_BZMC` 的中文名。
`BaseItemTree.cpp` 用 `GetStrTgValue("IOJCBDZD","IOJCBDZD_BZBH",<帮助值>,"IOJCBDZD_TABLE")`
反查表名，查不到就是空串。

只读定位（**这条最容易被误判，务必用它**）：

```sql
SELECT t.表名, t.PO, t.字段名, t.帮助 AS 当前填的值,
       (SELECT TOP 1 z.IOJCBDZD_BZBH FROM IOJCBDZD z WHERE z.IOJCBDZD_BZMC = t.帮助) AS 应填的编码
FROM SYS_TbColumn t
WHERE ISNULL(t.帮助, N'') <> N''
  AND NOT EXISTS (SELECT 1 FROM IOJCBDZD z WHERE z.IOJCBDZD_BZBH = t.帮助)
  AND EXISTS (SELECT 1 FROM IOJCBDZD z WHERE z.IOJCBDZD_BZMC = t.帮助);
```

修法：把「当前填的值」换成「应填的编码」。

### 帮助编码在 `IOJCBDZD_BZBH` 完全不存在（不是填了中文名）

表现和上一节一样（点帮助报「关键字 'with' 附近有语法错误」），但「应填的编码」那一步
查不到值——该编码在本库根本没有定义。先看有多少字段引用它：

```sql
SELECT c.帮助, COUNT(*) AS 引用数
FROM SYS_TbColumn c
WHERE ISNULL(c.帮助, N'') <> N''
  AND NOT EXISTS (SELECT 1 FROM IOJCBDZD z WHERE z.IOJCBDZD_BZBH = c.帮助)
GROUP BY c.帮助
ORDER BY COUNT(*) DESC;
```

**`IOJCBDZD` 有两个唯一键**：`PK_IOJCBDZD(IOJCBDZD_BH)` 与 `IX_IOJCBDZD(IOJCBDZD_MC)`。
后者是「帮助名唯一」，所以照着现有行插一条同 `MC` 的新编码必定失败：

```
违反了 UNIQUE KEY 约束"IX_IOJCBDZD"。不能在对象"dbo.IOJCBDZD"中插入重复键。重复键值为 (部门信息)。
```

三种修法，按优先级：

1. **把现有行的编码改成元数据在用的那个**（推荐，1 行；元数据不动）：
```sql
-- 先确认旧编码没有字段引用
SELECT COUNT(*) FROM SYS_TbColumn WHERE 帮助 = N'bb';

UPDATE IOJCBDZD SET IOJCBDZD_BZBH = N'BMBZ'
WHERE IOJCBDZD_BZBH = N'bb'
  AND NOT EXISTS (SELECT 1 FROM IOJCBDZD WHERE IOJCBDZD_BZBH = N'BMBZ');
```
2. 改元数据，让字段指向库里已有的编码：`UPDATE SYS_TbColumn SET 帮助 = N'bb' WHERE 帮助 = N'BMBZ';`
3. 确实要两条并存时，新行的 `IOJCBDZD_MC` 必须换成不重复的名字（如 `部门信息(BMBZ)`），否则 2627。

选择依据：旧编码被 `SYS_TbColumn.帮助` 引用数为 0 时它是孤儿，优先改旧行的编码；
被引用时说明两条都有用，只能改元数据或用不同的 `IOJCBDZD_MC` 新增。

### `对象 "X" 和 "X" 在 FROM 子句中有相同的表现名称`（错误 1013）

同一个表被 JOIN 两次且都没有别名。两种来源，**必须分别查**：

**来源 A：同一 Vkey 多行 `TOP=1`**

`v_tbcolumn` 的视图定义是
`LEFT JOIN IOJCBDZD ON SYS_TbColumn.GLZD = IOJCBDZD_Vkey AND IOJCBDZD_TOP = 1`。
同一 Vkey 有两行 `TOP=1`，每条匹配字段行就被复制成两份，`GetCrossTable`
遍历时拼出两条完全相同的 `left join`。

```sql
SELECT IOJCBDZD_Vkey, COUNT(*) AS TOP1行数,
       STUFF((SELECT N',' + z2.IOJCBDZD_BH + N'/' + ISNULL(z2.IOJCBDZD_BZBH, N'')
              FROM IOJCBDZD z2
              WHERE z2.IOJCBDZD_Vkey = z.IOJCBDZD_Vkey AND z2.IOJCBDZD_TOP = 1
              FOR XML PATH('')), 1, 1, N'') AS 冲突行
FROM IOJCBDZD z
WHERE IOJCBDZD_TOP = 1 AND ISNULL(IOJCBDZD_Vkey, N'') <> N''
GROUP BY IOJCBDZD_Vkey
HAVING COUNT(*) > 1;
```

**来源 B：同一字段集内多字段共用 `GLZD` 且都无别名**

```sql
SELECT 表名, PO, GLZD, COUNT(*) AS 引用字段数
FROM SYS_TbColumn
WHERE ISNULL(GLZD, N'') <> N'' AND ISNULL(LMark, N'') = N''
GROUP BY 表名, PO, GLZD
HAVING COUNT(*) > 1;
```

修法见下一节。

## 一主多辅：同一目标表要多个帮助时的唯一正确做法

同一张字典表既做「列转译」又要多个不同过滤的「帮助」时，**不能靠多行 `TOP=1`**。

正确范式（库中既有：`WLBZ`/`WLBZE`、`bb`/`CJBZ2`、`GYSBZ`/`GYSBZ2`）：

| 角色 | `IOJCBDZD_TOP` | 作用 |
| --- | --- | --- |
| 主路由 | **1** | 供 `v_tbcolumn` 关联，负责列转译。**同一 Vkey 只允许一行** |
| 帮助路由 | **0** | 只供帮助窗口按 `IOJCBDZD_BZBH` 反查。**不影响 `v_tbcolumn`，可多行** |

关键：**帮助窗口按 `IOJCBDZD_BZBH` 定位，不看 `TOP`**，所以 `TOP=0` 照样能弹出。
`TOP` 只决定「能不能被 `v_tbcolumn` 关联到」。

```sql
-- 主路由（已有的不要动）
UPDATE IOJCBDZD SET IOJCBDZD_TOP = 1 WHERE IOJCBDZD_BZBH = 'EAMZCLXBZ';

-- 额外的帮助路由：必须是 0
INSERT INTO IOJCBDZD
    (IOJCBDZD_BH, IOJCBDZD_MC, IOJCBDZD_Table, IOJCBDZD_Vkey, IOJCBDZD_BYZD,
     IOJCBDZD_BZBH, IOJCBDZD_BZMC, IOJCBDZD_BTYPE, IOJCBDZD_SXXS,
     IOJCBDZD_TOP, IOJCBDZD_Filter)
VALUES
    (N'<新BH>', N'<名称>', N'<目标表>', N'<同一个Vkey>', N'<显示列>',
     N'<新BZBH编码>', N'<帮助显示名>', NULL, 0,
     0, N'AND <目标表自己的列>=''<值>''');
```

### `IOJCBDZD_TOP` 是 `bit`，不是 `int`

```sql
-- 类型是 bit（sys.types 查得到）
UPDATE IOJCBDZD SET IOJCBDZD_TOP = 2 WHERE ...;   -- 存成 1，等于没改
UPDATE IOJCBDZD SET IOJCBDZD_TOP = 0 WHERE ...;   -- 这才是关掉
```

用户报「明明改成 2 了还是报错」时，先查列类型。`bit` 下任何非 0 值都变成 1。

## `IOJCBDZD_Filter` 的硬约束

`Filter` 是客户端**原样拼在 `WHERE 1=1` 后面**的片段，不是整个条件。

1. **必须以 `AND` 开头**。写成 `EAMZCLX_LBBH='20'` → `where 1=1 EAMZCLX_LBBH='20'` → 102。
2. **值必须带引号**。字符列写 `='20'`，不是 `=20`。
3. **只能引用 `IOJCBDZD_Table` 指向的那张表自己的列**。
   `EAMZCDA` 没有 `EAMZCLX_LBBH`，写了就是 **207 列名无效**。
   要按类别过滤时用子查询：
   ```sql
   AND EAMZCDA_ZCLX IN (SELECT EAMZCLX_BH FROM EAMZCLX WHERE EAMZCLX_LBBH='20')
   ```
4. **不要写死具体编码**（如 `AND EAMZCDA_ZCLX='MJ'`）。用子查询按类别实时取，
   新增类型后自动生效。

## 单字段孤立的 `GLZD` 会让整批表单失效

先跑这个，它能查出「某个 Vkey 从没有 `TOP=1` 路由，但几十个字段在用它」：

```sql
SELECT t.GLZD AS 缺失路由的键, COUNT(*) AS 引用字段数,
       MIN(t.表名) AS 表单示例
FROM SYS_TbColumn t
WHERE ISNULL(t.GLZD, N'') <> N''
  AND NOT EXISTS (SELECT 1 FROM IOJCBDZD z
                  WHERE z.IOJCBDZD_Vkey = t.GLZD AND z.IOJCBDZD_TOP = 1)
GROUP BY t.GLZD
ORDER BY 引用字段数 DESC;
```

后果：`GetDataField` 的 `IOJCBDZD_BYZD` 取不到 → `EAMZCDA_ZC. as [资产编号]` →
**156 `Incorrect syntax near the keyword 'as'`**；`GetCrossTable` 的
`IOJCBDZD_Table` 取不到 → `left join  on ...`。

修法：**补一条 `TOP=1` 主路由**（`Table`/`Vkey`/`BYZD` 填全），不是改那几十个字段。

顺带说明：这类缺失路由往往**早就存在**，只是没人打开那张表单。补一条路由可以
一并修好几十张表单，但也意味着**修复范围远超用户报告的单点**，必须在交付说明里写清楚。

## 同表多渠道引用（一个表里两个字段都要翻译同一张表）

两个字段都要显示同一张字典表的名称时，**必须给其中一个加 `LMark` 别名**，
否则就是 1013。加别名后 `GetDataField` 也会自动带上前缀（`LSBMZD_SY.LSBMZD_MC`），
两处是一致的。

```sql
-- 车间
UPDATE SYS_TbColumn SET LMark = N'LSBMZD_CJ'
 WHERE 表名 = N'<表单>' AND 字段名 = N'<字段A>' AND GLZD = N'LSBMZD_BH';
-- 使用部门
UPDATE SYS_TbColumn SET LMark = N'LSBMZD_SY'
 WHERE 表名 = N'<表单>' AND 字段名 = N'<字段B>' AND GLZD = N'LSBMZD_BH';
```

库中既有写法：`检定计划` 用 `EAMZCDA_ZC`/`EAMZCDA_JJ`，`参照资产借用` 用 `EAMZCLX_LX`。

**注意**：只给 JOIN 侧加别名、字段侧不加，会变成 `Ambiguous column name`。
`LMark` 一行同时决定 JOIN 别名和投影前缀，改一处即可，**不要在 SQL 里手写别名**。

## 改动前必做：建立「改前基线」

一次改动常牵动几十张表单。**改之前先跑全库扫描并留档**，改完再跑一次对比：

```sql
-- 改前/改后各跑一次，保存输出
-- 目标：任何一类缺陷的数量都不能比改前增加
```

判断是否为本次引入：用「改前有没有」而不是「现在有没有」。既有缺陷单列为 WARN，
不和本次失败混在一起计数——否则每次都要重新解释一遍。

## 验收：必须复刻客户端形状

不要只查元数据「看起来对」。**按 `GetDataField` + `GetCrossTable` 的规则拼出真实 SQL 执行**：

- `切换=1` 且 `GLZD<>''` → 投影 `<LMark.><IOJCBDZD_BYZD> as [显示名]`
- `LMark<>''` → `left join <表> as <LMark> on [<RMark>.]<字段名>=<LMark>.<VKEY>`
- `LMark=''` → `left join <表> on [<RMark>.]<字段名>=<VKEY>`
- 帮助窗口 → `select top 100 * from <TABLE> with(nolock) where 1=1 <FILTER> order by <VKEY>`

`scripts/scan_metadata_defects.sql` 内含这套复刻查询，直接用它的输出做验收。

## 停止条件

出现以下情况，停止改配置，改为报告：

- 物理列确实不存在（要改表结构，超出元数据范围）；
- 需要的 `IOJCBDZD` 行与既有行语义冲突，无法判定哪个该是 `TOP=1`；
- 缺失路由会影响几十张表单，需要在交付说明里明确扩大范围并取得确认；
- 报错来自存储过程或 `BDJB` 正文，不是客户端生成的 SQL。

## 常见误判

| 误判 | 事实 |
| --- | --- |
| 「改 `TOP=2` 就关掉了」 | `TOP` 是 `bit`，非 0 即 1 |
| 「`帮助` 填中文名更直观」 | 必须填 `IOJCBDZD_BZBH` 编码 |
| 「`切换=1` + 空 `GLZD`，把 `切换` 改成 0 就行」 | 会丢掉显示值翻译，编号直接显示 |
| 「`Filter` 写 `列='值'` 就行」 | 必须以 `AND` 开头，且只引用目标表自己的列 |
| 「同一张表要两个帮助，加两行 `TOP=1`」 | 必有一行是 `TOP=0` |
| 「`GLZD` 缺失只影响这一个字段」 | 通常影响几十张表单，先跑全库扫描 |
