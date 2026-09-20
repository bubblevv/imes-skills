# IMES Skills

面向 IMES（Sega ERP）SQL Server 数据库开发与排障的插件集合，同时支持 **Claude Code** 和 **Codex**。

仓库本身是一个插件市场（marketplace）。安装一次之后，后续更新通过 `update` 命令拉取，不需要再手工复制目录。

## 包含的插件

| 插件 | 用途 |
| --- | --- |
| `imes-db-development-testing` | 业务表设计、表结构迁移、索引与约束、存储过程、自定义报表、BDJB、PDA、报工、审核/撤审、回填、同步、元数据驱动的表单契约 |

## 安装

### Claude Code

```bash
claude plugin marketplace add bubblevv/imes-skills
claude plugin install imes-db-development-testing@imes-skills
```

安装后重开会话，或执行 `/reload-plugins`。

### Codex

```bash
codex plugin marketplace add bubblevv/imes-skills
codex plugin add imes-db-development-testing@imes-skills
```

安装后开新线程，Codex 才会加载到新技能。

## 更新

```bash
# Claude Code
claude plugin marketplace update imes-skills
claude plugin update imes-db-development-testing      # 需重启会话生效

# Codex
codex plugin marketplace upgrade imes-skills
codex plugin add imes-db-development-testing@imes-skills
```

## 数据库安全边界

- 本仓库**不包含**服务器地址、端口、账号、密码、连接字符串或任何客户数据。
- 技能默认只做**只读**调查。写入、部署和数据修复必须由使用者在当前对话中明确授权，并按其所在项目的规则执行。
- 技能内的规则是跨客户复用的通用规律。**具体的客户、账套、服务器和现场值属于使用方自己的项目**，不要写进本仓库。

## 仓库结构

```
.
├── .claude-plugin/marketplace.json     Claude Code 市场清单
├── .agents/plugins/marketplace.json    Codex 市场清单
└── plugins/
    └── imes-db-development-testing/
        ├── .claude-plugin/plugin.json  Claude Code 插件清单
        ├── .codex-plugin/plugin.json   Codex 插件清单
        ├── SKILL.md                    技能入口（两端共用）
        ├── references/                 分主题参考文档
        ├── scripts/                    脚手架与校验脚本
        └── agents/openai.yaml          Codex 显示元数据
```

## 维护

### 校验

```bash
claude plugin validate .                 # 校验市场与插件清单
cd plugins/imes-db-development-testing
python -X utf8 scripts/self_test.py
```

### 自测中的 ER 夹具

`scripts/self_test.py` 里有两个用例需要一份真实的项目 ER 图 SVG。该图属于具体客户资料，**没有随仓库分发**。未配置时这两个用例会打印跳过提示并返回，其余用例照常执行。

要在本地跑完整覆盖，把环境变量指向你自己的 ER 图：

```bash
export IMES_SKILL_ER_SVG="/path/to/你的ER图.svg"      # PowerShell: $env:IMES_SKILL_ER_SVG="..."
python -X utf8 scripts/self_test.py
```

### 发版

```bash
# 1. 修改 plugins/imes-db-development-testing 下的内容
# 2. 同步提升两个 plugin.json 的 version
# 3. 校验后提交
claude plugin validate .
git commit -am "release v1.0.1"

# 4. 打标签并推送（会校验 plugin.json 与市场条目版本一致）
claude plugin tag --push
```

标签格式为 `imes-db-development-testing--v<version>`。

## 许可

专有软件，未经授权不得分发。详见 [LICENSE](LICENSE)。
