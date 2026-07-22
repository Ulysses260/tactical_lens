"""
Benchmark Report Generator
根据对标结果生成战术洞察文本。
"""

from typing import Dict, List
from position_benchmark import (
    PlayerBenchmarkResult,
    TeamBenchmarkResult,
    StatComparison,
    PositionBenchmarkEngine,
)


class InsightGenerator:
    """将量化对标结果转化为可理解的战术洞察文本"""

    def __init__(self, engine: PositionBenchmarkEngine):
        self.engine = engine

    def generate_player_report(
        self, result: PlayerBenchmarkResult, verbose: bool = True
    ) -> str:
        """生成单个球员的对标报告"""
        lines = []
        pos_info = self.engine.get_position_info(result.position)

        lines.append(f"{'='*60}")
        lines.append(f"  {result.player_name} | 位置: {pos_info['label']}")
        lines.append(f"  综合评分: {result.overall_score:.1f}/100")
        lines.append(f"{'='*60}")

        # 基准对标表
        lines.append("")
        lines.append("📊 指标对标:")
        lines.append(f"{'指标':<20} {'实际值':>8} {'基准':>8} {'精英':>8} {'达成率':>8} {'评级':>8}")
        lines.append("-" * 72)

        for comp in sorted(result.comparisons, key=lambda c: c.pct_of_avg, reverse=True):
            lines.append(
                f"{comp.label:<18} {comp.player_value:>8.1f} "
                f"{comp.benchmark_avg:>8.1f} {comp.benchmark_elite:>8.1f} "
                f"{comp.pct_of_avg:>7.1f}% {comp.rating_cn:>8}"
            )

        # 强项
        if result.strengths:
            lines.append("")
            lines.append("✅ 强项:")
            for s in result.strengths:
                lines.append(f"  • {s}")

        # 弱项
        if result.weaknesses:
            lines.append("")
            lines.append("⚠️  需提升:")
            for w in result.weaknesses:
                lines.append(f"  • {w}")

        # 风格匹配
        style = self.engine.get_style_suggestion(result.position, {
            c.stat_name: c.player_value for c in result.comparisons
        })
        if style:
            lines.append("")
            lines.append(f"🎯 风格匹配: {style}")

        lines.append("")
        return "\n".join(lines)

    def generate_team_report(self, result: TeamBenchmarkResult) -> str:
        """生成球队完整对标报告"""
        lines = []

        lines.append(f"{'='*60}")
        lines.append(f"  📋 {result.team_name} - 世界杯基准对标报告")
        lines.append(f"  {result.match_info}")
        lines.append(f"  球队综合评分: {result.overall_team_score:.1f}/100")
        lines.append(f"{'='*60}")
        lines.append("")

        # 各位置评分概览
        lines.append("📍 各位置评分:")
        for pos, score in sorted(result.position_averages.items(), key=lambda x: x[1], reverse=True):
            pos_info = self.engine.positions.get(pos, {})
            label = pos_info.get("label", pos)
            bar = self._score_bar(score)
            lines.append(f"  {label:<12} {score:5.1f}/100  {bar}")

        lines.append("")

        # 逐个球员详情
        for name, pr in result.player_results.items():
            lines.append(self.generate_player_report(pr, verbose=False))

        # 球队总结
        lines.append(f"{'─'*60}")
        lines.append("📝 球队总结:")
        lines.append("")

        if result.team_strengths:
            lines.append("✅ 核心优势:")
            for s in result.team_strengths[:3]:
                lines.append(f"  • {s}")

        if result.team_weaknesses:
            lines.append("")
            lines.append("⚠️  关键短板:")
            for w in result.team_weaknesses[:3]:
                lines.append(f"  • {w}")

        # 训练建议
        lines.append("")
        lines.append("💡 训练建议:")
        suggestions = self._generate_suggestions(result)
        for s in suggestions:
            lines.append(f"  • {s}")

        lines.append("")
        return "\n".join(lines)

    def _score_bar(self, score: float, width: int = 20) -> str:
        """生成可视化评分条"""
        filled = int(score / 100 * width)
        filled = max(0, min(width, filled))
        return f"[{'█' * filled}{'░' * (width - filled)}]"

    def _generate_suggestions(self, result: TeamBenchmarkResult) -> List[str]:
        """基于对标结果生成训练建议"""
        suggestions = []

        for name, pr in result.player_results.items():
            pos_info = self.engine.get_position_info(pr.position)
            weights = pos_info["evaluation"]["weights"]

            # 找到权重最高且评分最低的指标
            worst = None
            worst_weighted_score = float("inf")

            for comp in pr.comparisons:
                w = weights.get(comp.stat_name, 0)
                if w == 0:
                    continue
                score = comp.pct_of_avg
                weighted = score * (1 - w)  # 高权重低分 → 更值得优先训练
                if score < 85 and weighted < worst_weighted_score:
                    worst_weighted_score = weighted
                    worst = comp

            if worst:
                suggestions.append(
                    f"{name}({pos_info['label']}): "
                    f"重点提升「{worst.label}」"
                    f"（当前{worst.player_value}{worst.unit}，"
                    f"基准{worst.benchmark_avg}{worst.unit}）"
                )

        return suggestions[:5]  # 最多5条建议

    def generate_comparison_table(
        self, results: List[PlayerBenchmarkResult]
    ) -> str:
        """生成多个球员的快速对比表"""
        if not results:
            return "无数据"

        lines = []
        lines.append(f"{'球员':<15} {'位置':<6} {'综合分':>6} {'强项数':>5} {'弱项数':>5}")
        lines.append("-" * 45)

        for r in sorted(results, key=lambda x: x.overall_score, reverse=True):
            pos_label = self.engine.positions.get(r.position, {}).get("label", r.position)
            lines.append(
                f"{r.player_name:<15} {pos_label:<6} "
                f"{r.overall_score:>5.1f} "
                f"{len(r.strengths):>5} {len(r.weaknesses):>5}"
            )

        return "\n".join(lines)
