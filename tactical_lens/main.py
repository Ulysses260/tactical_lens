"""
战术透镜 v5 — 入口（支持单文件FIFA/StatsBomb + 目录批量）
用法：
  python main.py <csv文件或目录> [--name 比赛名称] [--template default|concise|coach] [--output 输出目录]
示例：
  python main.py data.csv --name "西甲第10轮" --template default --output ./report
  python main.py 05_attempts_at_goal.csv  ← 单个FIFA射门文件也能直接跑
  python main.py ./fifa_data/              ← FIFA目录批量加载
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import auto_load, is_fifa_csv_dir, load_fifa_directory
from stats_engine import compute_match_stats, generate_insights
from report_engine import generate_text_report, generate_html_report, ReportTemplate


def _try_generate_charts(df, info, stats, output_dir):
    """安全生成图表（FIFA单文件数据缺少坐标时跳过）"""
    chart_paths = {}
    try:
        from visualizer import generate_all_charts
        chart_paths = generate_all_charts(df, info, stats, output_dir=output_dir)
        count = len([v for v in chart_paths.values() if v])
        print(f"  ✓ 生成 {count} 张图表")
    except Exception as e:
        print(f"  ⚠ 图表生成跳过（数据不完整：{e}）")
        chart_paths = {}
    return chart_paths


def main():
    parser = argparse.ArgumentParser(
        description='战术透镜 v5 — 比赛分析报告生成器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py 05_attempts_at_goal.csv    # 单FIFA文件
  python main.py events.csv                 # StatsBomb格式
  python main.py ./fifa_files/              # FIFA目录批量
  python main.py data.csv --template coach  # 教练版报告
        """
    )
    parser.add_argument('input', help='CSV数据文件路径 或 FIFA数据目录路径')
    parser.add_argument('--name', default=None, help='比赛名称（默认用文件名）')
    parser.add_argument('--template', default='default',
                        choices=['default', 'concise', 'coach'],
                        help='报告模板：default(完整)/concise(精简)/coach(教练版)')
    parser.add_argument('--output', default='./output', help='输出目录（默认 ./output）')
    parser.add_argument('--skip-charts', action='store_true', help='跳过图表生成')
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  战术透镜 v5")
    print(f"{'='*50}\n")

    # 确保输出目录存在
    os.makedirs(args.output, exist_ok=True)

    # 1. 加载数据
    print(f"[1/5] 加载数据：{args.input}")

    if os.path.isdir(args.input):
        # 目录模式：批量加载FIFA文件
        if is_fifa_csv_dir(args.input):
            print(f"  → FIFA 数据目录，批量加载...")
            df, info = load_fifa_directory(args.input)
        else:
            print(f"  ✗ 目录中没有可识别的CSV文件")
            sys.exit(1)
    elif os.path.isfile(args.input):
        # 单文件模式
        df, info = auto_load(args.input, match_name=args.name)
    else:
        print(f"  ✗ 找不到文件或目录：{args.input}")
        sys.exit(1)

    if df.empty and 'fifa_stats' not in info:
        print(f"  ✗ 数据为空，无法继续")
        sys.exit(1)

    # 2. 计算统计
    print(f"\n[2/5] 计算统计数据...")

    if info.get('fifa_single_data') or info.get('source') == 'fifa_directory':
        # FIFA模式：stats已在adapter中计算好
        if 'fifa_stats' in info:
            stats = info['fifa_stats']
            print(f"  → FIFA 数据源，使用预计算统计")
        else:
            print(f"  ✗ FIFA数据解析异常，未获取到统计数据")
            sys.exit(1)
    else:
        # StatsBomb/自定义模式：走正常计算流程
        stats = compute_match_stats(df, info)

    # 打印核心数据
    if stats:
        for team, s in stats.items():
            shots = s.get('shots_total', 0)
            goals = s.get('goals', 0)
            xg = s.get('xg', 0)
            pa = s.get('pass_accuracy', 0)
            poss = s.get('possession_pct', 0)
            print(f"  {team}: {goals}球 | 射门{shots} | xG {xg:.2f} | 传球{pa:.0f}% | 控球{poss:.0f}%")
    else:
        print("  ⚠ 无统计数据")
        sys.exit(1)

    # 3. 生成洞察
    print(f"\n[3/5] 生成战术洞察...")

    if info.get('fifa_single_data') or info.get('source') == 'fifa_directory':
        # FIFA模式：使用专用洞察生成器
        from fifa_adapter import generate_fifa_single_insights
        file_type = info.get('fifa_file_type', 'single')
        insights = generate_fifa_single_insights(stats, file_type)
    else:
        insights = generate_insights(stats, df, info)

    for ins in insights:
        marker = "★" if ins.get('priority') == 1 else "☆" if ins.get('priority') == 2 else "·"
        print(f"  {marker} [{ins.get('category', '通用')}] {ins.get('text', '')}")
        if ins.get('suggestion'):
            print(f"      → {ins['suggestion']}")

    # 4. 生成图表（FIFA单文件可能缺少坐标数据，跳过不影响报告）
    print(f"\n[4/5] 生成图表...")
    if args.skip_charts:
        print(f"  → 已跳过（--skip-charts）")
        chart_paths = {}
    else:
        chart_paths = _try_generate_charts(df, info, stats, args.output)

    # 5. 生成报告
    print(f"\n[5/5] 生成报告...")

    # 加载模板
    template_map = {
        'default': os.path.join(os.path.dirname(__file__), 'templates', 'default.json'),
        'concise': os.path.join(os.path.dirname(__file__), 'templates', 'concise.json'),
        'coach': os.path.join(os.path.dirname(__file__), 'templates', 'coach.json'),
    }
    template_path = template_map.get(args.template)
    if os.path.exists(template_path):
        template = ReportTemplate(template_path)
    else:
        template = ReportTemplate()
        print(f"  ⚠ 模板文件不存在，使用默认模板")

    # 文字版
    text_report = generate_text_report(stats, insights, info, template)
    text_path = os.path.join(args.output, 'report.txt')
    with open(text_path, 'w', encoding='utf-8') as f:
        f.write(text_report)
    print(f"  ✓ 文字报告 → {text_path}")

    # HTML版
    html_path = os.path.join(args.output, 'report.html')
    try:
        generate_html_report(stats, insights, info, chart_paths, template, output_path=html_path)
        print(f"  ✓ HTML报告 → {html_path}")
    except Exception as e:
        print(f"  ⚠ HTML报告生成失败（{e}），仅保留文字版")

    # 训练建议（如果有）
    if any(ins.get('training_key') for ins in insights):
        training_path = os.path.join(args.output, 'training_plan.txt')
        with open(training_path, 'w', encoding='utf-8') as f:
            f.write("战术透镜 — 训练建议\n")
            f.write("=" * 40 + "\n\n")
            for ins in insights:
                tk = ins.get('training_key')
                if tk and ins.get('training_recommendations'):
                    f.write(f"【{ins.get('category', '')}】{ins.get('text', '')}\n")
                    f.write(f"  训练方向：{ins.get('training_key', '')}\n")
                    f.write(f"  推荐训练：\n")
                    for tr in ins['training_recommendations']:
                        f.write(f"    • {tr}\n")
                    if ins.get('training_description'):
                        f.write(f"  说明：{ins['training_description']}\n")
                    f.write("\n")
        print(f"  ✓ 训练建议 → {training_path}")

    # 完成
    chart_count = len([v for v in chart_paths.values() if v]) if chart_paths else 0
    report_count = 2 if os.path.exists(html_path) else 1
    has_training = os.path.exists(os.path.join(args.output, 'training_plan.txt'))
    total = chart_count + report_count + (1 if has_training else 0)

    print(f"\n{'='*50}")
    print(f"  完成！{chart_count}张图 + {report_count}份报告" + (" + 训练建议" if has_training else ""))
    print(f"  输出目录：{os.path.abspath(args.output)}")
    print(f"{'='*50}\n")


if __name__ == '__main__':
    main()
