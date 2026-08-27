"""
problem_analyzer.py — 智能战术问题诊断系统

基准体系：
  • UEFA 官方指标体系
  • StatsBomb 数据定义（PPDA, xG, Progressive Pass 等）
  • 国际顶级联赛基准（英超、西甲、意甲）

核心功能：
  1. 自动识别球队战术问题（基于 KPI 异常检测）
  2. 按问题紧急度排序
  3. 生成诊断报告（包含对标数据）
"""

from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
import pandas as pd
import numpy as np


@dataclass
class TacticalProblem:
    """战术问题�义"""

    issue_id: str  # "high_shot_low_xg", "weak_defense_1v1"
    title: str  # "射门选择差"
    description: str
    severity: int  # 1-5, 5 最严重
    affected_team: str
    affected_stat: str
    current_value: float
    benchmark_value: float
    variance: float  # (current - benchmark) / benchmark
    evidence: Dict[str, Any]  # 支持性数据


class ProblemAnalyzer:
    """战术问题分析器"""

    # 国际基准数据（来自英超/西甲平均值）
    BENCHMARKS = {
        "possession_pct": {"mean": 50.5, "std": 12.3},
        "pass_accuracy": {"mean": 82.5, "std": 4.2},
        "shots_total": {"mean": 13.5, "std": 5.1},
        "shots_on_target": {"mean": 5.2, "std": 2.8},
        "xg": {"mean": 1.45, "std": 0.68},
        "xg_to_shot_ratio": {"mean": 0.11, "std": 0.04},
        "ppda": {"mean": 12.5, "std": 3.2},  # 进攻前每次传球
        "pass_into_final_third": {"mean": 8.5, "std": 4.1},
        "crosses_completed": {"mean": 4.2, "std": 2.3},
        "cross_accuracy": {"mean": 28.5, "std": 9.1},
        "duel_success_rate": {"mean": 48.5, "std": 7.3},
        "tackle_success": {"mean": 72.5, "std": 8.1},
        "aerials_won": {"mean": 12.3, "std": 5.2},
        "interceptions": {"mean": 8.5, "std": 3.2},
    }

    def __init__(self):
        self.problems: List[TacticalProblem] = []

    def analyze(self, stats1: Dict[str, float], stats2: Dict[str, float], team1_name: str, team2_name: str) -> List[TacticalProblem]:
        """分析两队的战术问题"""
        self.problems = []

        # 分析 Team 1
        self.problems.extend(self._analyze_team(stats1, team1_name))
        # 分析 Team 2
        self.problems.extend(self._analyze_team(stats2, team2_name))

        # 按严重度排序
        self.problems.sort(key=lambda p: (-p.severity, -abs(p.variance)))

        return self.problems

    def _analyze_team(self, stats: Dict[str, float], team_name: str) -> List[TacticalProblem]:
        """分析单队问题"""
        issues = []

        # 问题 1: 射门选择差（高射门数，低 xG）
        if stats.get("shots_total", 0) > 15 and stats.get("xg", 0) < 1.0:
            issues.append(
                TacticalProblem(
                    issue_id="high_shot_low_xg",
                    title="射门选择差",
                    description="射门数多但质量低，说明位置选择或时机欠佳",
                    severity=4,
                    affected_team=team_name,
                    affected_stat="xg_to_shot_ratio",
                    current_value=stats.get("xg", 0) / max(stats.get("shots_total", 1), 1),
                    benchmark_value=self.BENCHMARKS["xg_to_shot_ratio"]["mean"],
                    variance=-(stats.get("xg", 0) / max(stats.get("shots_total", 1), 1) - self.BENCHMARKS["xg_to_shot_ratio"]["mean"]) / self.BENCHMARKS["xg_to_shot_ratio"]["mean"],
                    evidence={
                        "shots_total": stats.get("shots_total", 0),
                        "xg": stats.get("xg", 0),
                        "shots_on_target": stats.get("shots_on_target", 0),
                    },
                )
            )

        # 问题 2: 进攻效率低（低控球、低传球）
        if stats.get("possession_pct", 50) < 40:
            issues.append(
                TacticalProblem(
                    issue_id="low_possession",
                    title="进攻节奏缺失",
                    description="控球率过低，难以组织有效进攻",
                    severity=3,
                    affected_team=team_name,
                    affected_stat="possession_pct",
                    current_value=stats.get("possession_pct", 50),
                    benchmark_value=self.BENCHMARKS["possession_pct"]["mean"],
                    variance=(stats.get("possession_pct", 50) - self.BENCHMARKS["possession_pct"]["mean"]) / self.BENCHMARKS["possession_pct"]["mean"],
                    evidence={
                        "possession_pct": stats.get("possession_pct", 50),
                        "pass_accuracy": stats.get("pass_accuracy", 0),
                    },
                )
            )

        # 问题 3: 防线不稳（PPDA 高，说明压迫深度浅）
        ppda = stats.get("ppda", 0)
        if ppda > 15 and ppda > 0:
            issues.append(
                TacticalProblem(
                    issue_id="weak_pressure",
                    title="压迫深度浅",
                    description="PPDA 过高，说明防线位置靠后，前场压迫不足",
                    severity=3,
                    affected_team=team_name,
                    affected_stat="ppda",
                    current_value=ppda,
                    benchmark_value=self.BENCHMARKS["ppda"]["mean"],
                    variance=(ppda - self.BENCHMARKS["ppda"]["mean"]) / self.BENCHMARKS["ppda"]["mean"],
                    evidence={
                        "ppda": ppda,
                        "tackle_success": stats.get("tackle_success", 0),
                    },
                )
            )

        # 问题 4: 传中效率低
        if stats.get("cross_accuracy", 0) < 25:
            issues.append(
                TacticalProblem(
                    issue_id="poor_crossing",
                    title="传中精度低",
                    description="传中成功率偏低，边锋/边后卫需要精度训练",
                    severity=2,
                    affected_team=team_name,
                    affected_stat="cross_accuracy",
                    current_value=stats.get("cross_accuracy", 0),
                    benchmark_value=self.BENCHMARKS["cross_accuracy"]["mean"],
                    variance=(stats.get("cross_accuracy", 0) - self.BENCHMARKS["cross_accuracy"]["mean"]) / self.BENCHMARKS["cross_accuracy"]["mean"],
                    evidence={
                        "crosses_total": stats.get("crosses_total", 0),
                        "crosses_completed": stats.get("crosses_completed", 0),
                        "cross_accuracy": stats.get("cross_accuracy", 0),
                    },
                )
            )

        # 问题 5: 防守对抗能力弱（对抗成功率低）
        if stats.get("duel_success_rate", 50) < 45:
            issues.append(
                TacticalProblem(
                    issue_id="weak_duels",
                    title="对抗能力弱",
                    description="身体对抗成功率低，1v1 防守需要加强",
                    severity=3,
                    affected_team=team_name,
                    affected_stat="duel_success_rate",
                    current_value=stats.get("duel_success_rate", 50),
                    benchmark_value=self.BENCHMARKS["duel_success_rate"]["mean"],
                    variance=(stats.get("duel_success_rate", 50) - self.BENCHMARKS["duel_success_rate"]["mean"]) / self.BENCHMARKS["duel_success_rate"]["mean"],
                    evidence={
                        "duels_total": stats.get("duels_total", 0),
                        "duels_won": stats.get("duels_won", 0),
                    },
                )
            )

        # 问题 6: 传球成功率低（容易失球）
        if stats.get("pass_accuracy", 85) < 80:
            issues.append(
                TacticalProblem(
                    issue_id="high_turnover",
                    title="传球精度低",
                    description="传球成功率偏低，容易丢球，后场出球压力大",
                    severity=3,
                    affected_team=team_name,
                    affected_stat="pass_accuracy",
                    current_value=stats.get("pass_accuracy", 85),
                    benchmark_value=self.BENCHMARKS["pass_accuracy"]["mean"],
                    variance=(stats.get("pass_accuracy", 85) - self.BENCHMARKS["pass_accuracy"]["mean"]) / self.BENCHMARKS["pass_accuracy"]["mean"],
                    evidence={
                        "pass_accuracy": stats.get("pass_accuracy", 85),
                        "passes_total": stats.get("passes_total", 0),
                    },
                )
            )

        return issues

    def get_top_problems(self, team_name: str, top_n: int = 3) -> List[TacticalProblem]:
        """获取某队的 Top N 问题"""
        team_problems = [p for p in self.problems if p.affected_team == team_name]
        return team_problems[:top_n]

    def to_dict(self) -> List[Dict[str, Any]]:
        """转为字典格式（用于 JSON 输出）"""
        return [
            {
                "issue_id": p.issue_id,
                "title": p.title,
                "description": p.description,
                "severity": p.severity,
                "team": p.affected_team,
                "stat": p.affected_stat,
                "current": round(p.current_value, 2),
                "benchmark": round(p.benchmark_value, 2),
                "variance_pct": round(p.variance * 100, 1),
                "evidence": p.evidence,
            }
            for p in self.problems
        ]
