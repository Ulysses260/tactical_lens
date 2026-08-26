# Tactical Lens — 数据库基础（Phase 0）

## 概述

本分支引入 **SQLite 结构化比赛库 + 多用户权限**，与现有解析/分析/报告流程解耦，可在无自有服务器环境下（本地 / Streamlit Cloud）运行。

### 已实现

| 模块 | 路径 | 说明 |
|------|------|------|
| Schema | `tactical_lens/db/schema.sql` | users / matches / events / stats / uploads / insights / reports / sessions |
| 连接 | `tactical_lens/db/connection.py` | 初始化、路径、上下文管理 |
| 认证权限 | `tactical_lens/db/auth.py` | 注册登录、会话、角色权限矩阵 |
| 仓储 | `tactical_lens/db/repositories.py` | Match / Upload / Insight / Report CRUD |
| 激励报告 | `tactical_lens/report_emotion.py` | 中文、偏激励的赛后报告 |
| 胶水层 | `tactical_lens/db_integration.py` | 分析完成后一键入库 |

### 角色与权限

| 角色 | 能力 |
|------|------|
| **admin** | 用户管理、全部比赛与报告 |
| **coach** | 创建/更新比赛、上传、生成报告与洞察 |
| **analyst** | 同 coach（分析向） |
| **viewer** | 只读比赛与报告 |

首次 `ensure_db_ready()` / `AuthService().ensure_default_admin()` 会创建默认账号：

- 用户名：`admin`
- 密码：`admin123`  
**请尽快修改。**

### 数据库位置

- 默认：`{仓库根}/data/tactical_lens.db`
- 覆盖：环境变量 `TACTICAL_LENS_DB=/path/to/file.db`

### 最小使用示例

```python
from db.connection import init_db
from db.auth import AuthService
from db_integration import persist_analysis_result, ensure_db_ready

ensure_db_ready()

# 登录
auth = AuthService()
session = auth.login("admin", "admin123")
user = session["user"]

# 分析完成后入库（stats / insights 来自现有引擎）
result = persist_analysis_result(
    stats=stats,
    insights=insights,
    info=info,
    match_name="联赛第10轮",
    source_type="fifa_pdf",
    user_id=user["id"],
)
print(result["match_id"])
print(result.get("emotion_text", "")[:500])
```

### 与现有 Streamlit 集成（下一步）

在 `app.py` 单场分析成功后增加：

```python
try:
    from db_integration import persist_analysis_result
    persist_analysis_result(
        stats=stats,
        insights=insights,
        info=info,
        match_name=match_name,
        source_type=detected_format,
    )
except Exception as e:
    st.warning(f"写入数据库跳过：{e}")
```

并增加「历史比赛」页：调用 `MatchRepository().list_matches()`。

### 后续 Phase

1. **Phase 1** — Excel / 通用 CSV / XML 适配器 + 映射确认 UI  
2. **Phase 2** — 报告模板全面中文化与激励风格接入 PDF  
3. **Phase 3** — Annotator 持久化并对齐 `events` 表  
4. **Phase 4** — 可选 PostgreSQL / 简易 FastAPI，减轻 Streamlit 负担  

### 关于「无服务器」

- SQLite 文件可随 Streamlit 部署（注意 Cloud 的短暂磁盘，重要数据请定期下载备份）
- 多用户目前为应用内账号（非 OAuth）；适合小团队先用
- 以后有服务器时，只需把连接层换成 PostgreSQL，表结构已按可迁移方式设计
