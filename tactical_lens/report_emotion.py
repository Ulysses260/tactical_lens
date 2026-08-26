"""
激励型中文赛后报告生成器（Emotion Report）
风格：专业但不冷冰冰，强调亮点、成长点与可执行行动，适合教练给球队/球员看。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _fmt_pct(v: Any) -> str:
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_num(v: Any, digits: int = 2) -> str:
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _safe(s: Dict[str, Any], key: str, default: Any = 0) -> Any:
    return s.get(key, default) if s else default


def generate_emotion_report(
    stats: Dict[str, Dict[str, Any]],
    insights: List[Dict[str, Any]],
    info: Optional[Dict[str, Any]] = None,
    match_name: str = "本场比赛",
) -> str:
    """
    生成激励型中文文字报告。

    stats: {队名: {goals, xg, possession_pct, ...}}
    insights: [{category, text/body, suggestion, priority}, ...]
    """
    info = info or {}
    teams = list(stats.keys())
    lines: List[str] = []

    # ---- 标题 ----
    lines.append("═" * 48)
    lines.append(f"  战术透镜 · 赛后激励报告")
    lines.append(f"  {match_name}")
    if info.get("match_date"):
        lines.append(f"  日期：{info['match_date']}")
    lines.append("═" * 48)
    lines.append("")

    # ---- 比分横幅 ----
    if len(teams) >= 2:
        t1, t2 = teams[0], teams[1]
        s1, s2 = stats[t1], stats[t2]
        g1, g2 = int(_safe(s1, "goals")), int(_safe(s2, "goals"))
        lines.append(f"  {t1}  {g1}  —  {g2}  {t2}")
        lines.append("")
        if g1 > g2:
            lines.append(f"本场由 {t1} 带走胜利。比分只是结果，过程里藏着下一场的答案。")
        elif g1 < g2:
            lines.append(f"本场 {t2} 胜出。失利不是终点，是校准方向的机会。")
        else:
            lines.append("双方战成平局。势均力敌的九十分钟，说明两边都有可打磨的细节。")
        lines.append("")

    # ---- 数据画像（温暖但不含糊） ----
    lines.append("────────────────────────────────")
    lines.append("一、本场数据画像")
    lines.append("────────────────────────────────")
    lines.append("")

    for team in teams:
        s = stats[team]
        lines.append(f"【{team}】")
        lines.append(
            f"  进球 {int(_safe(s, 'goals'))}  ·  "
            f"xG {_fmt_num(_safe(s, 'xg'))}  ·  "
            f"射门 {int(_safe(s, 'shots_total'))}/{int(_safe(s, 'shots_on_target'))}（总/正）"
        )
        lines.append(
            f"  控球 {_fmt_pct(_safe(s, 'possession_pct'))}  ·  "
            f"传球成功率 {_fmt_pct(_safe(s, 'pass_accuracy'))}  ·  "
            f"关键传球 {int(_safe(s, 'key_passes'))}"
        )
        if s.get("formation"):
            lines.append(f"  阵型 {s['formation']}")
        lines.append("")

    # ---- 值得肯定的地方 ----
    lines.append("────────────────────────────────")
    lines.append("二、值得肯定的地方")
    lines.append("────────────────────────────────")
    lines.append("")

    positives = [i for i in insights if int(i.get("priority", 3)) >= 3 or i.get("tone") == "positive"]
    # 从数据里提炼亮点
    auto_highlights: List[str] = []
    for team in teams:
        s = stats[team]
        xg = float(_safe(s, "xg") or 0)
        goals = int(_safe(s, "goals") or 0)
        if goals > 0 and xg > 0 and goals >= xg:
            auto_highlights.append(
                f"{team} 把预期进球转化为实际进球的效率值得肯定（进球 {goals} / xG {_fmt_num(xg)}）。"
            )
        pa = float(_safe(s, "pass_accuracy") or 0)
        if pa >= 85:
            auto_highlights.append(f"{team} 传球成功率达到 {_fmt_pct(pa)}，传导稳定性是继续保持的优势。")
        poss = float(_safe(s, "possession_pct") or 0)
        if poss >= 55:
            auto_highlights.append(f"{team} 控球 {_fmt_pct(poss)}，场面主动权掌握得不错。")

    if auto_highlights:
        for h in auto_highlights[:5]:
            lines.append(f"  ★ {h}")
        lines.append("")
    elif positives:
        for p in positives[:4]:
            text = p.get("body") or p.get("text") or ""
            lines.append(f"  ★ {text}")
        lines.append("")
    else:
        lines.append("  本场双方都付出了努力。把数据摊开看，下一场的进步空间会更清晰。")
        lines.append("")

    # ---- 需要一起面对的课题 ----
    lines.append("────────────────────────────────")
    lines.append("三、需要一起面对的课题")
    lines.append("────────────────────────────────")
    lines.append("")

    critical = sorted(
        [i for i in insights if int(i.get("priority", 3)) <= 2],
        key=lambda x: int(x.get("priority", 3)),
    )
    if critical:
        for i, ins in enumerate(critical[:6], 1):
            cat = ins.get("category") or "综合"
            text = ins.get("body") or ins.get("text") or ""
            lines.append(f"  {i}. [{cat}] {text}")
            if ins.get("suggestion"):
                lines.append(f"     → 行动：{ins['suggestion']}")
            lines.append("")
    else:
        # 数据驱动的温和提醒
        for team in teams:
            s = stats[team]
            xg = float(_safe(s, "xg") or 0)
            goals = int(_safe(s, "goals") or 0)
            shots = int(_safe(s, "shots_total") or 0)
            if shots >= 8 and xg < 1.0:
                lines.append(
                    f"  · {team} 射门次数不少（{shots}），但 xG 仅 {_fmt_num(xg)}，"
                    f"说明机会质量可以再打磨——少打勉强，多创造高价值区位的射门。"
                )
            if goals == 0 and xg >= 1.2:
                lines.append(
                    f"  · {team} xG 达到 {_fmt_num(xg)} 却未能破门，临门一脚与运气都有成分；"
                    f"训练里加强对门与冷静选择的练习会有帮助。"
                )
        if len(lines) and lines[-1] != "":
            lines.append("")
        if not any("·" in ln or "行动" in ln for ln in lines[-8:]):
            lines.append("  本场没有特别刺眼的短板。保持节奏，把细节做到位，就是最好的准备。")
            lines.append("")

    # ---- 给下一场的三句话 ----
    lines.append("────────────────────────────────")
    lines.append("四、给下一场的三句话")
    lines.append("────────────────────────────────")
    lines.append("")
    lines.append("  1. 数据会说谎，态度不会。把今天看到的数字，变成训练场上的一次次重复。")
    lines.append("  2. 赢球时找隐患，输球时找火种——无论比分如何，成长是唯一标准。")
    lines.append("  3. 信任体系，也信任彼此。九十分钟是结果，每天的准备才是答案。")
    lines.append("")

    # ---- 结尾 ----
    lines.append("─" * 48)
    lines.append("本报告由战术透镜生成 · 中文激励版")
    lines.append("数据不会替代你的眼睛，但能帮你看得更准一点。")
    lines.append("─" * 48)

    return "\n".join(lines)
