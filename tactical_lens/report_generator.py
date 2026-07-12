"""
report_generator.py — PDF战术报告生成器
功能：基于FIFA比赛数据生成完整的A4 PDF战术分析报告（7页）

依赖：reportlab（纯Python，Streamlit Cloud可直接安装）
中文字体：项目fonts/目录下 NotoSansSC-Regular.otf

报告结构：
  第1页 - 封面（标题、对阵、比分、日期、战术透镜标识）
  第2页 - 核心数据对比（表格 + 对比条形图）
  第3页 - 进攻端分析（射门位置图、防线穿透、传中战术、关键球员）
  第4页 - 防守端分析（防守热力图、防守数据、防线漏洞、防守关键球员）
  第5页 - 战术风格画像（雷达图 + 文字总结）
  第6页 - 体能与传球（体能五分区、传球网络、组织核心）
  第7页 - 战术洞察总结（进攻洞察、防守洞察、整体总结）

特性：
  - 数据缺失时对应板块自动跳过，不影响整体报告
  - 图表300dpi嵌入，打印级清晰度
  - 页码放在页脚
  - 深色风格与网页版一致
"""

import os
import sys
import tempfile
import io

# ===== reportlab 导入 =====
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, Image, PageBreak, KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ===== 颜色定义（与visualizer深色主题呼应，但PDF用浅色背景更适合打印） =====
BG_COLOR = '#f8f9fa'          # PDF背景：米白色（打印友好）
CARD_BG = '#ffffff'           # 卡片背景
PRIMARY_COLOR = '#1a365d'     # 主色：深蓝（标题）
ACCENT_COLOR = '#2563eb'      # 强调色：蓝色
TEAM1_COLOR = '#0d9488'       # 主队：青绿色
TEAM2_COLOR = '#2563eb'       # 客队：蓝色
SUBTEXT_COLOR = '#64748b'     # 辅助文字：灰蓝
BORDER_COLOR = '#e2e8f0'      # 边框色
HIGHLIGHT_BG = '#f0fdf4'      # 高亮背景
WARNING_BG = '#fef3c7'        # 警告背景

# ===== 全局字体名 =====
FONT_CN = 'NotoSansSC'
FONT_CN_BOLD = 'NotoSansSC-Bold'  # 备用，实际用同字体+加粗模拟

_font_registered = False


def _register_chinese_font():
    """注册中文字体，优先使用项目自带字体，降级使用系统字体"""
    global _font_registered, FONT_CN
    if _font_registered:
        return True
    
    # 查找项目fonts目录
    project_dir = os.path.dirname(os.path.abspath(__file__))
    font_dirs = [
        os.path.join(project_dir, 'fonts'),
        os.path.join(os.getcwd(), 'fonts'),
    ]
    
    font_candidates = [
        'NotoSansSC-Regular.otf',
        'NotoSansSC-Bold.otf',
        'NotoSansCJKsc-Regular.otf',
        'NotoSansSC-Regular.ttf',
    ]
    
    # 尝试注册常规字体
    for font_dir in font_dirs:
        if not os.path.isdir(font_dir):
            continue
        for fname in font_candidates:
            fpath = os.path.join(font_dir, fname)
            if os.path.exists(fpath):
                try:
                    pdfmetrics.registerFont(TTFont(FONT_CN, fpath))
                    _font_registered = True
                    print(f"[PDF生成器] 注册中文字体: {fpath}")
                    return True
                except Exception as e:
                    print(f"[PDF生成器] 字体注册失败 {fpath}: {e}")
    
    # 降级：尝试CID字体（reportlab内置的中文支持）
    try:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        FONT_CN = 'STSong-Light'
        _font_registered = True
        print("[PDF生成器] 使用内置中文CID字体 STSong-Light")
        return True
    except Exception as e:
        print(f"[PDF生成器] CID字体也不可用: {e}")
    
    # 最终降级：Helvetica（中文可能显示异常）
    FONT_CN = 'Helvetica'
    _font_registered = True
    print("[PDF生成器] 警告：无可用中文字体，使用Helvetica，中文可能无法正常显示")
    return False


def _get_styles():
    """获取所有段落样式"""
    _register_chinese_font()
    styles = {}
    
    styles['title_main'] = ParagraphStyle(
        'title_main', fontName=FONT_CN, fontSize=28, leading=36,
        textColor=HexColor(PRIMARY_COLOR), alignment=TA_CENTER,
        spaceAfter=10,
    )
    styles['title_sub'] = ParagraphStyle(
        'title_sub', fontName=FONT_CN, fontSize=16, leading=22,
        textColor=HexColor(SUBTEXT_COLOR), alignment=TA_CENTER,
        spaceAfter=6,
    )
    styles['score'] = ParagraphStyle(
        'score', fontName=FONT_CN, fontSize=36, leading=44,
        textColor=HexColor(PRIMARY_COLOR), alignment=TA_CENTER,
        spaceAfter=5,
    )
    styles['team_name'] = ParagraphStyle(
        'team_name', fontName=FONT_CN, fontSize=18, leading=24,
        textColor=HexColor(PRIMARY_COLOR), alignment=TA_CENTER,
    )
    styles['page_title'] = ParagraphStyle(
        'page_title', fontName=FONT_CN, fontSize=20, leading=28,
        textColor=HexColor(PRIMARY_COLOR), alignment=TA_LEFT,
        spaceAfter=14, spaceBefore=0,
    )
    styles['section_title'] = ParagraphStyle(
        'section_title', fontName=FONT_CN, fontSize=14, leading=20,
        textColor=HexColor(PRIMARY_COLOR), alignment=TA_LEFT,
        spaceAfter=8, spaceBefore=12,
    )
    styles['sub_section'] = ParagraphStyle(
        'sub_section', fontName=FONT_CN, fontSize=11, leading=16,
        textColor=HexColor(ACCENT_COLOR), alignment=TA_LEFT,
        spaceAfter=4, spaceBefore=6,
    )
    styles['body'] = ParagraphStyle(
        'body', fontName=FONT_CN, fontSize=10, leading=15,
        textColor=HexColor('#334155'), alignment=TA_JUSTIFY,
        spaceAfter=4,
    )
    styles['body_small'] = ParagraphStyle(
        'body_small', fontName=FONT_CN, fontSize=9, leading=13,
        textColor=HexColor(SUBTEXT_COLOR), alignment=TA_LEFT,
        spaceAfter=2,
    )
    styles['insight_text'] = ParagraphStyle(
        'insight_text', fontName=FONT_CN, fontSize=10, leading=15,
        textColor=HexColor('#1e293b'), alignment=TA_JUSTIFY,
        spaceAfter=3, leftIndent=8,
    )
    styles['insight_cat'] = ParagraphStyle(
        'insight_cat', fontName=FONT_CN, fontSize=9, leading=13,
        textColor=HexColor(ACCENT_COLOR), alignment=TA_LEFT,
        spaceAfter=1, leftIndent=8,
    )
    styles['footer'] = ParagraphStyle(
        'footer', fontName=FONT_CN, fontSize=8, leading=10,
        textColor=HexColor(SUBTEXT_COLOR), alignment=TA_CENTER,
    )
    styles['table_header'] = ParagraphStyle(
        'table_header', fontName=FONT_CN, fontSize=10, leading=14,
        textColor=white, alignment=TA_CENTER,
    )
    styles['table_cell'] = ParagraphStyle(
        'table_cell', fontName=FONT_CN, fontSize=9.5, leading=13,
        textColor=HexColor('#334155'), alignment=TA_CENTER,
    )
    styles['table_cell_left'] = ParagraphStyle(
        'table_cell_left', fontName=FONT_CN, fontSize=9.5, leading=13,
        textColor=HexColor('#334155'), alignment=TA_LEFT,
    )
    styles['player_rank'] = ParagraphStyle(
        'player_rank', fontName=FONT_CN, fontSize=9.5, leading=14,
        textColor=HexColor('#334155'), alignment=TA_LEFT,
        spaceAfter=2,
    )
    
    return styles


# ===== 页面装饰（页眉页脚） =====

def _page_decorator(canvas, doc):
    """每页的页眉页脚装饰"""
    canvas.saveState()
    
    page_w, page_h = A4
    margin = 15 * mm
    
    # ---- 页眉：细分隔线 + 标题 ----
    if doc.page > 1:  # 封面不画页眉
        canvas.setStrokeColor(HexColor(BORDER_COLOR))
        canvas.setLineWidth(0.5)
        canvas.line(margin, page_h - 18*mm, page_w - margin, page_h - 18*mm)
        
        canvas.setFont(FONT_CN, 9)
        canvas.setFillColor(HexColor(SUBTEXT_COLOR))
        canvas.drawString(margin, page_h - 16*mm, "战术透镜 · 比赛战术分析报告")
        canvas.drawRightString(page_w - margin, page_h - 16*mm, "Tactical Lens")
    
    # ---- 页脚：页码 + 底部线 ----
    canvas.setStrokeColor(HexColor(BORDER_COLOR))
    canvas.setLineWidth(0.5)
    canvas.line(margin, 12*mm, page_w - margin, 12*mm)
    
    canvas.setFont(FONT_CN, 8)
    canvas.setFillColor(HexColor(SUBTEXT_COLOR))
    canvas.drawCentredString(page_w / 2, 8*mm, f"第 {doc.page} 页")
    canvas.drawString(margin, 8*mm, "■ 战术透镜")
    canvas.drawRightString(page_w - margin, 8*mm, "tactical-lens.app")
    
    canvas.restoreState()


# ===== PDF报告生成器主类 =====

class TacticalReportGenerator:
    """战术报告PDF生成器
    
    使用方式：
        gen = TacticalReportGenerator(df, info, stats, output_path)
        gen.generate()
    """
    
    def __init__(self, df, info, stats, output_path, chart_dir=None):
        """
        参数:
            df: 事件数据DataFrame（来自fifa_adapter.load_fifa_from_csv）
            info: 比赛信息字典
            stats: 球队统计字典 {team_name: {stat_name: value}}
            output_path: PDF输出文件路径
            chart_dir: 高清图表目录，None则自动生成
        """
        self.df = df
        self.info = info
        self.stats = stats
        self.output_path = output_path
        
        # 球队
        teams = list(stats.keys())
        self.team1 = teams[0] if len(teams) > 0 else "主队"
        self.team2 = teams[1] if len(teams) > 1 else "客队"
        self.s1 = stats.get(self.team1, {})
        self.s2 = stats.get(self.team2, {})
        
        # 比赛信息
        self.match_name = info.get('match_name', '比赛') if info else '比赛'
        self.competition = info.get('competition', '') if info else ''
        self.match_date = info.get('match_date', '') if info else ''
        self.stadium = info.get('stadium', '') if info else ''
        
        # FIFA扩展数据
        self.fifa_extra = info.get('fifa_extra', {}) if info else {}
        self.is_fifa = info and info.get('source') == 'fifa'
        
        # 样式
        self.styles = _get_styles()
        
        # 图表目录
        self._chart_dir = chart_dir
        self._chart_paths = {}
        self._temp_dir = None
    
    def _ensure_charts(self):
        """确保高清图表已生成"""
        if self._chart_paths:
            return
        
        if self._chart_dir and os.path.isdir(self._chart_dir):
            # 使用已有图表目录
            for fname in os.listdir(self._chart_dir):
                if fname.endswith('.png'):
                    chart_id = fname.rsplit('.', 1)[0]
                    self._chart_paths[chart_id] = os.path.join(self._chart_dir, fname)
            if self._chart_paths:
                print(f"[PDF生成器] 使用已有图表: {len(self._chart_paths)}张 → {self._chart_dir}")
                return
        
        # 自动生成高清图表
        print("[PDF生成器] 正在生成高清图表（300dpi）...")
        self._temp_dir = tempfile.mkdtemp(prefix='tactical_pdf_charts_')
        
        # 延迟导入避免循环依赖
        from visualizer import generate_charts_for_pdf
        self._chart_paths = generate_charts_for_pdf(
            self.df, self.info, self.stats,
            output_dir=self._temp_dir, dpi=300
        )
    
    def _has_chart(self, chart_id):
        """检查某张图表是否可用"""
        return chart_id in self._chart_paths and os.path.exists(self._chart_paths[chart_id])
    
    def _chart_image(self, chart_id, max_width=None, max_height=None):
        """创建一个Image flowable，自动缩放以适应页面"""
        if not self._has_chart(chart_id):
            return None
        
        from reportlab.lib.utils import ImageReader
        img_path = self._chart_paths[chart_id]
        
        # 读取图片获取原始尺寸
        try:
            img = ImageReader(img_path)
            iw, ih = img.getSize()
        except Exception:
            return None
        
        # 默认最大宽度
        if max_width is None:
            max_width = 170 * mm
        if max_height is None:
            max_height = 120 * mm
        
        # 计算缩放比例
        scale = min(max_width / iw, max_height / ih)
        w = iw * scale
        h = ih * scale
        
        return Image(img_path, width=w, height=h)
    
    # ========== 第1页：封面 ==========
    
    def _build_cover(self, story):
        """构建封面页"""
        s = self.styles
        
        # 上方留白
        story.append(Spacer(1, 25*mm))
        
        # Logo / 标识
        logo_text = Paragraph("■", ParagraphStyle(
            'logo', fontName=FONT_CN, fontSize=48, alignment=TA_CENTER,
            textColor=HexColor(ACCENT_COLOR), spaceAfter=5,
        ))
        story.append(logo_text)
        
        # 主标题
        story.append(Paragraph("比赛战术分析报告", s['title_main']))
        
        # 副标题
        story.append(Paragraph("TACTICAL MATCH ANALYSIS", s['title_sub']))
        
        story.append(Spacer(1, 15*mm))
        
        # 对阵双方 + 比分
        score_text = f"{self.s1.get('goals', 0)}  —  {self.s2.get('goals', 0)}"
        story.append(Paragraph(score_text, s['score']))
        
        # 两队名称
        team_table_data = [[
            Paragraph(self.team1, ParagraphStyle(
                't1', fontName=FONT_CN, fontSize=18, leading=24,
                textColor=HexColor(TEAM1_COLOR), alignment=TA_RIGHT,
            )),
            Paragraph("VS", ParagraphStyle(
                'vs', fontName=FONT_CN, fontSize=14, leading=24,
                textColor=HexColor(SUBTEXT_COLOR), alignment=TA_CENTER,
            )),
            Paragraph(self.team2, ParagraphStyle(
                't2', fontName=FONT_CN, fontSize=18, leading=24,
                textColor=HexColor(TEAM2_COLOR), alignment=TA_LEFT,
            )),
        ]]
        team_table = Table(team_table_data, colWidths=[65*mm, 20*mm, 65*mm])
        team_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(team_table)
        
        story.append(Spacer(1, 10*mm))
        
        # 比赛信息
        info_lines = []
        if self.competition:
            info_lines.append(f"赛事：{self.competition}")
        if self.match_date:
            info_lines.append(f"日期：{self.match_date}")
        if self.stadium:
            info_lines.append(f"球场：{self.stadium}")
        info_lines.append(f"数据来源：FIFA 比赛报告")
        
        for line in info_lines:
            story.append(Paragraph(line, ParagraphStyle(
                'info_line', fontName=FONT_CN, fontSize=11, leading=18,
                textColor=HexColor(SUBTEXT_COLOR), alignment=TA_CENTER,
                spaceAfter=2,
            )))
        
        # 底部标识
        story.append(Spacer(1, 25*mm))
        story.append(Paragraph("战术透镜 · Tactical Lens", ParagraphStyle(
            'footer_brand', fontName=FONT_CN, fontSize=10, leading=14,
            textColor=HexColor(ACCENT_COLOR), alignment=TA_CENTER,
        )))
        story.append(Paragraph("用数据读懂足球", ParagraphStyle(
            'slogan', fontName=FONT_CN, fontSize=9, leading=12,
            textColor=HexColor(SUBTEXT_COLOR), alignment=TA_CENTER,
        )))
        
        story.append(PageBreak())
    
    # ========== 第2页：核心数据对比 ==========
    
    def _build_core_stats(self, story):
        """构建核心数据对比页"""
        s = self.styles
        
        story.append(Paragraph("一、核心数据对比", s['page_title']))
        
        # 核心数据表格
        story.append(Paragraph("1.1 关键数据一览", s['section_title']))
        
        # 表格数据
        stat_items = [
            ('阵型', 'formation', 'str'),
            ('控球率', 'possession_pct', 'pct'),
            ('传球成功率', 'pass_accuracy', 'pct'),
            ('射门总数', 'shots_total', 'int'),
            ('射正数', 'shots_on_target', 'int'),
            ('进球数', 'goals', 'int'),
            ('预期进球(xG)', 'xg', 'xg'),
            ('关键传球', 'key_passes', 'int'),
            ('角球', 'corners', 'int'),
            ('犯规', 'fouls', 'int'),
            ('越位', 'offsides', 'int_na'),
        ]
        
        table_data = [[
            Paragraph("指标", s['table_header']),
            Paragraph(self.team1, s['table_header']),
            Paragraph(self.team2, s['table_header']),
        ]]
        
        for label, key, fmt in stat_items:
            v1 = self.s1.get(key, '-')
            v2 = self.s2.get(key, '-')
            
            if fmt == 'pct':
                v1 = f"{v1:.1f}%" if isinstance(v1, (int, float)) else '-'
                v2 = f"{v2:.1f}%" if isinstance(v2, (int, float)) else '-'
            elif fmt == 'xg':
                v1 = f"{v1:.2f}" if isinstance(v1, (int, float)) else '-'
                v2 = f"{v2:.2f}" if isinstance(v2, (int, float)) else '-'
            elif fmt == 'int':
                v1 = str(int(v1)) if isinstance(v1, (int, float)) else str(v1)
                v2 = str(int(v2)) if isinstance(v2, (int, float)) else str(v2)
            elif fmt == 'int_na':
                # 越位FIFA数据可能没有
                v1 = str(int(v1)) if isinstance(v1, (int, float)) and v1 > 0 else '-'
                v2 = str(int(v2)) if isinstance(v2, (int, float)) and v2 > 0 else '-'
            else:
                v1 = str(v1) if v1 else '-'
                v2 = str(v2) if v2 else '-'
            
            table_data.append([
                Paragraph(label, s['table_cell_left']),
                Paragraph(str(v1), s['table_cell']),
                Paragraph(str(v2), s['table_cell']),
            ])
        
        stats_table = Table(table_data, colWidths=[50*mm, 50*mm, 50*mm])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor(PRIMARY_COLOR)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#f8fafc'), HexColor('#ffffff')]),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            # 主队列
            ('BACKGROUND', (1, 0), (1, 0), HexColor(TEAM1_COLOR)),
            # 客队列
            ('BACKGROUND', (2, 0), (2, 0), HexColor(TEAM2_COLOR)),
        ]))
        story.append(stats_table)
        
        story.append(Spacer(1, 5*mm))
        
        # 数据可视化：核心数据对比条形图
        if self._has_chart('stats_bar'):
            story.append(Paragraph("1.2 数据可视化对比", s['section_title']))
            img = self._chart_image('stats_bar', max_width=170*mm, max_height=75*mm)
            if img:
                # 居中
                img_table = Table([[img]], colWidths=[170*mm])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BOX', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#0d1117')),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ]))
                story.append(img_table)
        
        # 数据说明
        story.append(Spacer(1, 4*mm))
        note = "注：FIFA比赛报告数据为聚合统计数据；犯规、越位等部分指标为估算值，仅供参考。"
        if self.fifa_extra.get('fouls_estimated'):
            note = "注：FIFA比赛报告数据为聚合统计数据；犯规、越位等指标为估算值，关键传球以防线突破传球近似。"
        story.append(Paragraph(note, s['body_small']))
        
        story.append(PageBreak())
    
    # ========== 第3页：进攻端分析 ==========
    
    def _build_attack_analysis(self, story):
        """构建进攻端分析页"""
        s = self.styles
        
        story.append(Paragraph("二、进攻端分析", s['page_title']))
        
        # 射门位置图
        if self._has_chart('shot_map'):
            story.append(Paragraph("2.1 射门位置分布", s['section_title']))
            img = self._chart_image('shot_map', max_width=170*mm, max_height=85*mm)
            if img:
                img_table = Table([[img]], colWidths=[170*mm])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BOX', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#0d1117')),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(img_table)
        
        # 防线穿透分析
        lb_data = self.fifa_extra.get('line_breaks', {})
        if self._has_chart('line_breaks') and lb_data:
            story.append(Paragraph("2.2 防线穿透分析", s['section_title']))
            img = self._chart_image('line_breaks', max_width=170*mm, max_height=70*mm)
            if img:
                img_table = Table([[img]], colWidths=[170*mm])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BOX', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#0d1117')),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                story.append(img_table)
        elif lb_data:
            # 没有图表但有数据，用文字展示
            story.append(Paragraph("2.2 防线穿透分析", s['section_title']))
            for team in [self.team1, self.team2]:
                if team in lb_data:
                    d = lb_data[team]
                    story.append(Paragraph(
                        f"<b>{team}</b>：{d['attempts']}次尝试突破，成功{d['completed']}次，"
                        f"成功率{d['success_rate']:.1f}%，转化{d['goals']}球",
                        s['body']
                    ))
        
        # 传中战术分析
        cross_data = self.fifa_extra.get('cross_tactics', {})
        if self._has_chart('cross_tactics') and cross_data:
            story.append(Paragraph("2.3 传中战术分析", s['section_title']))
            img = self._chart_image('cross_tactics', max_width=170*mm, max_height=65*mm)
            if img:
                img_table = Table([[img]], colWidths=[170*mm])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BOX', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#0d1117')),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                story.append(img_table)
        
        # 进攻端关键球员
        story.append(Paragraph("2.4 进攻端关键球员 TOP3", s['section_title']))
        
        attack_players_data = self._get_attack_players()
        if attack_players_data[self.team1] or attack_players_data[self.team2]:
            player_table_data = [[
                Paragraph("排名", s['table_header']),
                Paragraph(self.team1, s['table_header']),
                Paragraph(self.team2, s['table_header']),
            ]]
            
            for i in range(3):
                row = [Paragraph(f"第{i+1}名", s['table_cell'])]
                for team in [self.team1, self.team2]:
                    players = attack_players_data[team]
                    if i < len(players):
                        p = players[i]
                        name = p.get('name', '-')
                        desc = p.get('desc', '')
                        row.append(Paragraph(
                            f"<b>{name}</b><br/><font size=8 color='{SUBTEXT_COLOR}'>{desc}</font>",
                            s['table_cell_left']
                        ))
                    else:
                        row.append(Paragraph("-", s['table_cell']))
                player_table_data.append(row)
            
            player_table = Table(player_table_data, colWidths=[25*mm, 72.5*mm, 72.5*mm])
            # 设置表头颜色
            header_style = [
                ('BACKGROUND', (0, 0), (0, 0), HexColor(PRIMARY_COLOR)),
                ('BACKGROUND', (1, 0), (1, 0), HexColor(TEAM1_COLOR)),
                ('BACKGROUND', (2, 0), (2, 0), HexColor(TEAM2_COLOR)),
            ]
            player_table.setStyle(TableStyle([
                *header_style,
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#f8fafc'), HexColor('#ffffff')]),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(player_table)
        
        story.append(PageBreak())
    
    def _get_attack_players(self):
        """获取进攻端关键球员数据（综合射门+突破+xG）"""
        result = {self.team1: [], self.team2: []}
        
        for team in [self.team1, self.team2]:
            players = {}
            
            # 射门领先者
            shot_leaders = self.stats[team].get('shot_leaders', {})
            if hasattr(shot_leaders, 'items'):
                for name, cnt in shot_leaders.items():
                    if name not in players:
                        players[name] = {'name': name, 'shots': 0, 'xg': 0, 'breaks': 0}
                    players[name]['shots'] = cnt
            
            # xG领先者
            xg_leaders = self.stats[team].get('xg_leaders', {})
            if hasattr(xg_leaders, 'items'):
                for name, val in xg_leaders.items():
                    if name not in players:
                        players[name] = {'name': name, 'shots': 0, 'xg': 0, 'breaks': 0}
                    players[name]['xg'] = val
            
            # 防线穿透TOP球员
            lb_data = self.fifa_extra.get('line_breaks', {})
            if team in lb_data:
                for p in lb_data[team].get('top_players', []):
                    name = p.get('name', '')
                    if name not in players:
                        players[name] = {'name': name, 'shots': 0, 'xg': 0, 'breaks': 0}
                    players[name]['breaks'] = p.get('completed', 0)
            
            # 计算综合评分
            player_list = list(players.values())
            player_list.sort(
                key=lambda p: p['shots'] * 2 + p['xg'] * 5 + p['breaks'] * 1.5,
                reverse=True
            )
            
            # 取TOP3，生成描述
            top3 = []
            for p in player_list[:3]:
                desc_parts = []
                if p['shots'] > 0:
                    desc_parts.append(f"{int(p['shots'])}次射门")
                if p['xg'] > 0:
                    desc_parts.append(f"xG {p['xg']:.2f}")
                if p['breaks'] > 0:
                    desc_parts.append(f"{p['breaks']}次突破")
                top3.append({
                    'name': p['name'],
                    'desc': ' | '.join(desc_parts) if desc_parts else '进攻核心',
                })
            result[team] = top3
        
        return result
    
    # ========== 第4页：防守端分析 ==========
    
    def _build_defense_analysis(self, story):
        """构建防守端分析页"""
        s = self.styles
        
        story.append(Paragraph("三、防守端分析", s['page_title']))
        
        # 防守热力图
        if self._has_chart('pressure_heatmap'):
            story.append(Paragraph("3.1 防守热力图", s['section_title']))
            img = self._chart_image('pressure_heatmap', max_width=170*mm, max_height=85*mm)
            if img:
                img_table = Table([[img]], colWidths=[170*mm])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BOX', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#0d1117')),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(img_table)
        
        # 防守数据统计
        story.append(Paragraph("3.2 防守数据统计", s['section_title']))
        
        def_stats = self._get_defense_stats()
        if def_stats:
            table_data = [[
                Paragraph("防守指标", s['table_header']),
                Paragraph(self.team1, s['table_header']),
                Paragraph(self.team2, s['table_header']),
            ]]
            
            for label, key in def_stats:
                v1 = self.s1.get(key, '-')
                v2 = self.s2.get(key, '-')
                if isinstance(v1, (int, float)):
                    v1 = str(int(v1)) if v1 == int(v1) else f"{v1:.1f}"
                if isinstance(v2, (int, float)):
                    v2 = str(int(v2)) if v2 == int(v2) else f"{v2:.1f}"
                
                table_data.append([
                    Paragraph(label, s['table_cell_left']),
                    Paragraph(str(v1), s['table_cell']),
                    Paragraph(str(v2), s['table_cell']),
                ])
            
            def_table = Table(table_data, colWidths=[60*mm, 45*mm, 45*mm])
            def_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, 0), HexColor(PRIMARY_COLOR)),
                ('BACKGROUND', (1, 0), (1, 0), HexColor(TEAM1_COLOR)),
                ('BACKGROUND', (2, 0), (2, 0), HexColor(TEAM2_COLOR)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#f8fafc'), HexColor('#ffffff')]),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(def_table)
        
        # 防线漏洞分析
        story.append(Paragraph("3.3 防线漏洞分析", s['section_title']))
        
        weakness_items = self._get_defense_weakness()
        if weakness_items:
            for item in weakness_items:
                story.append(Paragraph(f"[!] {item}", s['body']))
        else:
            story.append(Paragraph("暂无明显防线漏洞数据。", s['body']))
        
        # 防守端关键球员
        story.append(Paragraph("3.4 防守端关键球员", s['section_title']))
        
        def_players = self._get_defense_players()
        if def_players[self.team1] or def_players[self.team2]:
            player_table_data = [[
                Paragraph("排名", s['table_header']),
                Paragraph(self.team1, s['table_header']),
                Paragraph(self.team2, s['table_header']),
            ]]
            
            for i in range(3):
                row = [Paragraph(f"第{i+1}名", s['table_cell'])]
                for team in [self.team1, self.team2]:
                    players = def_players[team]
                    if i < len(players):
                        p = players[i]
                        row.append(Paragraph(
                            f"<b>{p['name']}</b><br/><font size=8 color='{SUBTEXT_COLOR}'>{p['desc']}</font>",
                            s['table_cell_left']
                        ))
                    else:
                        row.append(Paragraph("-", s['table_cell']))
                player_table_data.append(row)
            
            player_table = Table(player_table_data, colWidths=[25*mm, 72.5*mm, 72.5*mm])
            player_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, 0), HexColor(PRIMARY_COLOR)),
                ('BACKGROUND', (1, 0), (1, 0), HexColor(TEAM1_COLOR)),
                ('BACKGROUND', (2, 0), (2, 0), HexColor(TEAM2_COLOR)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#f8fafc'), HexColor('#ffffff')]),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(player_table)
        
        story.append(PageBreak())
    
    def _get_defense_stats(self):
        """获取防守相关统计项列表"""
        items = [
            ('抢断', 'tackles'),
            ('拦截', 'interceptions'),
            ('封堵', 'blocks'),
            ('解围', 'clearances'),
            ('犯规', 'fouls'),
            ('被射门次数', 'shots_against'),
        ]
        # 过滤掉没有的数据
        available = []
        for label, key in items:
            v1 = self.s1.get(key)
            v2 = self.s2.get(key)
            if v1 is not None or v2 is not None:
                available.append((label, key))
        return available
    
    def _get_defense_weakness(self):
        """分析防线漏洞"""
        weaknesses = []
        
        opp_team1 = self.team2  # team1的对手是team2
        opp_team2 = self.team1
        
        # 从对手进攻数据看本方防线漏洞
        for team, opp in [(self.team1, opp_team1), (self.team2, opp_team2)]:
            opp_s = self.stats.get(opp, {})
            opp_xg = opp_s.get('xg', 0)
            opp_shots = opp_s.get('shots_total', 0)
            opp_sot = opp_s.get('shots_on_target', 0)
            
            issues = []
            if opp_xg > 1.5:
                issues.append(f"被创造{xg:.1f}xG的得分机会".replace('{xg}', f'{opp_xg}'))
            if opp_shots > 12:
                issues.append(f"被射门{opp_shots}次，防守压力较大")
            
            # 防线穿透
            lb_data = self.fifa_extra.get('line_breaks', {})
            if opp in lb_data and lb_data[opp].get('completed', 0) > 5:
                d = lb_data[opp]
                issues.append(f"中路被穿透{d['completed']}次（成功率{d['success_rate']:.0f}%）")
            
            # 传中
            cross_data = self.fifa_extra.get('cross_tactics', {})
            if opp in cross_data and cross_data[opp].get('success_rate', 0) > 25:
                d = cross_data[opp]
                issues.append(f"边路传中成功率达{d['success_rate']:.0f}%，边路防守存在隐患")
            
            if issues:
                weaknesses.append(f"<b>{team}</b>：{'；'.join(issues)}")
        
        return weaknesses
    
    def _get_defense_players(self):
        """获取防守端关键球员"""
        result = {self.team1: [], self.team2: []}
        
        # 从fifa_extra的防守数据中获取
        defense_data = self.fifa_extra.get('player_defense', {})
        
        for team in [self.team1, self.team2]:
            players = []
            
            if team in defense_data:
                team_def = defense_data[team]
                # 按防守综合分排序
                sorted_p = sorted(
                    team_def,
                    key=lambda p: p.get('defense_score', 0),
                    reverse=True
                )
                for p in sorted_p[:3]:
                    desc_parts = []
                    if p.get('tackles_won'):
                        desc_parts.append(f"{p['tackles_won']}次抢断")
                    if p.get('interceptions'):
                        desc_parts.append(f"{p['interceptions']}次拦截")
                    if p.get('clearances'):
                        desc_parts.append(f"{p['clearances']}次解围")
                    players.append({
                        'name': p.get('name', ''),
                        'desc': ' | '.join(desc_parts) if desc_parts else '防守核心',
                    })
            
            # 如果没有详细防守数据，用传球多的后卫作为替代
            if not players:
                pass_leaders = self.stats[team].get('pass_leaders', {})
                if hasattr(pass_leaders, 'items') and len(pass_leaders) > 0:
                    # 取传球次数较多的（通常后场球员传球多）
                    items = list(pass_leaders.items())
                    items.sort(key=lambda x: x[1], reverse=True)
                    for name, cnt in items[:3]:
                        players.append({
                            'name': name,
                            'desc': f"{cnt}次传球（后场组织）",
                        })
            
            result[team] = players
        
        return result
    
    # ========== 第5页：战术风格画像 ==========
    
    def _build_tactical_style(self, story):
        """构建战术风格画像页"""
        s = self.styles
        
        story.append(Paragraph("四、战术风格画像", s['page_title']))
        
        # 战术雷达图
        if self._has_chart('tactical_radar'):
            story.append(Paragraph("4.1 攻防战术雷达图", s['section_title']))
            img = self._chart_image('tactical_radar', max_width=170*mm, max_height=90*mm)
            if img:
                img_table = Table([[img]], colWidths=[170*mm])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BOX', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#0d1117')),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(img_table)
        
        # 战术风格文字总结
        story.append(Paragraph("4.2 战术风格总结", s['section_title']))
        
        style_summary = self._generate_style_summary()
        
        # 主队风格
        story.append(Paragraph(f"<b>[主] {self.team1}</b>", s['sub_section']))
        story.append(Paragraph(style_summary[self.team1], s['body']))
        
        story.append(Spacer(1, 3*mm))
        
        # 客队风格
        story.append(Paragraph(f"<b>[客] {self.team2}</b>", s['sub_section']))
        story.append(Paragraph(style_summary[self.team2], s['body']))
        
        story.append(Spacer(1, 5*mm))
        
        # 战术对比小结
        story.append(Paragraph("4.3 战术对抗分析", s['section_title']))
        matchup = self._generate_matchup_analysis()
        story.append(Paragraph(matchup, s['body']))
        
        story.append(PageBreak())
    
    def _generate_style_summary(self):
        """生成每队的战术风格文字总结"""
        result = {self.team1: '', self.team2: ''}
        
        radar_data = self.fifa_extra.get('tactical_radar', {})
        
        for team in [self.team1, self.team2]:
            parts = []
            
            # 控球风格
            poss = self.stats[team].get('possession_pct', 50)
            pass_acc = self.stats[team].get('pass_accuracy', 0)
            if poss > 60:
                parts.append(f"控球主导型打法，场均{poss:.0f}%控球率，传球成功率{pass_acc:.0f}%，善于通过传控推进")
            elif poss > 50:
                parts.append(f"控球略占优势（{poss:.0f}%），打法均衡，传球成功率{pass_acc:.0f}%")
            elif poss > 40:
                parts.append(f"控球处于下风（{poss:.0f}%），偏向防守反击战术")
            else:
                parts.append(f"典型的防守反击打法，控球率仅{poss:.0f}%，依赖快速反击威胁对手")
            
            # 进攻风格（从雷达数据）
            if team in radar_data:
                attack = radar_data[team].get('attack', {})
                
                # 找出最高的2个进攻维度
                sorted_attack = sorted(attack.items(), key=lambda x: x[1], reverse=True)
                top2 = [d for d, v in sorted_attack[:2] if v > 5]
                
                if top2:
                    parts.append(f"进攻端以{'、'.join(top2)}为主要特点")
                
                # 反击倾向
                counter = attack.get('反击', 0)
                if counter > 8:
                    parts.append(f"反击威胁突出（占比{counter:.0f}%），善于利用攻防转换机会")
            
            # 防守风格（从雷达数据）
            if team in radar_data:
                defense = radar_data[team].get('defense', {})
                
                high_block = defense.get('高位压迫', 0) + defense.get('高位防线', 0)
                low_block = defense.get('低位防线', 0)
                
                if high_block > low_block and high_block > 25:
                    parts.append(f"防守端采取高位逼抢策略（高位防守占比约{high_block:.0f}%），主动压迫夺回球权")
                elif low_block > 20:
                    parts.append(f"防守端偏向低位防守（低位防线占比{low_block:.0f}%），收缩阵型保护禁区")
                else:
                    parts.append(f"防守呈中位防守态势，阵线保持在中场附近")
            
            # 射门效率
            shots = self.stats[team].get('shots_total', 0)
            goals = self.stats[team].get('goals', 0)
            xg = self.stats[team].get('xg', 0)
            if shots > 0:
                conv_rate = goals / shots * 100
                if conv_rate > 15:
                    parts.append(f"射门转化率达{conv_rate:.1f}%，终结效率出色")
                elif abs(goals - xg) > 0.5:
                    if goals > xg:
                        parts.append(f"把握机会能力强于预期（进球{goals} vs xG {xg:.2f}）")
                    else:
                        parts.append(f"临门一脚有待提升（进球{goals} vs xG {xg:.2f}）")
            
            result[team] = '；'.join(parts) + '。'
        
        return result
    
    def _generate_matchup_analysis(self):
        """生成战术对抗分析"""
        radar_data = self.fifa_extra.get('tactical_radar', {})
        
        t1_poss = self.stats[self.team1].get('possession_pct', 50)
        t2_poss = self.stats[self.team2].get('possession_pct', 50)
        
        parts = []
        
        # 控球对抗
        if abs(t1_poss - t2_poss) > 10:
            dom = self.team1 if t1_poss > t2_poss else self.team2
            reac = self.team2 if t1_poss > t2_poss else self.team1
            parts.append(
                f"本场呈现明显的「{dom}控球推进 vs {reac}防守反击」的战术对抗格局。"
                f"{dom}掌控球权，通过持续推进制造威胁；{reac}则收缩防线，伺机发动反击。"
            )
        else:
            parts.append(
                f"双方控球率接近（{t1_poss:.0f}% vs {t2_poss:.0f}%），"
                f"比赛呈中场拉锯态势，阵地战与转换进攻交替出现。"
            )
        
        # 进攻效率对比
        t1_xg = self.stats[self.team1].get('xg', 0)
        t2_xg = self.stats[self.team2].get('xg', 0)
        if abs(t1_xg - t2_xg) > 0.5:
            better = self.team1 if t1_xg > t2_xg else self.team2
            parts.append(
                f"从预期进球来看，{better}创造了更多高质量机会（{max(t1_xg,t2_xg):.2f} xG vs {min(t1_xg,t2_xg):.2f} xG），"
                f"进攻端威胁更大。"
            )
        
        # 防守强度
        if self.team1 in radar_data and self.team2 in radar_data:
            t1_high = radar_data[self.team1]['defense'].get('高位压迫', 0) + radar_data[self.team1]['defense'].get('高位防线', 0)
            t2_high = radar_data[self.team2]['defense'].get('高位压迫', 0) + radar_data[self.team2]['defense'].get('高位防线', 0)
            
            if abs(t1_high - t2_high) > 10:
                more = self.team1 if t1_high > t2_high else self.team2
                parts.append(
                    f"防守强度方面，{more}的高位防守比重更高（约{max(t1_high,t2_high):.0f}%），"
                    f"前场逼抢更积极。"
                )
        
        return ''.join(parts)
    
    # ========== 第6页：体能与传球 ==========
    
    def _build_fitness_passing(self, story):
        """构建体能与传球页"""
        s = self.styles
        
        story.append(Paragraph("五、体能与传球组织", s['page_title']))
        
        # 体能五分区图
        if self._has_chart('physical_zones'):
            story.append(Paragraph("5.1 体能五分区对比", s['section_title']))
            img = self._chart_image('physical_zones', max_width=170*mm, max_height=95*mm)
            if img:
                img_table = Table([[img]], colWidths=[170*mm])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BOX', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#0d1117')),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                story.append(img_table)
        
        # 传球网络
        if self._has_chart('pass_network'):
            story.append(Paragraph("5.2 传球网络图", s['section_title']))
            img = self._chart_image('pass_network', max_width=170*mm, max_height=85*mm)
            if img:
                img_table = Table([[img]], colWidths=[170*mm])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BOX', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#0d1117')),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                story.append(img_table)
        
        # 组织核心球员
        story.append(Paragraph("5.3 组织核心球员", s['section_title']))
        
        playmakers = self._get_playmakers()
        if playmakers:
            pm_table_data = [[
                Paragraph("球队", s['table_header']),
                Paragraph("核心球员", s['table_header']),
                Paragraph("数据表现", s['table_header']),
            ]]
            
            for team in [self.team1, self.team2]:
                if team in playmakers and playmakers[team]:
                    p = playmakers[team]
                    color = TEAM1_COLOR if team == self.team1 else TEAM2_COLOR
                    pm_table_data.append([
                        Paragraph(f"<b>{team}</b>", s['table_cell_left']),
                        Paragraph(f"<b>{p['name']}</b>", s['table_cell_left']),
                        Paragraph(p['desc'], s['table_cell_left']),
                    ])
            
            if len(pm_table_data) > 1:
                pm_table = Table(pm_table_data, colWidths=[40*mm, 50*mm, 60*mm])
                pm_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), HexColor(PRIMARY_COLOR)),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#f8fafc'), HexColor('#ffffff')]),
                    ('GRID', (0, 0), (-1, -1), 0.5, HexColor(BORDER_COLOR)),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ]))
                story.append(pm_table)
        
        story.append(PageBreak())
    
    def _get_playmakers(self):
        """获取组织核心球员（传球最多的中场球员）"""
        result = {}
        
        for team in [self.team1, self.team2]:
            pass_leaders = self.stats[team].get('pass_leaders', {})
            if hasattr(pass_leaders, 'items') and len(pass_leaders) > 0:
                items = list(pass_leaders.items())
                items.sort(key=lambda x: x[1], reverse=True)
                top_name, top_cnt = items[0]
                
                # 关键传球
                key_passes = self.stats[team].get('key_passes', 0)
                
                result[team] = {
                    'name': top_name,
                    'desc': f"{top_cnt}次成功传球，全队传球成功率{self.stats[team].get('pass_accuracy', 0):.0f}%",
                }
        
        return result
    
    # ========== 第7页：战术洞察总结 ==========
    
    def _build_insights_summary(self, story):
        """构建战术洞察总结页"""
        s = self.styles
        
        story.append(Paragraph("六、战术洞察总结", s['page_title']))
        
        # 从fifa_adapter获取洞察
        attack_insights = []
        defense_insights = []
        
        try:
            from fifa_adapter import generate_tactical_insights
            insights = generate_tactical_insights(self.stats, self.info)
            attack_insights = insights.get('attack', [])
            defense_insights = insights.get('defense', [])
        except Exception as e:
            print(f"[PDF生成器] 获取战术洞察失败: {e}")
        
        # 进攻端洞察
        story.append(Paragraph("6.1 进攻端洞察", s['section_title']))
        
        if attack_insights:
            for i, ins in enumerate(attack_insights[:7]):
                priority = ins.get('priority', 3)
                priority_icon = {1: '●', 2: '○', 3: '·'}.get(priority, '·')
                category = ins.get('category', '')
                text = ins.get('text', '')
                
                story.append(Paragraph(
                    f"<b>{priority_icon} [{category}]</b> {text}",
                    s['insight_text']
                ))
                if ins.get('suggestion'):
                    story.append(Paragraph(
                        f"<i>建议：{ins['suggestion']}</i>",
                        ParagraphStyle(
                            'suggestion', fontName=FONT_CN, fontSize=9, leading=13,
                            textColor=HexColor(SUBTEXT_COLOR), alignment=TA_JUSTIFY,
                            spaceAfter=4, leftIndent=20,
                        )
                    ))
        else:
            story.append(Paragraph("暂无进攻端洞察数据。", s['body']))
        
        # 防守端洞察
        story.append(Paragraph("6.2 防守端洞察", s['section_title']))
        
        if defense_insights:
            for i, ins in enumerate(defense_insights[:7]):
                priority = ins.get('priority', 3)
                priority_icon = {1: '●', 2: '○', 3: '·'}.get(priority, '·')
                category = ins.get('category', '')
                text = ins.get('text', '')
                
                story.append(Paragraph(
                    f"<b>{priority_icon} [{category}]</b> {text}",
                    s['insight_text']
                ))
                if ins.get('suggestion'):
                    story.append(Paragraph(
                        f"<i>建议：{ins['suggestion']}</i>",
                        ParagraphStyle(
                            'suggestion', fontName=FONT_CN, fontSize=9, leading=13,
                            textColor=HexColor(SUBTEXT_COLOR), alignment=TA_JUSTIFY,
                            spaceAfter=4, leftIndent=20,
                        )
                    ))
        else:
            story.append(Paragraph("暂无防守端洞察数据。", s['body']))
        
        # 整体比赛总结
        story.append(Paragraph("6.3 整体比赛总结", s['section_title']))
        
        summary = self._generate_overall_summary()
        story.append(Paragraph(summary, s['body']))
        
        # 结尾
        story.append(Spacer(1, 10*mm))
        story.append(Paragraph("—— 报告完 ——", ParagraphStyle(
            'end_note', fontName=FONT_CN, fontSize=10, leading=14,
            textColor=HexColor(SUBTEXT_COLOR), alignment=TA_CENTER,
        )))
        story.append(Paragraph("战术透镜 · 用数据读懂足球", ParagraphStyle(
            'end_brand', fontName=FONT_CN, fontSize=9, leading=12,
            textColor=HexColor(ACCENT_COLOR), alignment=TA_CENTER,
            spaceAfter=2,
        )))
    
    def _generate_overall_summary(self):
        """生成整体比赛总结"""
        t1_goals = self.s1.get('goals', 0)
        t2_goals = self.s2.get('goals', 0)
        t1_xg = self.s1.get('xg', 0)
        t2_xg = self.s2.get('xg', 0)
        
        parts = []
        
        # 比赛结果
        if t1_goals > t2_goals:
            result = f"{self.team1} {t1_goals}-{t2_goals} 战胜 {self.team2}"
            winner = self.team1
            loser = self.team2
        elif t2_goals > t1_goals:
            result = f"{self.team2} {t2_goals}-{t1_goals} 战胜 {self.team1}"
            winner = self.team2
            loser = self.team1
        else:
            result = f"{self.team1} 与 {self.team2} 战成 {t1_goals}-{t2_goals} 平局"
            winner = None
            loser = None
        
        parts.append(f"本场比赛{result}。")
        
        # xG vs 实际结果
        if winner:
            winner_xg = self.stats[winner].get('xg', 0)
            loser_xg = self.stats[loser].get('xg', 0)
            
            if winner_xg >= loser_xg:
                parts.append(
                    f"从预期进球来看，{winner}（{winner_xg:.2f} xG）确实创造了更多机会，"
                    f"胜利实至名归。"
                )
            else:
                parts.append(
                    f"值得注意的是，{loser}的预期进球（{loser_xg:.2f} xG）高于{winner}（{winner_xg:.2f} xG），"
                    f"{winner}在机会创造不占优的情况下凭借高效终结取得胜利。"
                )
        else:
            if abs(t1_xg - t2_xg) < 0.3:
                parts.append("双方预期进球也较为接近，平局反映了场上的均势格局。")
            else:
                better = self.team1 if t1_xg > t2_xg else self.team2
                parts.append(
                    f"尽管比分持平，但{better}的预期进球更高（{max(t1_xg,t2_xg):.2f} vs {min(t1_xg,t2_xg):.2f}），"
                    f"创造了更多得分机会，未能取胜略显遗憾。"
                )
        
        # 关键因素
        t1_poss = self.s1.get('possession_pct', 50)
        t2_poss = self.s2.get('possession_pct', 50)
        
        if abs(t1_poss - t2_poss) > 15:
            dom = self.team1 if t1_poss > t2_poss else self.team2
            parts.append(
                f"控球权方面，{dom}占据压倒性优势，"
                f"但控球优势能否转化为进球是决定比赛走向的关键因素。"
            )
        
        return ''.join(parts)
    
    # ========== 主生成函数 ==========
    
    def generate(self):
        """生成完整PDF报告"""
        print(f"[PDF生成器] 开始生成报告 → {self.output_path}")
        
        # 确保图表已生成
        self._ensure_charts()
        
        # 创建文档
        doc = BaseDocTemplate(
            self.output_path,
            pagesize=A4,
            leftMargin=20*mm,
            rightMargin=20*mm,
            topMargin=22*mm,
            bottomMargin=18*mm,
            title=f"{self.team1} vs {self.team2} 战术分析报告",
            author="战术透镜 Tactical Lens",
        )
        
        # 页面模板
        frame = Frame(
            doc.leftMargin, doc.bottomMargin,
            doc.width, doc.height,
            id='main'
        )
        template = PageTemplate(id='main', frames=[frame], onPage=_page_decorator)
        doc.addPageTemplates([template])
        
        # 构建内容
        story = []
        
        # 第1页：封面
        self._build_cover(story)
        
        # 第2页：核心数据对比
        self._build_core_stats(story)
        
        # 第3页：进攻端分析
        self._build_attack_analysis(story)
        
        # 第4页：防守端分析
        self._build_defense_analysis(story)
        
        # 第5页：战术风格画像
        self._build_tactical_style(story)
        
        # 第6页：体能与传球
        self._build_fitness_passing(story)
        
        # 第7页：战术洞察总结
        self._build_insights_summary(story)
        
        # 构建PDF
        doc.build(story)
        
        # 清理临时文件
        if self._temp_dir:
            import shutil
            try:
                shutil.rmtree(self._temp_dir)
                print(f"[PDF生成器] 临时图表目录已清理")
            except Exception:
                pass
        
        file_size = os.path.getsize(self.output_path) / (1024 * 1024)
        print(f"[PDF生成器] 报告生成完成！文件大小: {file_size:.2f} MB")
        
        return self.output_path


# ========== 便捷函数 ==========

def generate_pdf_report(df, info, stats, output_path, chart_dir=None):
    """便捷函数：生成PDF战术报告
    
    参数:
        df: 事件数据DataFrame
        info: 比赛信息字典
        stats: 球队统计字典
        output_path: PDF输出路径
        chart_dir: 预先生成的高清图表目录（可选）
    
    返回:
        str: PDF文件路径
    """
    gen = TacticalReportGenerator(df, info, stats, output_path, chart_dir)
    return gen.generate()


def get_pdf_filename(team1, team2):
    """生成PDF文件名：{主队}_{客队}_战术分析报告.pdf"""
    # 清理文件名中的非法字符
    def clean(name):
        for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            name = name.replace(ch, '_')
        return name.strip()
    
    return f"{clean(team1)}_{clean(team2)}_战术分析报告.pdf"
