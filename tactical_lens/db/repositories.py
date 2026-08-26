"""
数据仓储层 — Match / User / Upload / Insight / Report
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .connection import get_connection


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class UserRepository:
    def list_all(self) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, username, email, display_name, role, is_active, created_at FROM users"
            ).fetchall()
            return [dict(r) for r in rows]


class UploadRepository:
    def create(
        self,
        original_filename: str,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        mime_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        storage_path: Optional[str] = None,
        detected_format: Optional[str] = None,
    ) -> str:
        upload_id = _uid()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO uploads
                (id, org_id, user_id, original_filename, mime_type, size_bytes, storage_path, parse_status, detected_format)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (upload_id, org_id, user_id, original_filename, mime_type, size_bytes, storage_path, detected_format),
            )
        return upload_id

    def update_status(
        self,
        upload_id: str,
        status: str,
        parse_log: Optional[str] = None,
        detected_format: Optional[str] = None,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE uploads
                SET parse_status = ?,
                    parse_log = COALESCE(?, parse_log),
                    detected_format = COALESCE(?, detected_format)
                WHERE id = ?
                """,
                (status, parse_log, detected_format, upload_id),
            )

    def get(self, upload_id: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
            return dict(row) if row else None


class MatchRepository:
    def create_match(
        self,
        *,
        home_team_name: str,
        away_team_name: str,
        home_score: Optional[int] = None,
        away_score: Optional[int] = None,
        competition: Optional[str] = None,
        season: Optional[str] = None,
        match_date: Optional[str] = None,
        source_type: Optional[str] = None,
        created_by: Optional[str] = None,
        org_id: Optional[str] = None,
        status: str = "parsed",
        notes: Optional[str] = None,
    ) -> str:
        match_id = _uid()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO matches (
                    id, org_id, created_by, competition, season, match_date,
                    home_team_name, away_team_name, home_score, away_score,
                    status, source_type, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id, org_id, created_by, competition, season, match_date,
                    home_team_name, away_team_name, home_score, away_score,
                    status, source_type, notes,
                ),
            )
        return match_id

    def link_upload(self, match_id: str, upload_id: str, role: str = "primary") -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO match_sources (match_id, upload_id, source_role) VALUES (?, ?, ?)",
                (match_id, upload_id, role),
            )

    def save_team_stats(self, match_id: str, stats_by_team: Dict[str, Dict[str, Any]]) -> None:
        """stats_by_team: {team_name: {possession_pct, xg, ...}}"""
        with get_connection() as conn:
            for i, (team_name, s) in enumerate(stats_by_team.items()):
                extra = {k: v for k, v in s.items() if k not in {
                    "formation", "possession_pct", "pass_accuracy", "passes_total",
                    "passes_completed", "shots_total", "shots_on_target", "goals",
                    "xg", "xga", "key_passes", "progressive_passes", "corners",
                    "fouls", "yellow_cards", "red_cards", "ppda",
                }}
                # 序列化不可直接存的对象
                clean_extra = {}
                for k, v in extra.items():
                    try:
                        json.dumps(v)
                        clean_extra[k] = v
                    except (TypeError, ValueError):
                        clean_extra[k] = str(v)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO match_team_stats (
                        match_id, team_name, is_home, formation, possession_pct,
                        pass_accuracy, passes_total, passes_completed,
                        shots_total, shots_on_target, goals, xg, xga,
                        key_passes, progressive_passes, corners, fouls,
                        yellow_cards, red_cards, ppda, extra_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        match_id,
                        team_name,
                        1 if i == 0 else 0,
                        s.get("formation"),
                        s.get("possession_pct"),
                        s.get("pass_accuracy"),
                        s.get("passes_total"),
                        s.get("passes_completed"),
                        s.get("shots_total"),
                        s.get("shots_on_target"),
                        s.get("goals"),
                        s.get("xg"),
                        s.get("xga"),
                        s.get("key_passes"),
                        s.get("progressive_passes"),
                        s.get("corners"),
                        s.get("fouls"),
                        s.get("yellow_cards"),
                        s.get("red_cards"),
                        s.get("ppda"),
                        json.dumps(clean_extra, ensure_ascii=False) if clean_extra else None,
                    ),
                )

    def save_events(self, match_id: str, events: List[Dict[str, Any]]) -> int:
        if not events:
            return 0
        with get_connection() as conn:
            for e in events:
                eid = e.get("id") or _uid()
                raw = e.get("raw_payload")
                if raw is not None and not isinstance(raw, str):
                    raw = json.dumps(raw, ensure_ascii=False)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO events (
                        id, match_id, period, minute, second, timestamp_sec,
                        team_name, player_name, event_type, subtype, outcome,
                        x, y, end_x, end_y, xg, xa, raw_payload
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        eid, match_id,
                        e.get("period"), e.get("minute"), e.get("second"), e.get("timestamp_sec"),
                        e.get("team_name"), e.get("player_name"),
                        e.get("event_type", "unknown"), e.get("subtype"), e.get("outcome"),
                        e.get("x"), e.get("y"), e.get("end_x"), e.get("end_y"),
                        e.get("xg"), e.get("xa"), raw,
                    ),
                )
        return len(events)

    def save_insights(self, match_id: str, insights: List[Dict[str, Any]]) -> int:
        with get_connection() as conn:
            conn.execute("DELETE FROM insights WHERE match_id = ?", (match_id,))
            for ins in insights:
                evidence = ins.get("evidence_json") or ins.get("evidence")
                if evidence is not None and not isinstance(evidence, str):
                    evidence = json.dumps(evidence, ensure_ascii=False)
                conn.execute(
                    """
                    INSERT INTO insights
                    (id, match_id, category, priority, title, body, suggestion, training_key, evidence_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uid(),
                        match_id,
                        ins.get("category"),
                        int(ins.get("priority", 3)),
                        ins.get("title") or ins.get("text", "")[:80],
                        ins.get("body") or ins.get("text", ""),
                        ins.get("suggestion"),
                        ins.get("training_key"),
                        evidence,
                    ),
                )
        return len(insights)

    def save_report(
        self,
        match_id: str,
        *,
        template: str = "emotion",
        format: str = "txt",
        title: Optional[str] = None,
        summary: Optional[str] = None,
        content_text: Optional[str] = None,
        content_path: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> str:
        rid = _uid()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO reports
                (id, match_id, created_by, template, format, title, summary, content_path, content_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (rid, match_id, created_by, template, format, title, summary, content_path, content_text),
            )
            conn.execute(
                "UPDATE matches SET status = 'reported', updated_at = ? WHERE id = ?",
                (_now(), match_id),
            )
        return rid

    def get_match(self, match_id: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
            return dict(row) if row else None

    def list_matches(
        self,
        org_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            if org_id:
                rows = conn.execute(
                    """
                    SELECT * FROM matches WHERE org_id = ?
                    ORDER BY match_date DESC NULLS LAST, created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (org_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM matches
                    ORDER BY match_date DESC, created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_team_stats(self, match_id: str) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM match_team_stats WHERE match_id = ? ORDER BY is_home DESC",
                (match_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_insights(self, match_id: str) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM insights WHERE match_id = ? ORDER BY priority ASC, created_at",
                (match_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_events(self, match_id: str, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            if event_type:
                rows = conn.execute(
                    "SELECT * FROM events WHERE match_id = ? AND event_type = ? ORDER BY timestamp_sec, minute, second",
                    (match_id, event_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events WHERE match_id = ? ORDER BY timestamp_sec, minute, second",
                    (match_id,),
                ).fetchall()
            return [dict(r) for r in rows]
