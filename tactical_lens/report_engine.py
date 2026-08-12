"""
report_engine.py — 报告引擎 v2
核心：模板驱动 + 训练建议映射
新增：training_recommendations section，每条洞察自动关联训练方案
"""
import json
import os
import datetime

# 导入训练映射（从stats_engine）
try:
    from stats_engine import get_training_plan, TRAINING_MAPPING
    _HAS_TRAINING = True
except ImportError:
    _HAS_TRAINING = False


# ========== 模板系统 ==========
class ReportTemplate:
    """报告模板：定义报告包含哪些部分、顺序、洞察规则"""
    
    def __init__(self, template_path=None):
        if template_path and os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        else:
            self.config = self.default_template()
    
    @staticmethod
    def default_template():
        """默认模板：完整比赛报告"""
        return {
            "name": "默认比赛报告",
            "sections": [
                {"id": "header", "type": "header", "title": "比赛分析报告"},
                {"id": "stats_table", "type": "stats_table"},
                {"id": "shot_map", "type": "chart", "chart_func": "draw_shot_map", "title": "射门位置图", "insight_type": "射门选择"},
                {"id": "pass_network", "type": "chart", "chart_func": "draw_pass_network", "title": "传球网络图", "insight_type": "传球质量"},
                {"id": "shot_comparison", "type": "chart", "chart_func": "draw_shot_comparison", "title": "射门对比", "insight_type": "进攻效率"},
                {"id": "xg_flow", "type": "chart", "chart_func": "draw_xg_flow", "title": "xG累积曲线", "insight_type": "比赛节奏"},
                {"id": "possession_timeline", "type": "chart", "chart_func": "draw_possession_timeline", "title": "控球时间线", "insight_type": "比赛节奏"},
                {"id": "insights", "type": "insights_block", "title": "战术洞察与建议"},
                {"id": "training_recs", "type": "training_recommendations", "title": "训练建议"},
                {"id": "footer", "type": "footer"},
            ],
            "insight_rules": {
                "xg_diff_threshold": 0.8,
                "possession_diff_threshold": 15,
                "pass_accuracy_diff_threshold": 8,
                "shot_on_target_high": 55,
                "shot_on_target_low": 30,
                "foul_diff_threshold": 5,
                "cross_accuracy_low": 25,
                "duel_success_low": 40,
                "big_chance_conversion_low": 40,
            }
        }
    
    @staticmethod
    def concise_template():
        """精简模板：核心图+洞察+训练"""
        return {
            "name": "精简战术报告",
            "sections": [
                {"id": "header", "type": "header", "title": "战术速报"},
                {"id": "stats_table", "type": "stats_table"},
                {"id": "shot_map", "type": "chart", "chart_func": "draw_shot_map", "title": "射门位置图"},
                {"id": "pass_network", "type": "chart", "chart_func": "draw_pass_network", "title": "传球网络图"},
                {"id": "insights", "type": "insights_block", "title": "战术洞察"},
                {"id": "training_recs", "type": "training_recommendations", "title": "训练重点"},
                {"id": "footer", "type": "footer"},
            ],
            "insight_rules": {
                "xg_diff_threshold": 1.0,
                "possession_diff_threshold": 20,
                "pass_accuracy_diff_threshold": 10,
            }
        }
    
    def save(self, path):
        """保存模板到JSON"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)


# ========== 报告生成 ==========
def generate_text_report(stats, insights, info, template=None):
    """生成文字版报告"""
    if template is None:
        template = ReportTemplate()
    
    lines = []
    teams = list(stats.keys())
    if len(teams) < 2:
        return "数据不足"
    
    t1, t2 = teams[0], teams[1]
    s1, s2 = stats[t1], stats[t2]
    
    for section in template.config['sections']:
        sec_type = section['type']
        
        if sec_type == 'header':
            lines.append(f"{'='*60}")
            lines.append(f"  {section.get('title', '比赛分析报告')}：{info['name']}")
            lines.append(f"{'='*60}")
        
        elif sec_type == 'stats_table':
            lines.append(f"\n{'指标':<16} {t1:<20} {t2:<20}")
            lines.append(f"{'-'*56}")
            rows = [
                ('阵型', s1['formation'], s2['formation']),
                ('控球率', f"{s1.get('possession_pct',0):.1f}%", f"{s2.get('possession_pct',0):.1f}%"),
                ('传球(成功)', f"{s1['passes_completed']}/{s1['passes_total']}", f"{s2['passes_completed']}/{s2['passes_total']}"),
                ('传球成功率', f"{s1['pass_accuracy']:.1f}%", f"{s2['pass_accuracy']:.1f}%"),
                ('射门(射正)', f"{s1['shots_on_target']}/{s1['shots_total']}", f"{s2['shots_on_target']}/{s2['shots_total']}"),
                ('进球', str(s1['goals']), str(s2['goals'])),
                ('xG', f"{s1['xg']:.2f}", f"{s2['xg']:.2f}"),
                ('大机会(进)', f"{s1.get('big_chances_taken',0)}({s1.get('big_chances_goals',0)})",
                 f"{s2.get('big_chances_taken',0)}({s2.get('big_chances_goals',0)})"),
                ('推进传球', str(s1.get('progressive_passes',0)), str(s2.get('progressive_passes',0))),
                ('传入禁区', str(s1.get('passes_into_box',0)), str(s2.get('passes_into_box',0))),
                ('传中成功率', f"{s1.get('cross_accuracy',0):.0f}%", f"{s2.get('cross_accuracy',0):.0f}%"),
                ('对抗成功率', f"{s1.get('duel_success_rate',0):.0f}%", f"{s2.get('duel_success_rate',0):.0f}%"),
                ('PPDA', f"{s1.get('ppda','N/A')}", f"{s2.get('ppda','N/A')}"),
                ('关键传球', str(s1['key_passes']), str(s2['key_passes'])),
                ('角球', str(s1['corners']), str(s2['corners'])),
                ('犯规', str(s1['fouls']), str(s2['fouls'])),
            ]
            for label, v1, v2 in rows:
                lines.append(f"{label:<16} {v1:<20} {v2:<20}")
        
        elif sec_type == 'chart':
            title = section.get('title', '')
            lines.append(f"\n--- {title} ---（见对应图片）")
        
        elif sec_type == 'insights_block':
            lines.append(f"\n{'='*60}")
            lines.append(f"  {section.get('title', '战术洞察')}")
            lines.append(f"{'='*60}")
            for ins in insights:
                cat = ins.get('category', '')
                text = ins.get('text', '')
                suggestion = ins.get('suggestion', '')
                lines.append(f"  · [{cat}] {text}")
                if suggestion:
                    lines.append(f"    → 建议：{suggestion}")
                # v2: 训练建议
                recs = ins.get('training_recommendations', [])
                if recs:
                    for rec in recs:
                        lines.append(f"    🏋️ 训练：{rec.get('name', '')}（{rec.get('scenario', '')} / {rec.get('zone', '')} / {rec.get('duration', '')}）")
                        lines.append(f"       重点：{rec.get('focus', '')}")

        elif sec_type == 'training_recommendations':
            # v2: 独立训练建议板块
            if _HAS_TRAINING:
                plan = get_training_plan(insights)
            else:
                plan = []
            if plan:
                lines.append(f"\n{'='*60}")
                lines.append(f"  🏋️ {section.get('title', '训练建议')}")
                lines.append(f"{'='*60}")
                lines.append(f"  基于本场比赛数据发现，建议以下训练重点：\n")
                for i, item in enumerate(plan, 1):
                    lines.append(f"  {i}. {item.get('name', '')} ({item.get('duration', '')})")
                    lines.append(f"     场景：{item.get('scenario', '')} | 区域：{item.get('zone', '')}")
                    lines.append(f"     重点：{item.get('focus', '')}")
                    lines.append(f"     触发：{item.get('triggered_by', '')}")
                    lines.append("")
        
        elif sec_type == 'footer':
            lines.append(f"\n{'='*60}")
            lines.append(f"  战术透镜 | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
            lines.append(f"  数据来源：{info.get('source', 'StatsBomb Open Data')}")
            lines.append(f"{'='*60}")
    
    return '\n'.join(lines)


def generate_html_report(stats, insights, info, chart_paths, template=None, output_path=None):
    """生成HTML网页版报告"""
    if template is None:
        template = ReportTemplate()
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None
    
    t1, t2 = teams[0], teams[1]
    s1, s2 = stats[t1], stats[t2]
    
    # 构建HTML
    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>战术透镜 — {info['name']}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Microsoft YaHei', sans-serif; background: #0d1117; color: #e6edf3; padding: 20px; }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ text-align: center; font-size: 28px; padding: 30px 0 10px; color: #00f5c4; }}
  h2 {{ font-size: 20px; margin: 30px 0 15px; border-left: 4px solid #00f5c4; padding-left: 12px; }}
  .score {{ text-align: center; font-size: 36px; font-weight: bold; padding: 15px 0; }}
  .stats-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
  .stats-table th, .stats-table td {{ padding: 10px 15px; text-align: center; border-bottom: 1px solid #21262d; }}
  .stats-table th {{ background: #161b22; color: #8b949e; }}
  .stats-table td:first-child {{ text-align: left; color: #8b949e; }}
  .stats-table td:nth-child(2) {{ color: #00f5c4; font-weight: bold; }}
  .stats-table td:nth-child(3) {{ color: #4da6ff; font-weight: bold; }}
  .insight {{ background: #161b22; border-radius: 8px; padding: 15px 20px; margin: 8px 0; border-left: 3px solid #f0883e; }}
  .insight .category {{ color: #f0883e; font-size: 12px; text-transform: uppercase; }}
  .insight .suggestion {{ color: #8b949e; font-size: 13px; margin-top: 5px; }}
  .chart-full img {{ width: 100%; border-radius: 8px; margin: 10px 0; }}
  .chart-row {{ display: flex; gap: 15px; margin: 15px 0; }}
  .chart-row img {{ flex: 1; min-width: 300px; border-radius: 8px; }}
  .footer {{ text-align: center; color: #484f58; padding: 30px 0; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <h1>⚽ 战术透镜</h1>
  <div class="score">
    <span style="color:#00f5c4">{t1} {s1['goals']}</span>
    <span style="color:#8b949e"> - </span>
    <span style="color:#4da6ff">{s2['goals']} {t2}</span>
  </div>
  <p style="text-align:center;color:#8b949e;margin-bottom:20px;">{info['name']}</p>
""")
    
    for section in template.config['sections']:
        sec_type = section['type']
        
        if sec_type == 'stats_table':
            html_parts.append('  <h2>📊 核心数据</h2>\n  <table class="stats-table">\n')
            html_parts.append(f'    <tr><th>指标</th><th>{t1}</th><th>{t2}</th></tr>\n')
            rows = [
                ('阵型', s1['formation'], s2['formation']),
                ('控球率', f"{s1.get('possession_pct',0):.1f}%", f"{s2.get('possession_pct',0):.1f}%"),
                ('传球成功率', f"{s1['pass_accuracy']:.1f}%", f"{s2['pass_accuracy']:.1f}%"),
                ('射门/射正', f"{s1['shots_total']}/{s1['shots_on_target']}", f"{s2['shots_total']}/{s2['shots_on_target']}"),
                ('xG', f"{s1['xg']:.2f}", f"{s2['xg']:.2f}"),
                ('大机会(进球)', f"{s1.get('big_chances_taken',0)}({s1.get('big_chances_goals',0)})",
                 f"{s2.get('big_chances_taken',0)}({s2.get('big_chances_goals',0)})"),
                ('推进传球', str(s1.get('progressive_passes',0)), str(s2.get('progressive_passes',0))),
                ('传入禁区', str(s1.get('passes_into_box',0)), str(s2.get('passes_into_box',0))),
                ('传中成功率', f"{s1.get('cross_accuracy',0):.0f}%", f"{s2.get('cross_accuracy',0):.0f}%"),
                ('对抗成功率', f"{s1.get('duel_success_rate',0):.0f}%", f"{s2.get('duel_success_rate',0):.0f}%"),
                ('PPDA', f"{s1.get('ppda','N/A')}", f"{s2.get('ppda','N/A')}"),
                ('关键传球', str(s1['key_passes']), str(s2['key_passes'])),
                ('角球', str(s1['corners']), str(s2['corners'])),
                ('犯规', str(s1['fouls']), str(s2['fouls'])),
            ]
            for label, v1, v2 in rows:
                html_parts.append(f'    <tr><td>{label}</td><td>{v1}</td><td>{v2}</td></tr>\n')
            html_parts.append('  </table>\n')
        
        elif sec_type == 'chart':
            chart_id = section.get('id', '')
            img_path = chart_paths.get(chart_id, '')
            title = section.get('title', '')
            if img_path:
                # HTML和图片在同一目录，只用文件名
                img_filename = os.path.basename(img_path)
                html_parts.append(f'  <h2>📈 {title}</h2>\n  <div class="chart-full"><img src="{img_filename}" alt="{title}"></div>\n')
        
        elif sec_type == 'insights_block':
            html_parts.append(f'  <h2>🔍 {section.get("title", "战术洞察")}</h2>\n')
            for ins in insights:
                cat = ins.get('category', '')
                text = ins.get('text', '')
                suggestion = ins.get('suggestion', '')
                recs = ins.get('training_recommendations', [])
                html_parts.append(f'  <div class="insight">\n    <div class="category">{cat}</div>\n    <div>{text}</div>\n')
                if suggestion:
                    html_parts.append(f'    <div class="suggestion">→ {suggestion}</div>\n')
                if recs:
                    html_parts.append(f'    <div class="training-recs" style="margin-top:8px;padding:8px;background:#1c2128;border-radius:4px;">\n')
                    html_parts.append(f'      <div style="color:#00f5c4;font-size:12px;font-weight:bold;">🏋️ 推荐训练</div>\n')
                    for rec in recs:
                        html_parts.append(f'      <div style="color:#c9d1d9;font-size:13px;margin:2px 0;">• {rec.get("name","")}（{rec.get("scenario","")} / {rec.get("zone","")} / {rec.get("duration","")}）<span style="color:#8b949e">— {rec.get("focus","")}</span></div>\n')
                    html_parts.append(f'    </div>\n')
                html_parts.append('  </div>\n')

        elif sec_type == 'training_recommendations':
            # v2: 独立训练建议板块（HTML）
            if _HAS_TRAINING:
                plan = get_training_plan(insights)
            else:
                plan = []
            if plan:
                html_parts.append(f'  <h2>🏋️ {section.get("title", "训练建议")}</h2>\n')
                html_parts.append(f'  <div style="background:#161b22;border-radius:8px;padding:20px;margin:10px 0;">\n')
                html_parts.append(f'    <p style="color:#8b949e;margin-bottom:15px;">基于本场比赛数据发现，建议以下训练重点：</p>\n')
                for i, item in enumerate(plan, 1):
                    html_parts.append(f'    <div style="margin:10px 0;padding:12px;background:#0d1117;border-radius:6px;border-left:3px solid #00f5c4;">\n')
                    html_parts.append(f'      <div style="color:#00f5c4;font-weight:bold;font-size:15px;">{i}. {item.get("name","")} <span style="color:#8b949e;font-weight:normal;">（{item.get("duration","")}）</span></div>\n')
                    html_parts.append(f'      <div style="color:#c9d1d9;margin:4px 0;">场景：{item.get("scenario","")} | 区域：{item.get("zone","")}</div>\n')
                    html_parts.append(f'      <div style="color:#c9d1d9;">重点：{item.get("focus","")}</div>\n')
                    html_parts.append(f'      <div style="color:#8b949e;font-size:12px;margin-top:4px;">数据触发：{item.get("triggered_by","")}</div>\n')
                    html_parts.append(f'    </div>\n')
                html_parts.append(f'  </div>\n')
        
        elif sec_type == 'footer':
            html_parts.append(f"""
  <div class="footer">
    战术透镜 v4 | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据来源：{info.get('source', 'StatsBomb')}
  </div>
""")
    
    html_parts.append('</div>\n</body>\n</html>')
    
    html = ''.join(html_parts)
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"[报告生成] HTML → {output_path}")
    
    return html
