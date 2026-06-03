"""
战术透镜 v4 — 入口
用法：
  python main.py <csv文件路径> [--name 比赛名称] [--template default|concise|coach] [--output 输出目录]
示例：
  python main.py data.csv --name "西甲第10轮" --template default --output ./report
"""
import argparse
import os
import sys

# 把当前目录加到路径，方便 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import auto_load
from stats_engine import compute_match_stats, generate_insights
from visualizer import generate_all_charts
from report_engine import generate_text_report, generate_html_report, ReportTemplate


def main():
    parser = argparse.ArgumentParser(description='战术透镜 — 比赛分析报告生成器')
    parser.add_argument('csv', help='CSV数据文件路径')
    parser.add_argument('--name', default=None, help='比赛名称（默认用文件名）')
    parser.add_argument('--template', default='default', choices=['default', 'concise', 'coach'],
                        help='报告模板：default(完整)/concise(精简)/coach(教练版)')
    parser.add_argument('--output', default='./output', help='输出目录（默认 ./output）')
    args = parser.parse_args()

    # 1. 加载数据
    print(f"\n{'='*50}")
    print(f"  战术透镜 v4")
    print(f"{'='*50}\n")
    print(f"[1/5] 加载数据：{args.csv}")
    df, info = auto_load(args.csv, match_name=args.name)

    # 2. 计算统计
    print(f"\n[2/5] 计算统计数据...")
    stats = compute_match_stats(df, info)

    # 打印核心数据
    for team, s in stats.items():
        print(f"  {team}: {s['goals']}球 | xG {s['xg']:.2f} | 传球{s['pass_accuracy']:.0f}% | 控球{s.get('possession_pct',0):.0f}%")

    # 3. 生成洞察
    print(f"\n[3/5] 生成战术洞察...")
    insights = generate_insights(stats, df, info)
    for ins in insights:
        marker = "★" if ins['priority'] == 1 else "☆" if ins['priority'] == 2 else "·"
        print(f"  {marker} [{ins['category']}] {ins['text']}")

    # 4. 生成图表
    print(f"\n[4/5] 生成图表...")
    chart_paths = generate_all_charts(df, info, stats, output_dir=args.output)

    # 5. 生成报告
    print(f"\n[5/5] 生成报告...")

    # 加载模板
    template_map = {
        'default': os.path.join(os.path.dirname(__file__), 'templates', 'default.json'),
        'concise': os.path.join(os.path.dirname(__file__), 'templates', 'concise.json'),
        'coach': os.path.join(os.path.dirname(__file__), 'templates', 'coach.json'),
    }
    template = ReportTemplate(template_map.get(args.template))

    # 文字版
    text_report = generate_text_report(stats, insights, info, template)
    text_path = os.path.join(args.output, 'report.txt')
    with open(text_path, 'w', encoding='utf-8') as f:
        f.write(text_report)
    print(f"  文字报告 → {text_path}")

    # HTML版
    html_path = os.path.join(args.output, 'report.html')
    generate_html_report(stats, insights, info, chart_paths, template, output_path=html_path)
    print(f"  HTML报告 → {html_path}")

    # 完成
    print(f"\n{'='*50}")
    print(f"  完成！共 {len([v for v in chart_paths.values() if v])} 张图 + 2 份报告")
    print(f"  输出目录：{os.path.abspath(args.output)}")
    print(f"{'='*50}\n")


if __name__ == '__main__':
    main()
