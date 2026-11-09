/* ============================================================================
   scan_metadata_defects.sql —— 元数据 JOIN / 帮助路由缺陷全库扫描
   ----------------------------------------------------------------------------
   用途
     表单报「打不开 / 标题栏初始化失败 / 列名无效 / 对象 X 和 X 具有相同的
     表现名称」时，先跑本脚本，一次性拿到全部缺陷，再按清单修。
     对应 references/metadata-join-help-defects.md。

   只读：全部是 SELECT。不修改任何数据。

   执行
     sqlcmd -S <server> -d <db> -b -f 65001 -i scan_metadata_defects.sql

   输出
     每个缺陷一个结果集，含「严重度 / 编号 / 说明 / 明细」。
     FAIL = 会让客户端生成的 SQL 无法执行。
     WARN = 既有数据缺口，单列出来，不与 FAIL 混合计数。

   关键前提
     · GLZD 扫描必须带 LEN(GLZD)>0。这一族库里存在 Vkey 为空串且 TOP=1
       的路由，朴素 LEFT JOIN 会把一条路由放大成几千条幻影结果。
     · 解析 JOIN 目标不能用 OBJECT_ID(...,'U')：客户端生成 left join <目标>，
       表/视图/同义词都合法。
============================================================================ */
SET NOCOUNT ON;
GO

PRINT N'=== 0. 目标身份 ===';
SELECT DB_NAME() AS 当前库,
       CONVERT(sysname, SERVERPROPERTY('ServerName')) AS 当前实例,
       CONVERT(varchar(20), SERVERPROPERTY('ProductVersion')) AS 版本,
       DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS 排序规则;

/* ---------------------------------------------------------------------------
   1. FAIL：同一 IOJCBDZD_Vkey 有多个 TOP=1
      后果：v_tbcolumn 的 LEFT JOIN 把字段行复制成多份，
            GetCrossTable 拼出多条同名 join → 1013 重复表名。
   --------------------------------------------------------------------------- */
PRINT N'=== 1. FAIL 同一 Vkey 多行 TOP=1 ===';
SELECT N'FAIL' AS 严重度, N'1' AS 编号,
       N'同一 Vkey 多行 TOP=1，会让字段行被放大并生成重复 join（1013）' AS 说明,
       IOJCBDZD_Vkey AS Vkey, COUNT(*) AS TOP1行数,
       STUFF((SELECT N',' + z2.IOJCBDZD_BH + N'/' + ISNULL(z2.IOJCBDZD_BZBH, N'')
              FROM IOJCBDZD z2
              WHERE z2.IOJCBDZD_Vkey = z.IOJCBDZD_Vkey AND z2.IOJCBDZD_TOP = 1
              FOR XML PATH('')), 1, 1, N'') AS 冲突行_BH_BZBH
FROM IOJCBDZD z
WHERE IOJCBDZD_TOP = 1 AND ISNULL(IOJCBDZD_Vkey, N'') <> N''
GROUP BY IOJCBDZD_Vkey
HAVING COUNT(*) > 1;

/* ---------------------------------------------------------------------------
   2. FAIL：同一 (表名, PO) 内多字段引用同一 GLZD 且都无别名
      后果：生成两条完全相同的 left join → 1013。
      修法：给其中一个字段设 LMark（LMark 同时决定 JOIN 别名和投影前缀）。
   --------------------------------------------------------------------------- */
PRINT N'=== 2. FAIL 同表同 PO 同 GLZD 且都无别名 ===';
SELECT N'FAIL' AS 严重度, N'2' AS 编号,
       N'多字段共用同一 GLZD 且 LMark 都为空，会生成重复 join（1013）；需给其一加 LMark' AS 说明,
       表名, PO, GLZD, COUNT(*) AS 引用字段数,
       STUFF((SELECT N',' + t2.字段名 FROM SYS_TbColumn t2
              WHERE t2.表名 = t.表名 AND t2.PO = t.PO AND t2.GLZD = t.GLZD
                AND ISNULL(t2.LMark, N'') = N''
              FOR XML PATH('')), 1, 1, N'') AS 涉及字段
FROM SYS_TbColumn t
WHERE ISNULL(t.GLZD, N'') <> N'' AND ISNULL(t.LMark, N'') = N''
GROUP BY t.表名, t.PO, t.GLZD
HAVING COUNT(*) > 1;

/* ---------------------------------------------------------------------------
   3. FAIL：SYS_TbColumn.帮助 填了 BZMC 中文名而不是 BZBH 编码
      后果：BaseItemTree 按 IOJCBDZD_BZBH 反查表名取不到 → 拼出
            `from  with(nolock)` → 关键字 'with' 附近有语法错误。
   --------------------------------------------------------------------------- */
PRINT N'=== 3. FAIL 帮助填了中文名（应填 BZBH 编码） ===';
SELECT N'FAIL' AS 严重度, N'3' AS 编号,
       N'帮助值在 IOJCBDZD_BZBH 查不到但在 BZMC 能查到，帮助窗口会拼出空表名（with 语法错）' AS 说明,
       t.表名, t.PO, t.字段名, t.显示名,
       t.帮助 AS 当前填的值,
       (SELECT TOP 1 z.IOJCBDZD_BZBH FROM IOJCBDZD z WHERE z.IOJCBDZD_BZMC = t.帮助) AS 应填的编码
FROM SYS_TbColumn t
WHERE ISNULL(t.帮助, N'') <> N''
  AND NOT EXISTS (SELECT 1 FROM IOJCBDZD z WHERE z.IOJCBDZD_BZBH = t.帮助)
  AND EXISTS (SELECT 1 FROM IOJCBDZD z WHERE z.IOJCBDZD_BZMC = t.帮助)
ORDER BY t.表名, t.PO, t.顺序;

/* ---------------------------------------------------------------------------
   4. FAIL：切换=1 但 GLZD 为空
      后果：GetDataField 投影成 `, as [显示名],` → 关键字 'from' 附近有语法错误。
      修法：补 GLZD。不要改成 切换=0（会丢掉显示值翻译）。
   --------------------------------------------------------------------------- */
PRINT N'=== 4. FAIL 切换=1 但 GLZD 为空 ===';
SELECT N'FAIL' AS 严重度, N'4' AS 编号,
       N'切换=1 且 GLZD 为空，投影会变成空列名（from 语法错）；应补 GLZD 而非改 切换' AS 说明,
       表名, PO, 字段名, 显示名, 切换, GLZD
FROM SYS_TbColumn
WHERE 切换 = 1 AND ISNULL(GLZD, N'') = N''
ORDER BY 表名, PO, 顺序;

/* ---------------------------------------------------------------------------
   5. FAIL：GLZD 非空但在 IOJCBDZD 里没有 TOP=1 路由
      后果：GetDataField 的 IOJCBDZD_BYZD 取不到 → `X. as [列]` → 156 'as' 语法错；
            GetCrossTable 的 IOJCBDZD_Table 取不到 → `left join  on ...`。
      注意：这类缺失往往影响几十张表单，补一条 TOP=1 主路由即可全部修好。
   --------------------------------------------------------------------------- */
PRINT N'=== 5. FAIL GLZD 没有 TOP=1 路由 ===';
SELECT N'FAIL' AS 严重度, N'5' AS 编号,
       N'GLZD 指向的 Vkey 没有 TOP=1 路由，投影与 JOIN 会缺一半（156 as 语法错）' AS 说明,
       t.GLZD AS 缺失路由的键, COUNT(*) AS 引用字段数,
       STUFF((SELECT DISTINCT N',' + t2.表名 FROM SYS_TbColumn t2
              WHERE t2.GLZD = t.GLZD
              FOR XML PATH('')), 1, 1, N'') AS 涉及表单
FROM SYS_TbColumn t
WHERE ISNULL(t.GLZD, N'') <> N''
  AND NOT EXISTS (SELECT 1 FROM IOJCBDZD z
                  WHERE z.IOJCBDZD_Vkey = t.GLZD AND z.IOJCBDZD_TOP = 1)
GROUP BY t.GLZD
ORDER BY 引用字段数 DESC;

/* ---------------------------------------------------------------------------
   6. FAIL：SYS_TbColumn.字段名 在物理表里不存在
      后果：207 列名无效。
      只检查「必须是真实物理列」的行，且按客户端 FROM 实际包含的表判断：
        · GLZD 为空（GLZD 非空走 IOJCBDZD 投影）
        · 标识 为空（标识非空是聚合投影）
        · 字段名形如普通标识符（不含 '.'、不含 '('）
        · RMark 为空（非空是别名限定投影，如 a.LSWLZD_WLMC）
        · 该字段名不在本表单任一 JOIN 目标表里
          （同一表单的 GLZD 行会 left join 进 FROM，那些表的列也合法）
      动态单据按 PO 分表：PO=1 → IOBDZD_HTABLE，PO>1 → IOBDZD_FTABLE。
   --------------------------------------------------------------------------- */
PRINT N'=== 6. FAIL 元数据字段名在物理表里不存在 ===';
WITH base AS (
    SELECT o.IOBDZD_MC AS 表名, N'1' AS PO, N'IOBDZD:' + o.IOBDZD_MC AS 来源,
           o.IOBDZD_HTABLE AS 物理表
    FROM IOBDZD o WHERE ISNULL(o.IOBDZD_HTABLE, N'') <> N''
    UNION ALL
    SELECT o.IOBDZD_MC, N'2', N'IOBDZD:' + o.IOBDZD_MC, o.IOBDZD_FTABLE
    FROM IOBDZD o WHERE ISNULL(o.IOBDZD_FTABLE, N'') <> N''
    UNION ALL
    SELECT j.IOJCBDZD_MC, t.PO, N'IOJCBDZD:' + j.IOJCBDZD_MC, j.IOJCBDZD_Table
    FROM IOJCBDZD j
    JOIN (SELECT DISTINCT 表名, PO FROM SYS_TbColumn) t ON t.表名 = j.IOJCBDZD_MC
    WHERE ISNULL(j.IOJCBDZD_Table, N'') <> N''
),
joined AS (
    -- 本表单 GLZD 会 JOIN 进来的表（客户端 GetCrossTable 实际放进 FROM 的表）
    SELECT DISTINCT t.表名, j.IOJCBDZD_Table AS 物理表
    FROM SYS_TbColumn t
    JOIN IOJCBDZD j ON j.IOJCBDZD_Vkey = t.GLZD AND j.IOJCBDZD_TOP = 1
    WHERE LEN(ISNULL(t.GLZD, N'')) > 0 AND ISNULL(j.IOJCBDZD_Table, N'') <> N''
)
SELECT N'FAIL' AS 严重度, N'6' AS 编号,
       N'元数据字段名在物理表与同表单 JOIN 表里都不存在（207 列名无效）' AS 说明,
       t.表名, t.PO, t.字段名, t.显示名, b.物理表, b.来源
FROM SYS_TbColumn t
JOIN base b ON b.表名 = t.表名 AND b.PO = t.PO
WHERE ISNULL(t.GLZD, N'') = N''
  AND ISNULL(t.标识, N'') = N''
  AND ISNULL(t.RMark, N'') = N''
  AND CHARINDEX(N'.', ISNULL(t.字段名, N'')) = 0
  AND CHARINDEX(N'(', ISNULL(t.字段名, N'')) = 0
  AND NOT EXISTS (SELECT 1 FROM sys.columns c
                  WHERE c.object_id = OBJECT_ID(b.物理表) AND c.name = t.字段名)
  AND NOT EXISTS (SELECT 1 FROM joined jn
                  JOIN sys.columns c ON c.object_id = OBJECT_ID(jn.物理表) AND c.name = t.字段名
                  WHERE jn.表名 = t.表名)
ORDER BY t.表名, t.PO, t.顺序;

/* ---------------------------------------------------------------------------
   7. FAIL：IOJCBDZD_Filter 形状可疑
      后果：拼进 WHERE 1=1 后语法错（102/207）。
      约束：必须以 AND/SELECT 开头；只引用目标表自己的列。
   --------------------------------------------------------------------------- */
PRINT N'=== 7. FAIL Filter 形状可疑（缺 AND 开头） ===';
SELECT N'FAIL' AS 严重度, N'7' AS 编号,
       N'Filter 不以 AND/SELECT 开头，拼进 WHERE 1=1 后语法错' AS 说明,
       IOJCBDZD_BH, IOJCBDZD_MC, IOJCBDZD_Table, IOJCBDZD_BZBH,
       IOJCBDZD_Filter
FROM IOJCBDZD
WHERE ISNULL(IOJCBDZD_Filter, N'') <> N''
  AND LTRIM(IOJCBDZD_Filter) NOT LIKE N'AND%'
  AND LTRIM(IOJCBDZD_Filter) NOT LIKE N'SELECT%'
ORDER BY IOJCBDZD_BH;

/* ---------------------------------------------------------------------------
   8. WARN：帮助编码在 IOJCBDZD 中完全不存在（既无 BZBH 也无 BZMC）
      这类是既有数据缺口，不是本次改动引入。单列出来，不计入 FAIL。
   --------------------------------------------------------------------------- */
PRINT N'=== 8. WARN 帮助编码完全悬空（既有缺口，非本次引入） ===';
SELECT N'WARN' AS 严重度, N'8' AS 编号,
       N'帮助编码在 IOJCBDZD 中完全不存在，点帮助会报 with 语法错（既有缺口）' AS 说明,
       t.帮助 AS 悬空编码, COUNT(*) AS 引用字段数
FROM SYS_TbColumn t
WHERE ISNULL(t.帮助, N'') <> N''
  AND NOT EXISTS (SELECT 1 FROM IOJCBDZD z
                  WHERE z.IOJCBDZD_BZBH = t.帮助 OR z.IOJCBDZD_BZMC = t.帮助)
GROUP BY t.帮助
ORDER BY 引用字段数 DESC;

/* ---------------------------------------------------------------------------
   9. WARN：切换=1 的 BYZD 无法唯一反查（保存后编号会变空）
      后果：用户选了值，保存后字段是空。
   --------------------------------------------------------------------------- */
PRINT N'=== 9. WARN 切换行的 BYZD 反查可能不唯一 ===';
SELECT N'WARN' AS 严重度, N'9' AS 编号,
       N'切换=1 的 BYZD 可能不是唯一键，保存时反查不到会写空' AS 说明,
       t.表名, t.PO, t.字段名, t.显示名, t.GLZD,
       j.IOJCBDZD_Table AS 目标表, j.IOJCBDZD_BYZD AS 用于反查的显示列, j.IOJCBDZD_Vkey AS 回写列
FROM SYS_TbColumn t
JOIN IOJCBDZD j ON j.IOJCBDZD_Vkey = t.GLZD AND j.IOJCBDZD_TOP = 1
WHERE t.切换 = 1 AND LEN(ISNULL(t.GLZD, N'')) > 0
  AND ISNULL(j.IOJCBDZD_BYZD, N'') = N''
ORDER BY t.表名, t.PO, t.顺序;

/* ---------------------------------------------------------------------------
   10. 汇总：先看这个，再决定要不要翻明细
   --------------------------------------------------------------------------- */
PRINT N'=== 10. 汇总 ===';
;WITH d1 AS (SELECT COUNT(*) n FROM (SELECT IOJCBDZD_Vkey FROM IOJCBDZD
              WHERE IOJCBDZD_TOP = 1 AND ISNULL(IOJCBDZD_Vkey, N'') <> N''
              GROUP BY IOJCBDZD_Vkey HAVING COUNT(*) > 1) x),
d2 AS (SELECT COUNT(*) n FROM (SELECT 表名, PO, GLZD FROM SYS_TbColumn
              WHERE ISNULL(GLZD, N'') <> N'' AND ISNULL(LMark, N'') = N''
              GROUP BY 表名, PO, GLZD HAVING COUNT(*) > 1) x),
d3 AS (SELECT COUNT(*) n FROM SYS_TbColumn t
              WHERE ISNULL(t.帮助, N'') <> N''
                AND NOT EXISTS (SELECT 1 FROM IOJCBDZD z WHERE z.IOJCBDZD_BZBH = t.帮助)
                AND EXISTS (SELECT 1 FROM IOJCBDZD z WHERE z.IOJCBDZD_BZMC = t.帮助)),
d4 AS (SELECT COUNT(*) n FROM SYS_TbColumn WHERE 切换 = 1 AND ISNULL(GLZD, N'') = N''),
d5 AS (SELECT COUNT(*) n FROM (SELECT GLZD FROM SYS_TbColumn t
              WHERE ISNULL(GLZD, N'') <> N''
                AND NOT EXISTS (SELECT 1 FROM IOJCBDZD z
                                WHERE z.IOJCBDZD_Vkey = t.GLZD AND z.IOJCBDZD_TOP = 1)
              GROUP BY GLZD) x),
d7 AS (SELECT COUNT(*) n FROM IOJCBDZD
              WHERE ISNULL(IOJCBDZD_Filter, N'') <> N''
                AND LTRIM(IOJCBDZD_Filter) NOT LIKE N'AND%'
                AND LTRIM(IOJCBDZD_Filter) NOT LIKE N'SELECT%'),
w8 AS (SELECT COUNT(*) n FROM (SELECT 帮助 FROM SYS_TbColumn t
              WHERE ISNULL(t.帮助, N'') <> N''
                AND NOT EXISTS (SELECT 1 FROM IOJCBDZD z
                                WHERE z.IOJCBDZD_BZBH = t.帮助 OR z.IOJCBDZD_BZMC = t.帮助)
              GROUP BY 帮助) x)
SELECT N'1.同Vkey多行TOP=1（1013）' AS 检查项, CAST(d1.n AS nvarchar(20)) AS 命中数, N'FAIL' AS 级别 FROM d1
UNION ALL SELECT N'2.同表同PO同GLZD无别名（1013）', CAST(d2.n AS nvarchar(20)), N'FAIL' FROM d2
UNION ALL SELECT N'3.帮助填了中文名（with 语法错）', CAST(d3.n AS nvarchar(20)), N'FAIL' FROM d3
UNION ALL SELECT N'4.切换=1但GLZD为空（from 语法错）', CAST(d4.n AS nvarchar(20)), N'FAIL' FROM d4
UNION ALL SELECT N'5.GLZD无TOP=1路由（as 语法错）', CAST(d5.n AS nvarchar(20)), N'FAIL' FROM d5
UNION ALL SELECT N'7.Filter形状可疑（102/207）', CAST(d7.n AS nvarchar(20)), N'FAIL' FROM d7
UNION ALL SELECT N'8.帮助编码完全悬空（既有缺口）', CAST(w8.n AS nvarchar(20)), N'WARN' FROM w8
UNION ALL SELECT N'6.字段名悬空（207）', N'见上方明细（按表单分组计数）', N'FAIL';

SELECT N'扫描完成' AS 总结,
       N'FAIL 项必须全部修复后再验收；WARN 项为既有缺口，单列说明。' AS 说明;
GO
