SET NOCOUNT ON;
SET XACT_ABORT ON;

/*
    Read-only live audit for metadata-backed header/detail bills.
    The scope is discovered from IOBDZD: EAM tables plus forms explicitly named
    as equipment forms. It intentionally does not infer scope from a generated
    script's hand-maintained bill list.
*/

DECLARE @Forms TABLE
(
    RouteId int NOT NULL PRIMARY KEY,
    FormName nvarchar(100) NULL,
    BillCode nvarchar(100) NULL,
    BillMark nvarchar(100) NULL,
    HeaderTable sysname NULL,
    DetailTable sysname NULL,
    HeaderKey sysname NULL,
    DetailKey sysname NULL
);

/* Every finding is retained until the final result sets are emitted.  Keep
   the table explicit so a compile/runtime error in the auditor cannot be
   mistaken for a clean audit. */
DECLARE @Findings TABLE
(
    Severity varchar(10) NOT NULL,
    FormName nvarchar(100) NULL,
    CheckCode varchar(80) NOT NULL,
    Detail nvarchar(2000) NOT NULL
);

INSERT @Forms
(
    RouteId,FormName,BillCode,BillMark,HeaderTable,DetailTable,HeaderKey,DetailKey
)
SELECT
    d.IOBDZD_ID,d.IOBDZD_MC,d.IOBDZD_BH,d.IOBDZD_MARK,
    d.IOBDZD_HTABLE,d.IOBDZD_FTABLE,d.IOBDZD_HVKEY,d.IOBDZD_FVKEY
FROM dbo.IOBDZD AS d
WHERE d.IOBDZD_HTABLE LIKE N'EAM%'
   OR d.IOBDZD_FTABLE LIKE N'EAM%'
   OR d.IOBDZD_MC LIKE N'%设备%';

/*
    Migration dependency inventory.

    @MigratedColumns is supplied by the caller: this script cannot know which
    physical columns were renamed.  Populate it from the migration's own
    old-to-new map before running the audit, for example:

        INSERT @MigratedColumns (OldName,NewName) VALUES (N'EAMZCDA_CODE',N'EAMZCDA_BH');

    Every entry is then checked against every live dependency carrier, so a
    renamed column cannot survive in a place that no hand-written check happens
    to name.  With an empty @MigratedColumns the migration checks report
    nothing, which is correct for an audit that is not part of a migration.
*/
DECLARE @MigratedColumns TABLE
(
    OldName sysname NOT NULL PRIMARY KEY,
    NewName sysname NULL
);

/* Bounded numbers table used by the identifier tokenizer. */
DECLARE @Nums TABLE (n int NOT NULL PRIMARY KEY);
INSERT @Nums (n)
SELECT TOP (4000) ROW_NUMBER() OVER (ORDER BY (SELECT NULL))
FROM sys.all_objects AS a CROSS JOIN sys.all_objects AS b;

/* Every physical column currently present: a token resolves only against these. */
DECLARE @KnownColumns TABLE (ColumnName sysname NOT NULL PRIMARY KEY);
INSERT @KnownColumns (ColumnName)
SELECT DISTINCT c.name FROM sys.columns AS c;

/* Route identity and physical table/key closure. */
INSERT @Findings
SELECT 'FAIL',f.FormName,'ROUTE_VALUE',N'IOBDZD 路由存在空值：BH/MARK/FORMAT/HTABLE/FTABLE/HVKEY/FVKEY。'
FROM @Forms AS f
JOIN dbo.IOBDZD AS d ON d.IOBDZD_ID=f.RouteId
WHERE NULLIF(LTRIM(RTRIM(d.IOBDZD_BH)),N'') IS NULL
   OR NULLIF(LTRIM(RTRIM(d.IOBDZD_MARK)),N'') IS NULL
   OR NULLIF(LTRIM(RTRIM(d.IOBDZD_FORMAT)),N'') IS NULL
   OR NULLIF(LTRIM(RTRIM(d.IOBDZD_HTABLE)),N'') IS NULL
   OR NULLIF(LTRIM(RTRIM(d.IOBDZD_FTABLE)),N'') IS NULL
   OR NULLIF(LTRIM(RTRIM(d.IOBDZD_HVKEY)),N'') IS NULL
   OR NULLIF(LTRIM(RTRIM(d.IOBDZD_FVKEY)),N'') IS NULL;

INSERT @Findings
SELECT 'FAIL',f.FormName,'ROUTE_MARK',N'IOBDZD_MARK 必须是全库唯一的两个 ASCII 字母。'
FROM @Forms AS f
WHERE LEN(ISNULL(f.BillMark,N''))<>2
   OR f.BillMark LIKE N'%[^A-Za-z]%'
   OR EXISTS
      (
          SELECT 1 FROM dbo.IOBDZD AS d
          WHERE d.IOBDZD_MARK=f.BillMark
          GROUP BY d.IOBDZD_MARK
          HAVING COUNT(*)>1
      );

INSERT @Findings
SELECT 'FAIL',f.FormName,'ROUTE_OBJECT',N'表头、表体或单号键字段不存在。'
FROM @Forms AS f
WHERE OBJECT_ID(N'dbo.'+f.HeaderTable,N'U') IS NULL
   OR OBJECT_ID(N'dbo.'+f.DetailTable,N'U') IS NULL
   OR NOT EXISTS
      (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.'+f.HeaderTable,N'U') AND name=f.HeaderKey)
   OR NOT EXISTS
      (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.'+f.DetailTable,N'U') AND name=f.DetailKey);

/* The visible bill and its independent query dataset are both required. */
INSERT @Findings
SELECT 'FAIL',f.FormName,'META_DATASET',N'维护页或查询页字段集为空。'
FROM @Forms AS f
WHERE NOT EXISTS (SELECT 1 FROM dbo.v_tbcolumn WHERE [表名]=f.FormName)
   OR NOT EXISTS (SELECT 1 FROM dbo.v_tbcolumn WHERE [表名]=f.FormName+N'查询');

/* PO order is a runtime column index for dynamic-bill maintenance metadata. */
INSERT @Findings
SELECT 'FAIL',f.FormName,'MAINT_HEADER_ORDER',N'维护页 PO=1 顺序不是 1..n 连续唯一。'
FROM @Forms AS f
OUTER APPLY
(
    SELECT COUNT(*) AS RowTotal,MIN(TRY_CONVERT(int,[顺序])) AS MinOrder,
           MAX(TRY_CONVERT(int,[顺序])) AS MaxOrder,
           COUNT(DISTINCT TRY_CONVERT(int,[顺序])) AS DistinctOrder,
           SUM(CASE WHEN TRY_CONVERT(int,[顺序]) IS NULL THEN 1 ELSE 0 END) AS NullOrder
    FROM dbo.v_tbcolumn WHERE [表名]=f.FormName AND PO=N'1'
) AS x
WHERE ISNULL(x.RowTotal,0)=0 OR x.MinOrder<>1 OR x.MaxOrder<>x.RowTotal
   OR x.DistinctOrder<>x.RowTotal OR x.NullOrder>0;

INSERT @Findings
SELECT 'FAIL',f.FormName,'MAINT_DETAIL_ORDER',N'维护页明细页签 '+pg.PO+N' 顺序不是 1..n 连续唯一。'
FROM @Forms AS f
CROSS APPLY
(
    SELECT DISTINCT c.PO
    FROM dbo.v_tbcolumn AS c
    WHERE c.[表名]=f.FormName AND TRY_CONVERT(int,c.PO)>1
) AS pg
OUTER APPLY
(
    SELECT COUNT(*) AS RowTotal,MIN(TRY_CONVERT(int,[顺序])) AS MinOrder,
           MAX(TRY_CONVERT(int,[顺序])) AS MaxOrder,
           COUNT(DISTINCT TRY_CONVERT(int,[顺序])) AS DistinctOrder,
           SUM(CASE WHEN TRY_CONVERT(int,[顺序]) IS NULL THEN 1 ELSE 0 END) AS NullOrder
    FROM dbo.v_tbcolumn WHERE [表名]=f.FormName AND PO=pg.PO
) AS x
WHERE ISNULL(x.RowTotal,0)=0 OR x.MinOrder<>1 OR x.MaxOrder<>x.RowTotal
   OR x.DistinctOrder<>x.RowTotal OR x.NullOrder>0;

INSERT @Findings
SELECT 'FAIL',f.FormName,'QUERY_ORDER',N'查询页必须是单一 PO=1 且顺序为 1..n。'
FROM @Forms AS f
OUTER APPLY
(
    SELECT COUNT(*) AS RowTotal,MIN(TRY_CONVERT(int,[顺序])) AS MinOrder,
           MAX(TRY_CONVERT(int,[顺序])) AS MaxOrder,
           COUNT(DISTINCT TRY_CONVERT(int,[顺序])) AS DistinctOrder,
           SUM(CASE WHEN TRY_CONVERT(int,[顺序]) IS NULL THEN 1 ELSE 0 END) AS NullOrder
    FROM dbo.v_tbcolumn WHERE [表名]=f.FormName+N'查询'
) AS x
WHERE EXISTS
      (SELECT 1 FROM dbo.v_tbcolumn WHERE [表名]=f.FormName+N'查询' AND PO<>N'1')
   OR ISNULL(x.RowTotal,0)=0 OR x.MinOrder<>1 OR x.MaxOrder<>x.RowTotal
   OR x.DistinctOrder<>x.RowTotal OR x.NullOrder>0;

/* NULL is not the same as the empty alias consumed by the legacy client. */
INSERT @Findings
SELECT 'FAIL',c.[表名],'RELATION_NULL_ALIAS',
       N'GLZD 关联行的 LMark/RMark 不能为 NULL；无别名时必须存储空字符串。字段：'+ISNULL(c.[字段名],N'<NULL>')
FROM dbo.v_tbcolumn AS c
JOIN @Forms AS f ON f.FormName=c.[表名] OR f.FormName+N'查询'=c.[表名]
WHERE NULLIF(LTRIM(RTRIM(ISNULL(c.GLZD,N''))),N'') IS NOT NULL
  AND (c.LMark IS NULL OR c.RMark IS NULL);

INSERT @Findings
SELECT 'FAIL',c.[表名],'META_NULL_RUNTIME_VALUE',
       N'客户端直接读取的字段值为空：字段/显示名/标签名/类型/控件/RID。字段：'+ISNULL(c.[字段名],N'<NULL>')
FROM dbo.v_tbcolumn AS c
JOIN @Forms AS f ON f.FormName=c.[表名] OR f.FormName+N'查询'=c.[表名]
WHERE NULLIF(LTRIM(RTRIM(ISNULL(c.[字段名],N''))),N'') IS NULL
   OR NULLIF(LTRIM(RTRIM(ISNULL(c.[显示名],N''))),N'') IS NULL
   OR NULLIF(LTRIM(RTRIM(ISNULL(c.[标签名],N''))),N'') IS NULL
   OR NULLIF(LTRIM(RTRIM(ISNULL(c.[类型],N''))),N'') IS NULL
   OR NULLIF(LTRIM(RTRIM(ISNULL(c.[控件],N''))),N'') IS NULL
   OR c.RID IS NULL OR c.RID<=0;

INSERT @Findings
SELECT 'FAIL',c.[表名],'META_MARKER',N'普通动态单据字段的标识必须为 NULL。字段：'+ISNULL(c.[字段名],N'<NULL>')
FROM dbo.v_tbcolumn AS c
JOIN @Forms AS f ON f.FormName=c.[表名] OR f.FormName+N'查询'=c.[表名]
WHERE c.[标识] IS NOT NULL;

/* Fixed aliases and the detail-page outer predicate. */
INSERT @Findings
SELECT 'FAIL',f.FormName,'DETAIL_ALIAS',
       N'维护页明细页签 '+pg.PO+N' 必须恰好有“单号”和“分录号”两个固定别名。'
FROM @Forms AS f
CROSS APPLY
(
    SELECT DISTINCT c.PO
    FROM dbo.v_tbcolumn AS c
    WHERE c.[表名]=f.FormName AND TRY_CONVERT(int,c.PO)>1
) AS pg
WHERE (SELECT COUNT(*) FROM dbo.v_tbcolumn WHERE [表名]=f.FormName AND PO=pg.PO AND [字段名]=f.DetailTable+N'_SJDH' AND [显示名]=N'单号' AND [标签名]=N'单号')<>1
   OR (SELECT COUNT(*) FROM dbo.v_tbcolumn WHERE [表名]=f.FormName AND PO=pg.PO AND [显示名]=N'分录号' AND [标签名]=N'分录号')<>1;

INSERT @Findings
SELECT 'FAIL',f.FormName,'QUERY_ANCHOR',N'查询页表头日期/单号必须各有一个可见必填锚点，且不能用明细字段替代。'
FROM @Forms AS f
WHERE (SELECT COUNT(*) FROM dbo.v_tbcolumn WHERE [表名]=f.FormName+N'查询' AND [字段名]=f.HeaderTable+N'_YWRQ' AND [显示名]=N'日期' AND 显示=1 AND 必填=1)<>1
   OR (SELECT COUNT(*) FROM dbo.v_tbcolumn WHERE [表名]=f.FormName+N'查询' AND [字段名]=f.HeaderTable+N'_SJDH' AND [显示名]=N'单号' AND 显示=1 AND 必填=1)<>1;

INSERT @Findings
SELECT 'FAIL',c.[表名],'QUERY_ALIAS_DUPLICATE',N'查询页显示名或标签名重复：'+ISNULL(c.[显示名],N'<NULL>')
FROM dbo.v_tbcolumn AS c
JOIN @Forms AS f ON f.FormName+N'查询'=c.[表名]
WHERE EXISTS
      (SELECT 1 FROM dbo.v_tbcolumn AS d WHERE d.[表名]=c.[表名] AND d.[显示名]=c.[显示名] GROUP BY d.[表名],d.[显示名] HAVING COUNT(*)>1)
   OR EXISTS
      (SELECT 1 FROM dbo.v_tbcolumn AS d WHERE d.[表名]=c.[表名] AND d.[标签名]=c.[标签名] GROUP BY d.[表名],d.[标签名] HAVING COUNT(*)>1);

/* Relation route and physical-field closure. */
INSERT @Findings
SELECT 'FAIL',c.[表名],'RELATION_ROUTE',N'GLZD 没有唯一可用的 IOJCBDZD 路由：'+ISNULL(c.GLZD,N'<NULL>')
FROM dbo.v_tbcolumn AS c
JOIN @Forms AS f ON f.FormName=c.[表名] OR f.FormName+N'查询'=c.[表名]
OUTER APPLY
(
    SELECT COUNT(*) AS RouteCount
    FROM dbo.IOJCBDZD AS d
    WHERE d.IOJCBDZD_Vkey=c.GLZD
      AND d.IOJCBDZD_TOP=1
) AS r
WHERE NULLIF(LTRIM(RTRIM(ISNULL(c.GLZD,N''))),N'') IS NOT NULL
  AND r.RouteCount<>1;

INSERT @Findings
SELECT 'FAIL',c.[表名],'RELATION_OBJECT',N'GLZD 关联表、键或显示列不存在：'+ISNULL(c.GLZD,N'<NULL>')
FROM dbo.v_tbcolumn AS c
JOIN @Forms AS f ON f.FormName=c.[表名] OR f.FormName+N'查询'=c.[表名]
JOIN dbo.IOJCBDZD AS d ON d.IOJCBDZD_Vkey=c.GLZD AND d.IOJCBDZD_TOP=1
WHERE NULLIF(LTRIM(RTRIM(ISNULL(c.GLZD,N''))),N'') IS NOT NULL
  AND
  (
      OBJECT_ID(N'dbo.'+d.IOJCBDZD_Table,N'U') IS NULL
      OR NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.'+d.IOJCBDZD_Table,N'U') AND name=d.IOJCBDZD_Vkey)
      OR (c.[切换]=1 AND NULLIF(LTRIM(RTRIM(ISNULL(d.IOJCBDZD_BYZD,N''))),N'') IS NULL)
      OR (c.[切换]=1 AND NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.'+d.IOJCBDZD_Table,N'U') AND name=d.IOJCBDZD_BYZD))
  );

INSERT @Findings
SELECT 'FAIL',c.[表名],'META_PHYSICAL_FIELD',N'元数据字段不在表头/表体物理字段中：'+ISNULL(c.[字段名],N'<NULL>')
FROM dbo.v_tbcolumn AS c
JOIN @Forms AS f ON f.FormName=c.[表名] OR f.FormName+N'查询'=c.[表名]
WHERE NOT EXISTS
      (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.'+f.HeaderTable,N'U') AND name=c.[字段名])
  AND NOT EXISTS
      (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.'+f.DetailTable,N'U') AND name=c.[字段名]);

/* Every physical field must be present in both the maintenance and query sets. */
INSERT @Findings
SELECT 'FAIL',f.FormName,'FIELD_CLOSURE',N'表头物理字段未完整注册：'+sc.name
FROM @Forms AS f
JOIN sys.columns AS sc ON sc.object_id=OBJECT_ID(N'dbo.'+f.HeaderTable,N'U')
WHERE NOT EXISTS (SELECT 1 FROM dbo.v_tbcolumn WHERE [表名]=f.FormName AND PO=N'1' AND [字段名]=sc.name)
   OR NOT EXISTS (SELECT 1 FROM dbo.v_tbcolumn WHERE [表名]=f.FormName+N'查询' AND [字段名]=sc.name);

INSERT @Findings
SELECT 'FAIL',f.FormName,'FIELD_CLOSURE',N'表体物理字段未完整注册：'+sc.name
FROM @Forms AS f
JOIN sys.columns AS sc ON sc.object_id=OBJECT_ID(N'dbo.'+f.DetailTable,N'U')
WHERE NOT EXISTS (SELECT 1 FROM dbo.v_tbcolumn WHERE [表名]=f.FormName AND PO=N'2' AND [字段名]=sc.name)
   OR NOT EXISTS (SELECT 1 FROM dbo.v_tbcolumn WHERE [表名]=f.FormName+N'查询' AND [字段名]=sc.name);

/* Date/control semantics are source contracts, not inferred UI decoration. */
INSERT @Findings
SELECT 'FAIL',c.[表名],'TYPE_CONTROL',N'类型/控件与物理列或凭证类型契约不一致：'+c.[字段名]
FROM dbo.v_tbcolumn AS c
JOIN @Forms AS f ON f.FormName=c.[表名] OR f.FormName+N'查询'=c.[表名]
WHERE (UPPER(c.[字段名]) LIKE N'%[_]PJLX'
       AND (c.[类型]<>N'S' OR c.[控件]<>N'S'))
   OR (UPPER(c.[字段名]) LIKE N'%[_]YWRQ' AND c.[类型]<>N'D')
   OR (UPPER(c.[字段名]) LIKE N'%[_]SHBZ'
       AND (c.[类型]<>N'S' OR c.[控件]<>N'E'));

INSERT @Findings
SELECT 'FAIL',f.FormName,'DATE_INIT',N'表头日期必须是物理日期、维护页类型 D、置空=1，并有 SQL 默认日期兜底。'
FROM @Forms AS f
LEFT JOIN sys.columns AS sc
  ON sc.object_id=OBJECT_ID(N'dbo.'+f.HeaderTable,N'U')
 AND sc.name=f.HeaderTable+N'_YWRQ'
LEFT JOIN sys.types AS st ON st.user_type_id=sc.user_type_id
OUTER APPLY
(
    SELECT TOP (1) c.[类型],c.[置空]
    FROM dbo.v_tbcolumn AS c
    WHERE c.[表名]=f.FormName AND c.[字段名]=sc.name
) AS m
WHERE st.name NOT IN (N'date',N'datetime',N'datetime2')
   OR m.[类型]<>N'D' OR ISNULL(m.[置空],0)<>1
   OR NOT EXISTS
      (
          SELECT 1
          FROM sys.default_constraints AS dc
          WHERE dc.parent_object_id=sc.object_id
            AND dc.parent_column_id=sc.column_id
            AND LOWER(CONVERT(nvarchar(max),dc.definition)) LIKE N'%getdate%'
      );

/* BDJB: four standard lifecycle rows are required; verified feature rows are allowed. */
INSERT @Findings
SELECT 'FAIL',f.FormName,'BDJB_BASE',N'缺少审核/撤审四条基础规则；额外业务校验规则不计入缺陷。'
FROM @Forms AS f
WHERE (SELECT COUNT(*) FROM dbo.BDJB WHERE BDJB_PJLX=f.FormName AND BDJB_YX=1 AND BDJB_CMD=N'审核' AND BDJB_QZJC=1 AND ISNULL(BDJB_ORDER,0)=0)<>1
   OR (SELECT COUNT(*) FROM dbo.BDJB WHERE BDJB_PJLX=f.FormName AND BDJB_YX=1 AND BDJB_CMD=N'审核' AND BDJB_QZJC=0 AND ISNULL(BDJB_ORDER,0)=0)<>1
   OR (SELECT COUNT(*) FROM dbo.BDJB WHERE BDJB_PJLX=f.FormName AND BDJB_YX=1 AND BDJB_CMD=N'取消审核' AND BDJB_QZJC=1 AND ISNULL(BDJB_ORDER,0)=0)<>1
   OR (SELECT COUNT(*) FROM dbo.BDJB WHERE BDJB_PJLX=f.FormName AND BDJB_YX=1 AND BDJB_CMD=N'取消审核' AND BDJB_QZJC=0 AND ISNULL(BDJB_ORDER,0)=0)<>1;

INSERT @Findings
SELECT 'FAIL',f.FormName,'BDJB_SQL',N'启用 BDJB 存在空 SQL。'
FROM @Forms AS f
WHERE EXISTS (SELECT 1 FROM dbo.BDJB WHERE BDJB_PJLX=f.FormName AND BDJB_YX=1 AND NULLIF(LTRIM(RTRIM(ISNULL(BDJB_SQL,N''))),N'') IS NULL);

INSERT @Findings
SELECT 'FAIL',f.FormName,'WORKSPACE',N'缺少可见工作区叶节点。'
FROM @Forms AS f
WHERE NOT EXISTS (SELECT 1 FROM dbo.SYSWSPACE WHERE SYSWSPACE_MC=f.FormName AND SYSWSPACE_MX=1 AND SYSWSPACE_BTN=0);

INSERT @Findings
SELECT 'FAIL',f.FormName,'SYSMENU',N'缺少动态单据标准菜单按钮：'+b.ButtonName
FROM @Forms AS f
CROSS JOIN
(
    VALUES (N'显示关联单据'),(N'保存列宽'),(N'列配置'),(N'从EXCEL导入'),
           (N'说明'),(N'附件'),(N'复制分录')
) AS b(ButtonName)
WHERE NOT EXISTS
      (SELECT 1 FROM dbo.sysmenu WHERE sysmenu_bdmc=f.FormName AND sysmenu_buttonname=b.ButtonName);

/*
    Generic stale-reference sweep.

    A physical-column rename is never a metadata-only change: the old name also
    lives inside stored SQL text, and the historical failure was exactly that --
    BDJB rows kept referencing a dropped column while every hand-written check
    passed.  These checks are driven by @MigratedColumns and by the live
    dependency carriers, so they do not name any particular column.

    LIKE metacharacters in the supplied old name are escaped so the match stays
    literal rather than becoming a wildcard.
*/
INSERT @Findings
SELECT 'FAIL',d.BDJB_PJLX,'MIGRATED_REF_IN_BDJB',
       N'BDJB 仍引用已迁移的旧字段 '+m.OldName+N'（'+ISNULL(d.BDJB_CMD,N'<NULL>')+N'）。'
FROM @MigratedColumns AS m
CROSS APPLY
(
    SELECT Esc=REPLACE(REPLACE(REPLACE(m.OldName,N'\',N'\\'),N'%',N'\%'),N'_',N'\_')
) AS e
JOIN dbo.BDJB AS d
  ON ISNULL(d.BDJB_SQL,N'') LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
WHERE d.BDJB_YX=1;

INSERT @Findings
SELECT 'FAIL',o.name,'MIGRATED_REF_IN_MODULE',
       N'存储对象 '+o.name+N' 仍引用已迁移的旧字段 '+m.OldName+N'。'
FROM @MigratedColumns AS m
CROSS APPLY
(
    SELECT Esc=REPLACE(REPLACE(REPLACE(m.OldName,N'\',N'\\'),N'%',N'\%'),N'_',N'\_')
) AS e
JOIN sys.sql_modules AS sm ON sm.definition LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
JOIN sys.objects AS o ON o.object_id=sm.object_id
WHERE o.is_ms_shipped=0;

INSERT @Findings
SELECT 'FAIL',c.[表名],'MIGRATED_REF_IN_METADATA',
       N'元数据仍引用已迁移的旧字段 '+m.OldName+N'（列 '+ISNULL(c.[字段名],N'<NULL>')+N'）。'
FROM @MigratedColumns AS m
CROSS APPLY
(
    SELECT Esc=REPLACE(REPLACE(REPLACE(m.OldName,N'\',N'\\'),N'%',N'\%'),N'_',N'\_')
) AS e
JOIN dbo.v_tbcolumn AS c
  ON c.[字段名] LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
  OR ISNULL(c.GLZD,N'') LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
  OR ISNULL(c.[帮助],N'') LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
JOIN @Forms AS f ON f.FormName=c.[表名] OR f.FormName+N'查询'=c.[表名];

INSERT @Findings
SELECT 'FAIL',r.Carrier,'MIGRATED_REF_IN_RELATION',
       N'关系配置 '+r.Carrier+N' 行 '+r.RowId+N' 仍引用已迁移的旧字段 '+m.OldName+N'。'
FROM @MigratedColumns AS m
CROSS APPLY
(
    SELECT Esc=REPLACE(REPLACE(REPLACE(m.OldName,N'\',N'\\'),N'%',N'\%'),N'_',N'\_')
) AS e
CROSS APPLY
(
    SELECT N'IOYYGX' AS Carrier,CONVERT(nvarchar(40),y.IOYYGX_ID) AS RowId
    FROM dbo.IOYYGX AS y
    WHERE ISNULL(y.IOYYGX_GLTJ,N'')      LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
       OR ISNULL(y.IOYYGX_SYLJ,N'')      LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
       OR ISNULL(y.IOYYGX_XYLJ,N'')      LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
       OR ISNULL(y.IOYYGX_TABLE,N'')     LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
       OR ISNULL(y.IOYYGX_FROMTABLE,N'') LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
    UNION ALL
    SELECT N'IOPOPDLG',CONVERT(nvarchar(40),p.IOPOPDLG_ID)
    FROM dbo.IOPOPDLG AS p
    WHERE ISNULL(p.IOPOPDLG_JOINSTR,N'') LIKE N'%'+e.Esc+N'%' ESCAPE N'\'
) AS r;

/*
    Unknown-identifier check.

    Extracts every whole identifier from each enabled BDJB SQL string and
    reports the ones that (a) look like an IMES column name -- they contain an
    underscore and are at least four characters -- and (b) do not exist as a
    column anywhere in the current database.

    This is the check that catches a renamed physical column surviving inside
    stored SQL text.  It needs no migration map, so it also covers renames that
    happened before this audit existed.  An identifier is located by scanning
    every start position (a letter or underscore not preceded by an identifier
    character) and extending forward to the end of the run, both bounded by
    MIN over @Nums; no LIKE escaping is needed because the character classes are
    fixed and the underscore is matched literally.
*/
INSERT @Findings
SELECT 'FAIL',d.BDJB_PJLX,'BDJB_UNKNOWN_IDENTIFIER',
       N'BDJB 引用了当前库不存在的字段/标识符 '+tok.Token+N'（'+ISNULL(d.BDJB_CMD,N'<NULL>')+N'）。'
FROM dbo.BDJB AS d
CROSS APPLY (SELECT Txt=ISNULL(d.BDJB_SQL,N'')) AS s
CROSS APPLY
(
    SELECT DISTINCT SUBSTRING(s.Txt,b.n,ISNULL(fwd.L,64)) AS Token
    FROM @Nums AS b
    CROSS APPLY
    (
        SELECT MIN(n) AS L FROM @Nums
        WHERE n<=64 AND SUBSTRING(s.Txt,b.n+n,1) NOT LIKE N'[A-Za-z0-9_]'
    ) AS fwd
    WHERE b.n<=LEN(s.Txt)
      AND SUBSTRING(s.Txt,b.n,1) LIKE N'[A-Za-z_]'
      AND (b.n=1 OR SUBSTRING(s.Txt,b.n-1,1) NOT LIKE N'[A-Za-z0-9_]')
) AS tok
WHERE d.BDJB_YX=1
  AND tok.Token LIKE N'%[_]%'
  AND LEN(tok.Token)>=4
  AND NOT EXISTS (SELECT 1 FROM @KnownColumns AS k WHERE k.ColumnName=tok.Token);

/* Emit compact results first; consumers can fail the deployment on any FAIL. */
SELECT Severity,FormName,CheckCode,Detail
FROM @Findings
ORDER BY CASE WHEN Severity='FAIL' THEN 0 ELSE 1 END,FormName,CheckCode;

SELECT
    (SELECT COUNT(*) FROM @Forms) AS ScopedRoutes,
    (SELECT COALESCE(SUM(CASE WHEN FormName IS NULL THEN 1 ELSE 0 END),0) FROM @Forms) AS BlankRouteNames,
    (SELECT COUNT(DISTINCT FormName) FROM @Findings WHERE Severity='FAIL') AS FailedForms,
    (SELECT COUNT(*) FROM @Findings WHERE Severity='FAIL') AS FailureCount;

SELECT f.FormName,
       (SELECT COUNT(*) FROM dbo.BDJB WHERE BDJB_PJLX=f.FormName AND BDJB_YX=1) AS ActiveBDJBRows,
       (SELECT COUNT(*) FROM dbo.v_tbcolumn WHERE [表名]=f.FormName) AS MaintenanceRows,
       (SELECT COUNT(*) FROM dbo.v_tbcolumn WHERE [表名]=f.FormName+N'查询') AS QueryRows
FROM @Forms AS f
ORDER BY f.FormName;

/*
    Report the status instead of throwing: a final THROW would suppress the
    finding detail that the caller needs in order to fix anything.  Consumers
    must fail closed on AuditStatus=FAIL.
*/
SELECT
    CASE WHEN EXISTS (SELECT 1 FROM @Findings WHERE Severity='FAIL')
         THEN N'FAIL' ELSE N'PASS' END AS AuditStatus,
    CASE WHEN EXISTS (SELECT 1 FROM @Findings WHERE Severity='FAIL')
         THEN N'动态单据 live metadata audit failed; deployment is blocked.'
         ELSE N'LIVE_DYNAMIC_BILL_AUDIT_PASS' END AS Result;

SELECT N'LIVE_DYNAMIC_BILL_AUDIT_PASS' AS Result;
