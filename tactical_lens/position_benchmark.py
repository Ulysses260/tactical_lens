"""
Position Benchmark Engine
基于世界杯Top10球员数据的各位置评估基准引擎。

将球队/球员数据与世界杯顶级水准对标，
输出差距分析、强弱项识别和风格分类。
"""

import json
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class StatComparison:
    """单项指标对比结果"""
    stat_name: str
    label: str
    player_value: float
    benchmark_avg: float
    benchmark_elite: float
    unit: str
    higher_is_better: bool
    gap_vs_avg: float        # 与Top10平均值的差距（正=优于基准，负=低于基准）
    gap_vs_elite: float      # 与精英标准的差距
    pct_of_avg: float        # 达到基准平均值的百分比
    rating: str              # elite / above / average / below / far_below

    @property
    def rating_cn(self) -> str:
        mapping = {
            "elite": "🟢 顶级",
            "above": "🔵 优秀",
            "average": "🟡 达标",
            "below": "🟠 不足",
            "far_below": "🔴 显著不足"
        }
        return mapping.get(self.rating, "⚪ 无数据")


@dataclass
class PlayerBenchmarkResult:
    """单个球员的对标结果"""
    player_name: str
    position: str
    comparisons: List[StatComparison] = field(default_factory=list)
    overall_score: float = 0.0
    style_match: str = ""
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)


@dataclass
class TeamBenchmarkResult:
    """一支球队的完整对标结果"""
    team_name: str
    match_info: str
    player_results: Dict[str, PlayerBenchmarkResult] = field(default_factory=dict)
    position_averages: Dict[str, float] = field(default_factory=dict)
    team_strengths: List[str] = field(default_factory=list)
    team_weaknesses: List[str] = field(default_factory=list)
    overall_team_score: float = 0.0


class PositionBenchmarkEngine:
    """位置基准对标引擎"""

    def __init__(self, benchmark_path: Optional[str] = None):
        if benchmark_path is None:
            benchmark_path = os.path.join(
                os.path.dirname(__file__),
                "position_benchmarks.json"
            )
        with open(benchmark_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        self._positions = self._data["positions"]
        self._meta = self._data["meta"]

    @property
    def positions(self) -> Dict:
        return self._positions

    @property
    def meta(self) -> Dict:
        return self._meta

    def get_position_names(self) -> List[str]:
        """返回所有支持的位置代码"""
        return list(self._positions.keys())

    def get_position_info(self, position: str) -> Dict:
        """获取位置的基准信息"""
        pos = position.upper()
        if pos not in self._positions:
            raise ValueError(
                f"未知位置: {position}。"
                f"支持的位置: {', '.join(self._positions.keys())}"
            )
        return self._positions[pos]

    def _compute_rating(
        self, value: float, avg: float, elite: float,
        higher_is_better: bool
    ) -> str:
        """根据数值计算评级"""
        if higher_is_better:
            if value >= elite:
                return "elite"
            elif value >= avg:
                return "above"
            elif value >= avg * 0.8:
                return "average"
            elif value >= avg * 0.6:
                return "below"
            else:
                return "far_below"
        else:
            # 对于越低越好的指标（如失球），反转逻辑
            if value <= elite:
                return "elite"
            elif value <= avg:
                return "above"
            elif value <= avg * 1.2:
                return "average"
            elif value <= avg * 1.5:
                return "below"
            else:
                return "far_below"

    def compare_player(
        self,
        player_name: str,
        position: str,
        stats: Dict[str, float]
    ) -> PlayerBenchmarkResult:
        """
        将单个球员的数据与位置基准进行对比。

        Args:
            player_name: 球员名称
            position: 位置代码 (GK/CB/FB/CDM/CM/W/ST)
            stats: 球员数据字典，key为指标名，value为数值
                   例: {"saves": 18, "save_pct": 78.5, "clean_sheets": 2}

        Returns:
            PlayerBenchmarkResult: 对标分析结果
        """
        pos_info = self.get_position_info(position)
        benchmarks = pos_info["benchmarks"]
        weights = pos_info["evaluation"]["weights"]
        style_templates = pos_info["evaluation"].get("style_templates", {})

        result = PlayerBenchmarkResult(
            player_name=player_name,
            position=position
        )

        total_score = 0.0
        total_weight = 0.0

        for stat_key, stat_data in benchmarks.items():
            if stat_key not in stats:
                continue

            player_val = stats[stat_key]
            avg_val = stat_data["average"]
            elite_val = stat_data["elite"]
            higher = stat_data["higher_is_better"]

            gap_avg = player_val - avg_val
            gap_elite = player_val - elite_val
            pct_avg = (player_val / avg_val * 100) if avg_val != 0 else 0

            if higher:
                pct_of_avg = min(player_val / avg_val * 100, 150)
            else:
                pct_of_avg = min(avg_val / player_val * 100, 150) if player_val > 0 else 0

            rating = self._compute_rating(player_val, avg_val, elite_val, higher)

            comparison = StatComparison(
                stat_name=stat_key,
                label=stat_data["description"],
                player_value=player_val,
                benchmark_avg=avg_val,
                benchmark_elite=elite_val,
                unit=stat_data["unit"],
                higher_is_better=higher,
                gap_vs_avg=gap_avg if higher else -gap_avg,
                gap_vs_elite=gap_elite if higher else -gap_elite,
                pct_of_avg=pct_avg,
                rating=rating
            )
            result.comparisons.append(comparison)

            # 加权评分计算
            w = weights.get(stat_key, 0)
            if higher:
                score = min(player_val / elite_val, 1.5) * 100
            else:
                score = min(elite_val / player_val, 1.5) * 100 if player_val > 0 else 0

            total_score += score * w
            total_weight += w

        if total_weight > 0:
            result.overall_score = total_score / total_weight * (total_weight / sum(weights.values()))
        else:
            result.overall_score = 0

        # 识别强项和弱项
        for comp in result.comparisons:
            if comp.rating in ("elite", "above"):
                result.strengths.append(
                    f"{comp.label}: {comp.player_value}{comp.unit} "
                    f"(基准{comp.benchmark_avg}{comp.unit})"
                )
            elif comp.rating in ("below", "far_below"):
                result.weaknesses.append(
                    f"{comp.label}: {comp.player_value}{comp.unit} "
                    f"(基准{comp.benchmark_avg}{comp.unit}，差距{abs(comp.gap_vs_avg):.1f})"
                )

        return result

    def compare_team(
        self,
        team_name: str,
        match_info: str,
        players: Dict[str, Dict[str, float]],
        positions: Dict[str, str]
    ) -> TeamBenchmarkResult:
        """
        将一支球队的多个球员数据与位置基准进行对比。

        Args:
            team_name: 球队名称
            match_info: 比赛信息描述
            players: 球员数据 {player_name: {stat_key: value, ...}}
            positions: 球员位置映射 {player_name: position_code}

        Returns:
            TeamBenchmarkResult: 球队对标分析结果
        """
        result = TeamBenchmarkResult(
            team_name=team_name,
            match_info=match_info
        )

        position_scores = {}

        for player_name, stats in players.items():
            pos = positions.get(player_name, "CM")  # 默认中场
            player_result = self.compare_player(player_name, pos, stats)
            result.player_results[player_name] = player_result

            if pos not in position_scores:
                position_scores[pos] = []
            position_scores[pos].append(player_result.overall_score)

        # 计算各位置平均分
        for pos, scores in position_scores.items():
            result.position_averages[pos] = sum(scores) / len(scores)

        # 汇总球队强弱项
        all_strengths = []
        all_weaknesses = []
        for pr in result.player_results.values():
            all_strengths.extend(pr.strengths)
            all_weaknesses.extend(pr.weaknesses)

        # 按评级排序，最突出的排在前面
        result.team_strengths = all_strengths[:5]
        result.team_weaknesses = all_weaknesses[:5]

        # 球队总分
        if result.position_averages:
            result.overall_team_score = sum(result.position_averages.values()) / len(result.position_averages)

        return result

    def get_best_xi(self) -> Dict:
        """获取赛事最佳阵容"""
        return self._data.get("best_xi", {})

    def get_style_suggestion(
        self,
        position: str,
        stats: Dict[str, float]
    ) -> str:
        """
        根据球员数据匹配最佳风格模板。
        简单启发式：检查哪些风格模板的关键指标最接近。
        """
        pos_info = self.get_position_info(position)
        templates = pos_info["evaluation"].get("style_templates", {})
        if not templates:
            return "数据不足，无法判断风格"

        # 简单返回最接近的风格（基于总分）
        benchmarks = pos_info["benchmarks"]
        best_match = ""
        best_score = -1

        for style_name, style_desc in templates.items():
            score = 0
            count = 0
            for stat_key in benchmarks:
                if stat_key in stats:
                    bm = benchmarks[stat_key]
                    val = stats[stat_key]
                    if bm["higher_is_better"]:
                        score += min(val / bm["elite"], 1.5)
                    else:
                        score += min(bm["elite"] / val, 1.5) if val > 0 else 0
                    count += 1
            if count > 0:
                avg_score = score / count
                if avg_score > best_score:
                    best_score = avg_score
                    best_match = style_name

        return best_match or list(templates.keys())[0]
