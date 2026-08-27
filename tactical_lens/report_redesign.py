"""
report_redesign.py — 重构的 PDF 报告结构

新报告结构（9 页，训练置顶）:
  第 1 页: 【专业简介】Executive Summary + Top 3 问题
  第 2 页: 【训练计划】推荐训练模块 + 周训练日程
  第 3 页: 【图例说明】所有图表和指标的基础讲解
  第 4 页: 核心数据对比 + 问题分析
  第 5 页: 进攻端分析（射门位置图 + 传球网络）
  第 6 页: 防守端分析（防守热力图 + 对抗数据）
  第 7 页: 战术风格（雷达图 + 对标分析）
  第 8 页: 体能与传球（五分区 + 传球网络）
  第 9 页: 洞察和后续行动
"""

from typing import Dict, List, Any, Tuple
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, PageBreak


# ===== 颜色定义 =====
PRIMARY_COLOR = "#1a365d"  # 深蓝
ACCENT_COLOR = "#2563eb"  # 强调蓝
SUCCESS_COLOR = "#10b981"  # 绿色（好的指标）
WARNING_COLOR = "#f97316"  # 橙色（需关注）
CRITICAL_COLOR = "#ef4444"  # 红色（严重问题）


class ExecutiveSummaryPage:
    """第 1 页：专业简介"""

    @staticmethod
    def build(styles, info, problems_dict, stats1, stats2, team1, team2):
        """生成专业简介页"""
        story = []

        # 标题
        story.append(
            Paragraph(
                "比赛战术分析报告 - 专业简介",
                styles["title_main"],
            )
        )
        story.append(Spacer(1, 8 * mm))

        # 比赛基本信息
        match_info_text = (
            f"<b>{team1} vs {team2}</b><br/>"
            f"日期：{info.get('match_date', 'N/A')}<br/>"
            f"场地：{info.get('stadium', 'N/A')}<br/>"
            f"赛事：{info.get('competition', 'N/A')}"
        )
        story.append(Paragraph(match_info_text, styles["body"]))
        story.append(Spacer(1, 8 * mm))

        # 【关键指标对比】
        story.append(Paragraph("【关键指标对比】", styles["section_title"]))

        comparison_data = [
            ["指标", team1, team2, "差值", "评估"],
            [
                "控球率",
                f"{stats1.get('possession_pct', 50):.1f}%",
                f"{stats2.get('possession_pct', 50):.1f}%",
                f"{abs(stats1.get('possession_pct', 50) - stats2.get('possession_pct', 50)):.1f}%",
                "↑ 优势" if stats1.get("possession_pct", 50) > stats2.get("possession_pct", 50) else "↓ 劣势",
            ],
            [
                "射门数/xG",
                f"{stats1.get('shots_total', 0)}/{stats1.get('xg', 0):.2f}",
                f"{stats2.get('shots_total', 0)}/{stats2.get('xg', 0):.2f}",
                "",
                "",
            ],
            [
                "传球成功率",
                f"{stats1.get('pass_accuracy', 85):.1f}%",
                f"{stats2.get('pass_accuracy', 85):.1f}%",
                f"{abs(stats1.get('pass_accuracy', 85) - stats2.get('pass_accuracy', 85)):.1f}%",
                "稳定" if stats1.get("pass_accuracy", 85) > 80 else "需改进",
            ],
        ]

        table = Table(comparison_data, colWidths=[35 * mm, 35 * mm, 35 * mm, 30 * mm, 30 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor(PRIMARY_COLOR)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("GRID", (0, 0), (-1, -1), 1, HexColor("#e2e8f0")),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 8 * mm))

        # 【Top 3 问题】
        story.append(Paragraph("【识别的战术问题（Top 3）】", styles["section_title"]))

        for i, problem in enumerate(problems_dict[:3], 1):
            severity_color = {5: CRITICAL_COLOR, 4: WARNING_COLOR, 3: "#fbbf24", 2: "#a3e635", 1: SUCCESS_COLOR}.get(
                problem.get("severity", 3), ACCENT_COLOR
            )
            story.append(
                Paragraph(
                    f'<font color="{severity_color}">●</font> '
                    f'<b>{i}. {problem["title"]}</b> (严重度: {problem["severity"]}/5)<br/>'
                    f'{problem["description"]}<br/>'
                    f'<font size="8">当前值: {problem["current"]:.2f} '
                    f'| 国际基准: {problem["benchmark"]:.2f} '
                    f'| 差异: {problem["variance_pct"]:.1f}%</font>',
                    styles["body_small"],
                )
            )
            story.append(Spacer(1, 4 * mm))

        return story, PageBreak()


class TrainingPlanPage:
    """第 2 页：训练计划"""

    @staticmethod
    def build(styles, training_plan):
        """生成训练计划页"""
        story = []

        # 标题
        story.append(Paragraph("【推荐训练计划】", styles["page_title"]))
        story.append(Spacer(1, 6 * mm))

        # 周训练日程
        story.append(Paragraph("周训练日程（基于问题优先度）", styles["section_title"]))

        schedule = training_plan.get("weekly_schedule", [])
        schedule_data = [["星期", "训练主题", "时长"]]
        for day_info in schedule:
            schedule_data.append([day_info["day"], day_info["focus"], f"{day_info['duration_min']}min"])

        table = Table(schedule_data, colWidths=[30 * mm, 100 * mm, 30 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor(PRIMARY_COLOR)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 1, HexColor("#e2e8f0")),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 8 * mm))

        # 关键训练模块
        story.append(Paragraph("关键训练模块（按优先度排序）", styles["section_title"]))

        for i, training in enumerate(training_plan.get("recommended_training", [])[:3], 1):
            problem = training["problem"]
            severity = training["severity"]
            modules = training["modules"]

            story.append(
                Paragraph(
                    f'<b>{i}. {problem}</b> (优先度: {severity}/5)<br/>'
                    f'推荐训练: {", ".join([m["name"] for m in modules[:2]])}',
                    styles["body_small"],
                )
            )

            # 子训练模块详情
            for module in modules[:1]:  # 只展示第一个模块的详情
                story.append(
                    Paragraph(
                        f'<b>• {module["name"]}</b> ({module["duration"]}min, {module["intensity"]}强度)<br/>'
                        f'要点: {"; ".join(module["coaching_points"][:2])}<br/>'
                        f'参考: {module["reference"]}',
                        styles["body_small"],
                    )
                )
            story.append(Spacer(1, 4 * mm))

        story.append(
            Paragraph(
                f'<b>周训练总时长：{training_plan.get("total_duration_min", 0)} 分钟</b>',
                styles["insight_text"],
            )
        )

        return story, PageBreak()


class LegendPage:
    """第 3 页：基础图例说明"""

    @staticmethod
    def build(styles):
        """生成图例说明页"""
        story = []

        story.append(Paragraph("【基础图例 & 指标说明】", styles["page_title"]))
        story.append(Spacer(1, 6 * mm))

        # 核心指标解释
        story.append(Paragraph("核心战术指标定义", styles["section_title"]))

        indicators = [
            ("xG (期望进球)", "预期进球数，综合考虑射门位置、角度、防守压力。>1.5 表示创造高质量机会。"),
            ("PPDA (进攻前传球数)", "对手完成一次传球前平均需要的传球次数。<10 表示前场压迫强度大。"),
            ("传球成功率", "成功传球数/总传球数。>85% 为国际水平。"),
            ("对抗成功率", "赢得对抗次数/总对抗次数。>50% 为优势。"),
            ("进攻三区传球", "传入禁区前 20m 区域的传球。体现进攻推进能力。"),
        ]

        for title, desc in indicators:
            story.append(Paragraph(f'<b>• {title}:</b> {desc}', styles["body_small"]))
            story.append(Spacer(1, 2 * mm))

        story.append(Spacer(1, 6 * mm))

        # 图表说明
        story.append(Paragraph("报告中的图表说明", styles["section_title"]))

        charts = [
            ("射门位置图", "绿点表示射门位置，大小代表 xG 值。位置越接近球门，质量越高。"),
            ("传球网络图", "球员之间的连线表示传球，线宽代表传球频率。体现球队的传球组织模式。"),
            ("热力图", "色深表示活动频率。进攻热力图显示进攻集中区域；防守热力图显示防守压力分布。"),
            ("雷达图", "多维度评估球队特点。越接近边缘表示该维度越强。"),
        ]

        for title, desc in charts:
            story.append(Paragraph(f'<b>• {title}:</b> {desc}', styles["body_small"]))
            story.append(Spacer(1, 2 * mm))

        return story, PageBreak()


# 导出函数
def build_redesigned_pages(df, info, stats1, stats2, team1, team2, problems, training_plan, styles):
    """构建重设计的报告前三页"""
    pages = []

    # 第 1 页：专业简介
    summary_content, _ = ExecutiveSummaryPage.build(styles, info, problems, stats1, stats2, team1, team2)
    pages.extend(summary_content)

    # 第 2 页：训练计划
    training_content, _ = TrainingPlanPage.build(styles, training_plan)
    pages.extend(training_content)

    # 第 3 页：图例说明
    legend_content, _ = LegendPage.build(styles)
    pages.extend(legend_content)

    return pages
