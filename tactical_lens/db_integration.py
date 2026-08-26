"""
将现有分析流程结果写入 SQLite 的胶水层
在 app.py / main.py 分析完成后调用 persist_analysis_result(...)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from db.connection import init_db
from db.repositories import MatchRepository, UploadRepository
from report_emotion import generate_emotion_report


def ensure_db_ready() -> str:
    """初始化数据库（若不存在），返回路径字符串"""
    path = init_db()
    from db.auth import AuthService
    AuthService().ensure_default_admin()
    return str(path)


def persist_analysis_result(
    *,
    stats: Dict[str, Dict[str, Any]],
    insights: List[Dict[str, Any]],
    info: Optional[Dict[str, Any]] = None,
    match_name: str = "自定义比赛",
    source_type: str = "unknown",
    user_id: Optional[str] = None,
    upload_id: Optional[str] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    save_emotion_report: bool = True,
) -> Dict[str, Any]:
    """
    把一场分析结果落入数据库。

    返回: {match_id, report_id?, emotion_text?}
    """
    ensure_db_ready()
    info = info or {}
    teams = list(stats.keys())
    home = teams[0] if teams else "主队"
    away = teams[1] if len(teams) > 1 else "客队"

    home_score = int(stats.get(home, {}).get("goals") or 0)
    away_score = int(stats.get(away, {}).get("goals") or 0) if away in stats else 0

    repo = MatchRepository()
    match_id = repo.create_match(
        home_team_name=home,
        away_team_name=away,
        home_score=home_score,
        away_score=away_score,
        competition=match_name,
        match_date=info.get("match_date"),
        source_type=source_type,
        created_by=user_id,
        status="analyzed",
    )

    if upload_id:
        repo.link_upload(match_id, upload_id, "primary")

    repo.save_team_stats(match_id, stats)

    if insights:
        repo.save_insights(match_id, insights)

    if events:
        repo.save_events(match_id, events)

    result: Dict[str, Any] = {"match_id": match_id}

    if save_emotion_report:
        emotion_text = generate_emotion_report(stats, insights, info, match_name=match_name)
        report_id = repo.save_report(
            match_id,
            template="emotion",
            format="txt",
            title=f"{match_name} · 激励报告",
            summary=emotion_text[:200],
            content_text=emotion_text,
            created_by=user_id,
        )
        result["report_id"] = report_id
        result["emotion_text"] = emotion_text

    return result
