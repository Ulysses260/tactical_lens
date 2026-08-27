#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Demo Script: Show new features in action
Run: python demo_simple.py
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tactical_lens.format_detector import FormatDetector, FormatType
from tactical_lens.problem_analyzer import ProblemAnalyzer
from tactical_lens.training_standards import get_training_plan, TrainingStandards

def demo():
    print("\n" + "="*70)
    print("TACTICAL LENS - New Features Demo")
    print("="*70)
    
    # Test 1: Format Detector
    print("\n[Test 1] Format Detector Module")
    print("-"*70)
    detector = FormatDetector()
    print("OK: FormatDetector initialized")
    format_types = [f.value for f in FormatType]
    print(f"    Supported formats: {len(format_types)} types")
    print(f"    - {', '.join(format_types)}")
    
    # Test 2: Problem Analyzer
    print("\n[Test 2] Problem Analyzer - Tactical Issues Detection")
    print("-"*70)
    analyzer = ProblemAnalyzer()
    print("OK: ProblemAnalyzer initialized")
    
    # Simulated team data
    team1_stats = {
        "possession_pct": 35.0,      # Below benchmark (50.5%)
        "xG": 0.8,                   # Below benchmark (1.45)
        "pass_accuracy_pct": 72.0,
        "tackles_per_90": 14.2,
        "interceptions_per_90": 4.5,
        "shots_on_target": 2,
    }
    
    team2_stats = {
        "possession_pct": 65.0,      # Above benchmark
        "xG": 2.1,                   # Above benchmark
        "pass_accuracy_pct": 78.0,
        "tackles_per_90": 10.0,
        "interceptions_per_90": 5.2,
        "shots_on_target": 6,
    }
    
    print("\nSimulated Match Data:")
    print(f"  Team A: Possession {team1_stats['possession_pct']}%, xG {team1_stats['xG']}")
    print(f"  Team B: Possession {team2_stats['possession_pct']}%, xG {team2_stats['xG']}")
    
    # Analyze
    print("\nAnalyzing problems...")
    problems = analyzer.analyze(
        team1_stats, 
        team2_stats, 
        team1_name="Team A",
        team2_name="Team B"
    )
    
    print(f"OK: Found {len(problems)} issues\n")
    
    for i, problem in enumerate(problems[:3], 1):
        severity_map = {5: "[CRITICAL]", 4: "[HIGH]", 3: "[MEDIUM]", 2: "[LOW]", 1: "[INFO]"}
        print(f"{i}. {problem.title} {severity_map.get(problem.severity, '')}")
        print(f"   Description: {problem.description}")
        print(f"   Current: {problem.current_value:.2f} vs Benchmark: {problem.benchmark_value:.2f}")
        print(f"   Variance: {problem.variance*100:+.1f}%")
        print(f"   Severity: {problem.severity}/5")
        print()
    
    # Test 3: Training Plan
    print("\n[Test 3] Training Plan Generation")
    print("-"*70)
    
    problems_dict = analyzer.to_dict()
    print(f"OK: Converted {len(problems_dict)} problems to training inputs")
    
    training_plan = get_training_plan(problems_dict, top_n=3)
    
    print(f"\nWeekly Training Schedule (Total: {training_plan['total_duration_min']} min):\n")
    
    for day_info in training_plan["weekly_schedule"]:
        print(f"  {day_info['day']:12} -> {day_info['focus']:30} ({day_info['duration_min']} min)")
    
    # Test 4: Export
    print("\n[Test 4] Export Results to JSON")
    print("-"*70)
    
    export_data = {
        "analysis": {
            "team_a": "Team A",
            "team_b": "Team B",
        },
        "problems_found": len(problems),
        "problems": problems_dict[:3],
        "training": {
            "total_min": training_plan['total_duration_min'],
            "modules": len(training_plan.get("recommended_training", [])),
        }
    }
    
    output_file = "demo_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2)
    
    print(f"OK: Results saved to {output_file}\n")
    
    # Test 5: Training Modules Database
    print("\n[Test 5] Available Training Modules")
    print("-"*70)
    
    ts = TrainingStandards()
    
    print(f"\nTraining Module Categories:")
    print(f"  - Transition Training: {len(ts.TRANSITION_MODULES)} modules")
    print(f"  - Attacking Training: {len(ts.ATTACKING_MODULES)} modules")
    print(f"  - Defending Training: {len(ts.DEFENDING_MODULES)} modules")
    print(f"  - Possession Training: {len(ts.POSSESSION_MODULES)} modules")
    
    # Show one example
    if ts.TRANSITION_MODULES:
        module = ts.TRANSITION_MODULES[0]
        print(f"\nExample Module:")
        print(f"  Name: {module.name_cn} ({module.name_en})")
        print(f"  Duration: {module.duration_min} min, Intensity: {module.intensity}")
        print(f"  Reference: {module.reference_source}")
    
    # Summary
    print("\n" + "="*70)
    print("SUCCESS: All features working!")
    print("="*70)
    print("\nNext steps:")
    print("  1. Try Streamlit UI: streamlit run app_enhanced.py")
    print("  2. Run full tests: pytest tests/test_integrated_system.py -v")
    print("  3. Push to GitHub: git push origin ulysses260-code-structure-review")
    print("  4. See docs: 快速使用指南.md and 改动位置和使用方法.md")
    print()

if __name__ == "__main__":
    try:
        demo()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
