"""
tests/test_integrated_system.py — 集成测试

验证：
  1. 格式检测器能识别所有支持的格式
  2. 问题分析器能自动诊断问题
  3. 训练标准库能生成对应的训练计划
"""

import pytest
from pathlib import Path
from tactical_lens.format_detector import FormatDetector, FormatType
from tactical_lens.problem_analyzer import ProblemAnalyzer
from tactical_lens.training_standards import get_training_plan


class TestFormatDetector:
    """测试格式检测器"""

    def test_detect_csv_format(self, tmp_path):
        """测试 CSV 格式检测"""
        import pandas as pd

        # 创建 StatsBomb CSV
        df = pd.DataFrame({
            "type": ["Pass", "Shot"],
            "team": ["A", "A"],
            "location": ["[10, 20]", "[80, 40]"],
            "possession_team": ["A", "A"],
        })
        csv_file = tmp_path / "statsbomb.csv"
        df.to_csv(csv_file, index=False)

        detector = FormatDetector()
        result = detector.detect(str(csv_file))
        assert result.format_type == FormatType.STATSBOMB_CSV
        assert result.confidence >= 0.90

    def test_detect_custom_csv(self, tmp_path):
        """测试自定义 CSV 检测"""
        import pandas as pd

        df = pd.DataFrame({
            "player": ["Alice", "Bob"],
            "goals": [1, 2],
        })
        csv_file = tmp_path / "custom.csv"
        df.to_csv(csv_file, index=False)

        detector = FormatDetector()
        result = detector.detect(str(csv_file))
        # 应该降级到自定义格式
        assert result.format_type == FormatType.CUSTOM_CSV


class TestProblemAnalyzer:
    """测试问题诊断系统"""

    def test_identify_high_shot_low_xg(self):
        """测试识别"射门数高但 xG 低"问题"""
        stats_team1 = {
            "shots_total": 18,
            "xg": 0.9,
            "shots_on_target": 4,
            "possession_pct": 60,
            "pass_accuracy": 85,
            "ppda": 10,
            "duel_success_rate": 50,
        }

        analyzer = ProblemAnalyzer()
        problems = analyzer.analyze(
            stats_team1, {}, "Team A", "Team B"
        )

        # 应该识别出"射门选择差"问题
        assert any(p.issue_id == "high_shot_low_xg" for p in problems)

    def test_identify_low_possession(self):
        """测试识别低控球问题"""
        stats_team1 = {
            "possession_pct": 35,
            "pass_accuracy": 80,
            "shots_total": 8,
        }

        analyzer = ProblemAnalyzer()
        problems = analyzer.analyze(
            stats_team1, {}, "Team A", "Team B"
        )

        assert any(p.issue_id == "low_possession" for p in problems)

    def test_problem_severity_ranking(self):
        """测试问题按严重度排序"""
        stats_team1 = {
            "shots_total": 18,
            "xg": 0.9,
            "possession_pct": 30,
            "pass_accuracy": 75,
            "ppda": 16,
            "duel_success_rate": 40,
            "cross_accuracy": 20,
        }

        analyzer = ProblemAnalyzer()
        problems = analyzer.analyze(
            stats_team1, {}, "Team A", "Team B"
        )

        # 验证按 severity 排序
        severities = [p.severity for p in problems]
        assert severities == sorted(severities, reverse=True)


class TestTrainingStandards:
    """测试训练标准库"""

    def test_training_modules_for_issue(self):
        """测试获取某问题的训练模块"""
        from tactical_lens.training_standards import get_training_modules_for_issue

        modules = get_training_modules_for_issue("high_shot_low_xg")
        assert len(modules) > 0
        assert all(m.category in ["attacking", "possession"] for m in modules)

    def test_training_plan_generation(self):
        """测试训练计划生成"""
        problems = [
            {
                "issue_id": "high_shot_low_xg",
                "title": "射门选择差",
                "severity": 4,
            },
            {
                "issue_id": "low_possession",
                "title": "进攻节奏缺失",
                "severity": 3,
            },
        ]

        plan = get_training_plan(problems, top_n=2)

        # 验证训练计划包含必要字段
        assert "recommended_training" in plan
        assert "weekly_schedule" in plan
        assert "total_duration_min" in plan
        assert len(plan["recommended_training"]) > 0


class TestEndToEnd:
    """端到端集成测试"""

    def test_full_pipeline(self, tmp_path):
        """测试完整流程：检测 → 分析 → 训练计划"""
        import pandas as pd

        # Step 1: 创建 StatsBomb 格式 CSV
        df = pd.DataFrame({
            "type": ["Pass", "Shot", "Pass"],
            "team": ["A", "A", "A"],
            "location": ["[10, 20]", "[80, 40]", "[50, 50]"],
            "possession_team": ["A", "A", "A"],
        })
        csv_file = tmp_path / "match.csv"
        df.to_csv(csv_file, index=False)

        # Step 2: 检测格式
        detector = FormatDetector()
        result = detector.detect(str(csv_file))
        assert result.format_type == FormatType.STATSBOMB_CSV

        # Step 3: 模拟统计数据
        stats_team_a = {
            "shots_total": 18,
            "xg": 0.9,
            "possession_pct": 35,
            "pass_accuracy": 78,
            "ppda": 14,
            "duel_success_rate": 42,
            "cross_accuracy": 22,
        }

        # Step 4: 分析问题
        analyzer = ProblemAnalyzer()
        problems = analyzer.analyze(stats_team_a, {}, "Team A", "Team B")
        assert len(problems) > 0

        # Step 5: 生成训练计划
        problems_dict = analyzer.to_dict()
        plan = get_training_plan(problems_dict, top_n=3)
        assert plan["total_duration_min"] > 0

        print(f"✅ 端到端测试通过")
        print(f"   识别问题数: {len(problems)}")
        print(f"   推荐训练模块: {len(plan['recommended_training'])}")
        print(f"   周训练时长: {plan['total_duration_min']} 分钟")
