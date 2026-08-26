# db 包说明

- `schema.sql` — 表结构
- `connection.py` — SQLite 连接与 init
- `auth.py` — 多用户、角色、会话
- `repositories.py` — Match / Upload 等仓储

初始化：

```python
from db.connection import init_db
from db.auth import AuthService

init_db()
AuthService().ensure_default_admin()  # admin / admin123
```

环境变量 `TACTICAL_LENS_DB` 可指定数据库文件路径。
