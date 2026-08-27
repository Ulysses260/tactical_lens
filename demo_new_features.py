#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
演示脚本：展示新功能如何工作
运行：python demo_new_features.py
"""

import os
import sys

# 确保可以导入 tactical_lens
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tactical_lens.format_detector import FormatDetector, detect_format
from tactical_lens.problem_analyzer import ProblemAnalyzer
from tactical_lens.training_standards import get_training_plan, TrainingStandards
from tactical_lens.stats_engine import compute_match_stats
import json

def demo():
    print("=" * 70)
    print("🎯 战术透镜 - 新功能演示")
    print("=" * 70)
    
    # 演示 1: 格式检测
    print("\n【演示 1】格式检测器")
    print("-" * 70)
    detector = FormatDetector()
    print(f"✅ FormatDetector 已初始化")
    print(f"   支持的格式: {[f.value for f in detector.supported_formats]}")
    
    # 演示 2: 问题分析器
    print("\n【演示 2】问题分析器 - 识别战术问题")
    print("-" * 70)
    analyzer = ProblemAnalyzer()
    print(f"✅ ProblemAnalyzer 已初始化")
    
    # 创建模拟的球队数据
    team1_stats = {
        "possession_pct": 35.0,      # 远低于国际基准 50.5%
        "xG": 0.8,                   # 远低于国际基准 1.45
        "pass_accuracy_pct": 72.0,   # 基本正常
        "tackles_per_90": 14.2,      # 正常
        "interceptions_per_90": 4.5, # 正常
        "shots_on_target": 2,        # 低于基准
    }
    
    team2_stats = {
        "possession_pct": 65.0,      # 高于国际基准
        "xG": 2.1,                   # 高于国际基准
        "pass_accuracy_pct": 78.0,   # 很好
        "tackles_per_90": 10.0,      # 低，因为控球多
        "interceptions_per_90": 5.2, # 很好
        "shots_on_target": 6,        # 很好
    }
    
    print(f"\n📊 模拟比赛数据:")
    print(f"   球队 A: 控球率 {team1_stats['possession_pct']}%, xG {team1_stats['xG']}")
    print(f"   球队 B: 控球率 {team2_stats['possession_pct']}%, xG {team2_stats['xG']}")
    
    # 分析问题
    print(f"\n🔍 正在分析问题...")
    problems = analyzer.analyze(
        team1_stats, 
        team2_stats, 
        affected_team="球队 A",
        benchmark_team="球队 B"
    )
    
    print(f"✅ 发现 {len(problems)} 个问题:\n")
    
    severity_icons = {5: "🔴", 4: "🟠", 3: "🟡", 2: "🟢", 1: "⚪"}
    for i, problem in enumerate(problems[:3], 1):
        icon = severity_icons.get(problem.severity, "•")
        print(f"{icon} #{i} {problem.title}")
        print(f"   描述: {problem.description}")
        print(f"   当前值: {problem.current_value:.2f}")
        print(f"   国际基准: {problem.benchmark_value:.2f}")
        print(f"   差异: {problem.variance*100:+.1f}%")
        print(f"   严重度: {problem.severity}/5")
        if problem.evidence:
            print(f"   证据: {'; '.join(problem.evidence[:2])}")
        print()
    
    # 演示 3: 训练计划
    print("\n【演示 3】训练计划生成 - 国际教练方法")
    print("-" * 70)
    
    # 把问题转换为字典格式
    problems_dict = analyzer.to_dict()
    print(f"✅ {len(problems_dict)} 个问题已转换为训练计划输入")
    
    # 生成训练计划
    training_plan = get_training_plan(problems_dict, top_n=3)
    
    print(f"\n📋 周训练计划 (总时长: {training_plan['total_duration_min']} 分钟):\n")
    
    # 显示周日程
    for day_info in training_plan["weekly_schedule"]:
        print(f"   {day_info['day']:12} → {day_info['focus']:30} ({day_info['duration_min']:3d} 分钟)")
    
    # 显示关键训练模块
    print(f"\n🎓 关键训练模块 (Top 3):\n")
    for i, training in enumerate(training_plan.get("recommended_training", [])[:3], 1):
        print(f"{i}. {training['problem']} (优先度: {training['severity']}/5)")
        
        # 显示前 2 个推荐的训练模块
        for j, module in enumerate(training.get("modules", [])[:2], 1):
            print(f"\n   {j}) {module['name']}")
            print(f"      ⏱️  时长: {module['duration']} 分钟")
            print(f"      💪 强度: {module['intensity']}")
            print(f"      📚 参考: {module['reference']}")
            if module.get('coaching_points'):
                print(f"      🎯 要点: {'; '.join(module['coaching_points'][:2])}")
        print()
    
    # 演示 4: 导出结果
    print("\n【演示 4】导出结果为 JSON")
    print("-" * 70)
    
    export_data = {
        "match_summary": {
            "team_a": "球队 A",
            "team_b": "球队 B",
            "analysis_timestamp": "2024-XX-XX",
        },
        "detected_problems": problems_dict[:3],  # Top 3
        "training_plan": {
            "total_duration_min": training_plan['total_duration_min'],
            "weekly_schedule": training_plan["weekly_schedule"],
            "recommended_training_count": len(training_plan.get("recommended_training", [])),
        }
    }
    
    # 保存为 JSON
    output_file = "demo_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 结果已导出到: {output_file}\n")
    
    # 演示 5: 训练模块数据库
    print("\n【演示 5】可用的训练模块 (国际教练方法)")
    print("-" * 70)
    
    print(f"\n✅ 可用的训练模块类别:")
    
    ts = TrainingStandards()
    modules_list = [
        ("转换训练", ts.TRANSITION_MODULES),
        ("进攻训练", ts.ATTACKING_MODULES),
        ("防守训练", ts.DEFENDING_MODULES),
    ]
    
    for category_name, modules in modules_list[:3]:
        print(f"\n🎯 {category_name}: {len(modules)} 个训练模块")
        for module in modules[:1]:  # 只显示第一个
            print(f"   • {module.name_cn} ({module.duration_min}min, {module.intensity}强度)")
            print(f"     参考: {module.reference_source}")
    
    # 演示 6: 总结
    print("\n" + "=" * 70)
    print("✅ 演示完成！")
    print("=" * 70)
    print("\n📌 后续步骤:")
    print("   1. 试用 Streamlit UI: streamlit run app_enhanced.py")
    print("   2. 运行完整测试: pytest tests/test_integrated_system.py -v")
    print("   3. 推送到 GitHub: git push origin ulysses260-code-structure-review")
    print("   4. 查看详细文档: 打开 快速使用指南.md 或 改动位置和使用方法.md")
    print()

if __name__ == "__main__":
    try:
        demo()
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
