"""
app.py — 战术透镜 Streamlit 网页版
启动：streamlit run app.py

v5 更新说明：
- 新增「FIFA比赛报告(PDF)」直接上传功能 — 最优体验，传一个PDF就完事
- 新增FIFA PDF解析器 (fifa_pdf_parser.py)，自动解析12个数据表
- 数据格式选项顺序：FIFA PDF > FIFA ZIP > 单文件CSV
- 默认选中FIFA PDF
- 解析失败时友好提示，不崩溃

v6 UI升级：专业运动数据报告风格
- 浅色纸张感背景，深海军蓝标题
- 主队深青蓝 / 客队暖砖橙 配色体系
- 赛事横幅、数据卡片、板块化布局
"""
import streamlit as st
import os
import sys
import tempfile
import zipfile

# 把当前目录加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import auto_load
from stats_engine import compute_match_stats, generate_insights
from visualizer import generate_all_charts, plot_team_trend, plot_attack_defense_trend
from report_engine import generate_text_report, generate_html_report, ReportTemplate

# 尝试导入FIFA适配器
try:
    from fifa_adapter import load_fifa_from_csv, is_fifa_csv_dir, generate_tactical_insights, detect_fifa_from_filenames
    _HAS_FIFA = True
    _FIFA_IMPORT_ERROR = None
except ImportError as e:
    _HAS_FIFA = False
    _FIFA_IMPORT_ERROR = str(e)

# 尝试导入FIFA PDF解析器
try:
    from fifa_pdf_parser import parse_fifa_pdf
    _HAS_FIFA_PDF = True
    _FIFA_PDF_IMPORT_ERROR = None
except ImportError as e:
    _HAS_FIFA_PDF = False
    _FIFA_PDF_IMPORT_ERROR = str(e)
    # 进一步检测是pdfplumber缺失还是其他问题
    try:
        import pdfplumber  # noqa: F401
        _PDFPLUMBER_AVAILABLE = True
    except ImportError:
        _PDFPLUMBER_AVAILABLE = False

# 尝试导入球队追踪模块
try:
    from team_tracker import load_multiple_matches, compute_team_overview, compute_trends, find_common_teams
    _HAS_TEAM_TRACKER = True
    _TEAM_TRACKER_ERROR = None
except ImportError as e:
    _HAS_TEAM_TRACKER = False
    _TEAM_TRACKER_ERROR = str(e)

# PDF报告生成器（延迟导入，点击下载时才加载，节省内存）
_HAS_PDF_REPORT = True  # 假设存在，真正导入失败会在下载时提示
_PDF_REPORT_ERROR = None

def _get_pdf_generator():
    """延迟导入PDF生成器，只有点击下载时才加载"""
    try:
        from report_generator import generate_pdf_report, get_pdf_filename
        return generate_pdf_report, get_pdf_filename, None
    except Exception as e:
        return None, None, str(e)


# ========== 页面配置 ==========
st.set_page_config(
    page_title="战术透镜",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 自定义CSS：深色专业运动数据报告风格 ==========
st.markdown("""
<style>
    /* ===== 全局字体与基础样式 ===== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }
    
    /* ===== 标题样式 ===== */
    h1 {
        color: #f1f5f9 !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em;
        padding-bottom: 0.75rem;
        margin-bottom: 1.5rem;
    }
    
    h2, .stSubheader > div > div > div > p {
        color: #e2e8f0 !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em;
    }
    
    h3 {
        color: #cbd5e1 !important;
        font-weight: 600 !important;
    }
    
    p, span, div {
        color: #cbd5e1;
    }
    
    /* ===== 卡片样式 ===== */
    .data-card {
        background: #1e293b;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3), 0 1px 2px rgba(0, 0, 0, 0.2);
        border: 1px solid #334155;
        transition: box-shadow 0.2s ease, border-color 0.2s ease;
    }
    
    .data-card:hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4), 0 2px 4px rgba(0, 0, 0, 0.3);
        border-color: #475569;
    }
    
    .data-card-label {
        font-size: 0.75rem;
        color: #94a3b8;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.5rem;
    }
    
    .data-card-value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #f1f5f9;
        line-height: 1.2;
    }
    
    .data-card-sub {
        font-size: 0.8rem;
        color: #64748b;
        margin-top: 0.25rem;
    }
    
    /* ===== 赛事横幅 ===== */
    .match-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border-radius: 16px;
        padding: 2rem 2.5rem;
        margin-bottom: 2rem;
        position: relative;
        overflow: hidden;
        border: 1px solid #334155;
    }
    
    .match-banner::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #0d9488 0%, #f97316 100%);
    }
    
    .banner-team-home {
        text-align: right;
        padding-right: 1rem;
    }
    
    .banner-team-away {
        text-align: left;
        padding-left: 1rem;
    }
    
    .banner-team-name {
        font-size: 1.5rem;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 0.25rem;
    }
    
    .banner-team-name.home {
        color: #0d9488;
    }
    
    .banner-team-name.away {
        color: #f97316;
    }
    
    .banner-team-formation {
        font-size: 0.85rem;
        color: #94a3b8;
    }
    
    .banner-score-section {
        text-align: center;
    }
    
    .banner-score {
        font-size: 3rem;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: 0.05em;
        line-height: 1;
        font-variant-numeric: tabular-nums;
    }
    
    .banner-score .home-score {
        color: #0d9488;
    }
    
    .banner-score .away-score {
        color: #f97316;
    }
    
    .banner-score-divider {
        color: #475569;
        margin: 0 0.5rem;
    }
    
    .banner-meta {
        text-align: center;
        margin-top: 0.75rem;
        font-size: 0.85rem;
        color: #94a3b8;
    }
    
    .banner-competition {
        font-weight: 500;
        color: #cbd5e1;
    }
    
    /* ===== 板块标题样式 ===== */
    .section-header {
        display: flex;
        align-items: center;
        margin: 2.5rem 0 1.25rem 0;
        padding-bottom: 0.75rem;
        border-bottom: 2px solid #334155;
    }
    
    .section-header-icon {
        font-size: 1.25rem;
        margin-right: 0.75rem;
    }
    
    .section-header-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #f1f5f9;
        flex: 1;
    }
    
    .section-header-tag {
        font-size: 0.75rem;
        padding: 0.25rem 0.75rem;
        background: #1e293b;
        color: #94a3b8;
        border-radius: 999px;
        font-weight: 500;
        border: 1px solid #334155;
    }
    
    /* ===== 侧边栏样式 ===== */
    section[data-testid="stSidebar"] {
        background-color: #0f172a !important;
        border-right: 1px solid #334155;
    }
    
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1rem !important;
    }
    
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div,
    section[data-testid="stSidebar"] label {
        color: #cbd5e1 !important;
    }
    
    section[data-testid="stSidebar"] small {
        color: #64748b !important;
    }
    
    .sidebar-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        margin: -1rem -1rem 1rem -1rem;
        padding: 1.5rem 1.25rem;
        border-radius: 0 0 16px 16px;
        border-bottom: 1px solid #334155;
    }
    
    .sidebar-logo {
        font-size: 1.5rem;
        margin-bottom: 0.25rem;
    }
    
    .sidebar-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #ffffff !important;
        margin: 0;
    }
    
    .sidebar-subtitle {
        font-size: 0.75rem;
        color: #94a3b8 !important;
        margin-top: 0.25rem;
    }
    
    .sidebar-accent {
        height: 3px;
        background: linear-gradient(90deg, #0d9488 0%, #f97316 100%);
        margin: 0.75rem -1.25rem 0 -1.25rem;
        border-radius: 2px;
    }
    
    /* ===== 上传框样式 ===== */
    [data-testid="stFileUploader"] {
        border: 2px dashed #334155;
        border-radius: 10px;
        background: #1e293b;
        transition: border-color 0.2s ease;
    }
    
    [data-testid="stFileUploader"]:hover {
        border-color: #0d9488;
    }
    
    /* ===== 按钮样式增强 ===== */
    .stButton > button[kind="primary"] {
        background-color: #0d9488;
        color: #ffffff;
        font-weight: 600;
        border-radius: 8px;
        border: none;
        padding: 0.6rem 1.25rem;
        transition: all 0.2s ease;
    }
    
    .stButton > button[kind="primary"]:hover {
        background-color: #0f766e;
        box-shadow: 0 4px 12px rgba(13, 148, 136, 0.3);
    }
    
    .stButton > button[kind="primary"]:active {
        background-color: #115e59;
    }
    
    .stButton > button {
        background-color: #1e293b;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 8px;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        background-color: #334155;
        border-color: #475569;
    }
    
    /* ===== PDF下载大按钮 ===== */
    .pdf-download-card {
        background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        color: #ffffff;
    }
    
    .pdf-download-title {
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 0.25rem;
        color: #ffffff !important;
    }
    
    .pdf-download-desc {
        font-size: 0.8rem;
        opacity: 0.9;
        color: rgba(255,255,255,0.85) !important;
    }
    
    /* ===== 分割线 ===== */
    hr {
        border-color: #334155 !important;
        margin: 1.5rem 0;
    }
    
    /* ===== 洞察卡片 ===== */
    .insight-card {
        background: #1e293b;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
        border-left: 4px solid #0d9488;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
    }
    
    .insight-card.priority-1 {
        border-left-color: #ef4444;
        background: #1c1917;
    }
    
    .insight-card.priority-2 {
        border-left-color: #f97316;
        background: #1c1917;
    }
    
    .insight-card.priority-3 {
        border-left-color: #64748b;
        background: #1e293b;
    }
    
    /* ===== 表格样式 ===== */
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #334155;
    }
    
    /* ===== 隐藏默认菜单和页脚 ===== */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* ===== 展开面板样式 ===== */
    .streamlit-expanderHeader {
        font-weight: 600;
        color: #94a3b8;
    }
    
    .streamlit-expanderContent {
        background: #0f172a;
    }
    
    /* ===== 指标对比条 ===== */
    .metric-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.6rem 0;
        border-bottom: 1px solid #334155;
    }
    
    .metric-row:last-child {
        border-bottom: none;
    }
    
    .metric-label {
        color: #94a3b8;
        font-size: 0.85rem;
    }
    
    .metric-values {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    
    .metric-home {
        font-weight: 600;
        color: #0d9488;
        min-width: 3.5rem;
        text-align: right;
    }
    
    .metric-away {
        font-weight: 600;
        color: #f97316;
        min-width: 3.5rem;
        text-align: left;
    }
    
    .metric-bar-container {
        width: 80px;
        height: 6px;
        background: #334155;
        border-radius: 3px;
        position: relative;
        overflow: hidden;
    }
    
    .metric-bar-fill-home {
        position: absolute;
        left: 0;
        top: 0;
        height: 100%;
        background: #0d9488;
        border-radius: 3px 0 0 3px;
    }
    
    .metric-bar-fill-away {
        position: absolute;
        right: 0;
        top: 0;
        height: 100%;
        background: #f97316;
        border-radius: 0 3px 3px 0;
    }
    
    /* ===== 首页提示信息条 ===== */
    .stAlert [data-testid="stAlertContainer"] {
        background: #1e293b !important;
        border: 1px solid #334155 !important;
        color: #cbd5e1 !important;
    }
    
    .stAlert p,
    .stAlert span,
    .stAlert div {
        color: #cbd5e1 !important;
    }
    
    /* ===== caption 小字 ===== */
    .stCaption, small, [data-testid="stCaptionContainer"] {
        color: #64748b !important;
    }
    
    /* ===== 代码块 ===== */
    .stCodeBlock > div {
        background: #0f172a !important;
        border: 1px solid #334155 !important;
    }
    
    .stCodeBlock pre,
    .stCodeBlock code {
        color: #e2e8f0 !important;
        background: transparent !important;
    }
    
    /* ===== 下拉选择框 ===== */
    .stSelectbox > div > div > select {
        background-color: #1e293b;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 8px;
    }
    
    .stSelectbox > div > div > select:focus {
        border-color: #0d9488;
    }
    
    /* ===== 输入框 ===== */
    .stTextInput > div > div > input {
        background-color: #1e293b;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 8px;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #0d9488;
    }
    
    /* ===== 上传框内部文字 ===== */
    [data-testid="stFileUploader"] p,
    [data-testid="stFileUploader"] span,
    [data-testid="stFileUploader"] small {
        color: #94a3b8 !important;
    }
    
    [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneInstructions"] > div {
        color: #94a3b8 !important;
    }
    
    /* ===== 图片说明文字 ===== */
    [data-testid="stImageCaption"] {
        color: #64748b !important;
    }
    
    /* ===== 折叠面板内部 ===== */
    .streamlit-expanderContent p,
    .streamlit-expanderContent span,
    .streamlit-expanderContent div {
        color: #cbd5e1;
    }
    
    /* ===== DataFrame 深色模式 ===== */
    .stDataFrame [data-testid="stTableStyledTable"] {
        background-color: #1e293b !important;
    }
    
    .stDataFrame table {
        color: #cbd5e1 !important;
    }
    
    .stDataFrame th {
        background-color: #334155 !important;
        color: #f1f5f9 !important;
    }
    
    .stDataFrame td {
        background-color: #1e293b !important;
        color: #cbd5e1 !important;
    }
    
    /* ===== 响应式调整 ===== */
    @media (max-width: 768px) {
        .banner-team-name {
            font-size: 1.1rem;
        }
        .banner-score {
            font-size: 2rem;
        }
        .match-banner {
            padding: 1.25rem 1rem;
        }
    }
</style>
""", unsafe_allow_html=True)


# ========== 辅助函数：图表放大展示 ==========
def show_chart_with_zoom(chart_path, chart_title, zoom_level=1.0):
    """展示图表并提供点击放大功能
    
    参数:
        chart_path: 图表文件路径
        chart_title: 图表标题
        zoom_level: 放大倍数（默认1.0即原图大小）
    """
    if not chart_path or not os.path.exists(chart_path):
        st.info(f"暂无 {chart_title} 数据")
        return
    
    # 缩略图展示（带卡片容器）
    st.markdown('<div class="data-card" style="padding: 1rem; margin-bottom: 0.75rem;">', unsafe_allow_html=True)
    st.image(chart_path, caption=chart_title, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 放大查看（折叠面板）
    with st.expander(f"🔍 点击放大查看 — {chart_title}"):
        st.image(chart_path, caption=chart_title, use_container_width=True, clamp=False)
        st.caption("💡 提示：右键图片可保存或在新标签页中查看原图")


# ========== 辅助函数：数据卡片 ==========
def render_stat_card(label, value, sub_text="", home_color=True):
    """渲染一个数据卡片
    
    参数:
        label: 卡片标签（顶部小字）
        value: 主要数值
        sub_text: 底部补充说明
        home_color: True用主队色强调，False用客队色
    """
    accent_color = "#0d9488" if home_color else "#f97316"
    sub_html = f'<div class="data-card-sub">{sub_text}</div>' if sub_text else ''
    st.markdown(f"""
    <div class="data-card">
        <div class="data-card-label">{label}</div>
        <div class="data-card-value" style="color: {accent_color};">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


# ========== 辅助函数：赛事横幅 ==========
def render_match_banner(team_home, team_away, score_home, score_away, 
                        formation_home="", formation_away="",
                        competition="", match_date=""):
    """渲染赛事顶部横幅
    
    参数:
        team_home: 主队名
        team_away: 客队名
        score_home: 主队得分
        score_away: 客队得分
        formation_home: 主队阵型
        formation_away: 客队阵型
        competition: 赛事名称
        match_date: 比赛日期
    """
    formation_home_html = f'<div class="banner-team-formation">{formation_home}</div>' if formation_home else ''
    formation_away_html = f'<div class="banner-team-formation">{formation_away}</div>' if formation_away else ''
    
    meta_parts = []
    if competition:
        meta_parts.append(f'<span class="banner-competition">{competition}</span>')
    if match_date:
        meta_parts.append(f'<span>{match_date}</span>')
    meta_html = f'<div class="banner-meta">{" · ".join(meta_parts)}</div>' if meta_parts else ''
    
    st.markdown(f"""
    <div class="match-banner">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <div class="banner-team-home" style="flex: 1;">
                <div class="banner-team-name home">{team_home}</div>
                {formation_home_html}
            </div>
            <div class="banner-score-section" style="flex: 0 0 auto; padding: 0 1.5rem;">
                <div class="banner-score">
                    <span class="home-score">{score_home}</span>
                    <span class="banner-score-divider">:</span>
                    <span class="away-score">{score_away}</span>
                </div>
                {meta_html}
            </div>
            <div class="banner-team-away" style="flex: 1;">
                <div class="banner-team-name away">{team_away}</div>
                {formation_away_html}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ========== 辅助函数：板块标题 ==========
def render_section_header(icon, title, tag=""):
    """渲染板块标题（带图标和分割线效果）
    
    参数:
        icon: emoji图标
        title: 板块标题
        tag: 右侧标签文字
    """
    tag_html = f'<span class="section-header-tag">{tag}</span>' if tag else ''
    st.markdown(f"""
    <div class="section-header">
        <span class="section-header-icon">{icon}</span>
        <span class="section-header-title">{title}</span>
        {tag_html}
    </div>
    """, unsafe_allow_html=True)


# ========== 侧边栏 ==========
with st.sidebar:
    # 侧边栏顶部标题区
    st.markdown("""
    <div class="sidebar-header">
        <div class="sidebar-logo">⚽</div>
        <div class="sidebar-title">战术透镜</div>
        <div class="sidebar-subtitle">Tactical Lens · v5</div>
        <div class="sidebar-accent"></div>
    </div>
    """, unsafe_allow_html=True)
    
    # ===== 模式切换 =====
    analysis_mode = st.radio(
        "分析模式",
        ["单场分析", "球队追踪"],
        horizontal=True,
        help="单场分析：一场比赛的完整战术分析；球队追踪：一支球队多场比赛的趋势对比"
    )
    
    st.divider()
    
    st.subheader("📂 上传数据")
    
    if analysis_mode == "单场分析":
        uploaded_files = st.file_uploader(
            "拖拽文件到此处，或点击选择",
            type=['pdf', 'csv', 'zip'],
            accept_multiple_files=True,
            help="支持：FIFA比赛报告PDF、FIFA多文件CSV、StatsBomb事件流CSV、ZIP打包、Catapult体能数据等，自动识别格式"
        )
        st.caption("💡 一个上传框搞定所有格式，自动识别，无需手动选择")

        match_name = st.text_input("比赛名称", value="自定义比赛")

        template_choice = st.selectbox(
            "报告模板",
            ["default - 完整报告", "concise - 精简速报", "coach - 教练版"],
            help="完整报告7张图；精简版2张图；教练版重点训练建议"
        )
    else:
        # 球队追踪模式上传
        uploaded_files = st.file_uploader(
            "上传多场比赛数据（FIFA CSV/ZIP/PDF）",
            type=['pdf', 'csv', 'zip'],
            accept_multiple_files=True,
            help="上传多场FIFA比赛的数据，支持混合格式。上传后自动识别共同球队，查看球队多场表现趋势"
        )
        st.caption("💡 上传多场比赛 → 自动识别共同球队 → 查看趋势")
        match_name = "球队追踪"
        template_choice = "default - 完整报告"

    template_map = {
        "default - 完整报告": "default",
        "concise - 精简速报": "concise",
        "coach - 教练版": "coach",
    }
    template_name = template_map[template_choice]

    st.divider()

    # 比赛信息摘要（有数据时显示）
    # （在主区域分析完成后会有数据再更新，这里先占位）

    # 项目结构展示
    with st.expander("📁 项目结构"):
        st.code("""
tactical_lens/
├── main.py           入口
├── app.py            网页版(当前)
├── data_loader.py    数据加载
├── fifa_adapter.py   FIFA数据适配器
├── fifa_pdf_parser.py FIFA PDF解析器
├── stats_engine.py   统计引擎
├── visualizer.py     可视化引擎
├── report_engine.py  报告引擎
└── templates/        报告模板
""", language=None)

    st.divider()
    st.caption("数据来源：StatsBomb / FIFA 比赛报告")

# ========== 主区域 ==========
if analysis_mode == "球队追踪":
    st.title("📊 战术透镜 — 球队多场追踪")
else:
    st.title("⚽ 战术透镜 — 比赛分析报告")

# 判断是否有上传
has_data = uploaded_files is not None and len(uploaded_files) > 0

if not has_data:
    if analysis_mode == "球队追踪":
        st.info("👈 上传多场FIFA比赛数据，查看球队跨场表现趋势")
        
        st.markdown("""
        <div class="section-header">
            <span class="section-header-icon">📋</span>
            <span class="section-header-title">球队追踪功能</span>
        </div>
        """, unsafe_allow_html=True)
        
        feat_cols = st.columns(2)
        with feat_cols[0]:
            st.markdown("""
            <div class="data-card" style="margin-bottom: 1rem;">
                <div class="data-card-label">📈 趋势分析</div>
                <div class="data-card-value" style="font-size: 1.1rem; color: #0d9488;">多场表现追踪</div>
                <div class="data-card-sub">控球率、xG、进球、传球成功率趋势</div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div class="data-card" style="margin-bottom: 1rem;">
                <div class="data-card-label">🎯 汇总指标</div>
                <div class="data-card-value" style="font-size: 1.1rem; color: #e2e8f0;">胜率/净胜球/xG差</div>
                <div class="data-card-sub">球队整体表现一目了然</div>
            </div>
            """, unsafe_allow_html=True)
        with feat_cols[1]:
            st.markdown("""
            <div class="data-card" style="margin-bottom: 1rem;">
                <div class="data-card-label">⚔️ 攻防对比</div>
                <div class="data-card-value" style="font-size: 1.1rem; color: #e2e8f0;">进球vs失球 / xG vs xGA</div>
                <div class="data-card-sub">每场攻防两端表现对比</div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div class="data-card" style="margin-bottom: 1rem;">
                <div class="data-card-label">🔍 自动识别</div>
                <div class="data-card-value" style="font-size: 1.1rem; color: #e2e8f0;">自动检测共同球队</div>
                <div class="data-card-sub">上传多场比赛，自动找出共同球队</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div class="section-header">
            <span class="section-header-icon">🚀</span>
            <span class="section-header-title">使用流程</span>
        </div>
        """, unsafe_allow_html=True)
        
        steps_cols = st.columns(3)
        steps = [
            ("1", "上传多场", "拖拽多场FIFA比赛PDF/CSV/ZIP到上传框"),
            ("2", "选择球队", "自动识别共同球队，选择要追踪的球队"),
            ("3", "查看趋势", "汇总指标 + 趋势图 + 攻防对比 + 比赛列表"),
        ]
        for i, (num, title, desc) in enumerate(steps):
            with steps_cols[i]:
                st.markdown(f"""
                <div class="data-card" style="text-align: center;">
                    <div style="font-size: 2rem; font-weight: 800; color: #0d9488; margin-bottom: 0.5rem;">{num}</div>
                    <div style="font-weight: 600; color: #e2e8f0; margin-bottom: 0.25rem;">{title}</div>
                    <div class="data-card-sub">{desc}</div>
                </div>
                """, unsafe_allow_html=True)
        
        st.stop()
    else:
        st.info("👈 拖拽文件到左侧上传框，自动识别格式，开始分析")
        
        st.markdown("""
        <div class="section-header">
            <span class="section-header-icon">📋</span>
            <span class="section-header-title">支持的数据格式</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 用卡片展示支持的格式
        fmt_cols = st.columns(2)
        with fmt_cols[0]:
            st.markdown("""
            <div class="data-card" style="margin-bottom: 1rem;">
                <div class="data-card-label">⭐ 最推荐</div>
                <div class="data-card-value" style="font-size: 1.1rem; color: #0d9488;">FIFA比赛报告PDF</div>
                <div class="data-card-sub">一个PDF = 12项完整数据 = 11张图表</div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div class="data-card" style="margin-bottom: 1rem;">
                <div class="data-card-label">专业级</div>
                <div class="data-card-value" style="font-size: 1.1rem; color: #e2e8f0;">StatsBomb 事件流</div>
                <div class="data-card-sub">最完整的逐事件分析</div>
            </div>
            """, unsafe_allow_html=True)
        with fmt_cols[1]:
            st.markdown("""
            <div class="data-card" style="margin-bottom: 1rem;">
                <div class="data-card-label">灵活导入</div>
                <div class="data-card-value" style="font-size: 1.1rem; color: #e2e8f0;">FIFA 多文件CSV</div>
                <div class="data-card-sub">有几个传几个，缺数据自动降级</div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div class="data-card" style="margin-bottom: 1rem;">
                <div class="data-card-label">体能专用</div>
                <div class="data-card-value" style="font-size: 1.1rem; color: #e2e8f0;">Catapult 追踪数据</div>
                <div class="data-card-sub">体育科学体能分析</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div class="section-header">
            <span class="section-header-icon">🚀</span>
            <span class="section-header-title">使用流程</span>
        </div>
        """, unsafe_allow_html=True)
        
        steps_cols = st.columns(3)
        steps = [
            ("1", "上传文件", "拖拽PDF/CSV/ZIP到左侧上传框"),
            ("2", "选择模板", "完整 / 精简 / 教练版"),
            ("3", "自动分析", "识别格式 → 生成图表+洞察+报告"),
        ]
        for i, (num, title, desc) in enumerate(steps):
            with steps_cols[i]:
                st.markdown(f"""
                <div class="data-card" style="text-align: center;">
                    <div style="font-size: 2rem; font-weight: 800; color: #0d9488; margin-bottom: 0.5rem;">{num}</div>
                    <div style="font-weight: 600; color: #e2e8f0; margin-bottom: 0.25rem;">{title}</div>
                    <div class="data-card-sub">{desc}</div>
                </div>
                """, unsafe_allow_html=True)
        
        st.stop()

# ========== 分析流程 ==========
if analysis_mode == "球队追踪":
    # ===== 球队追踪模式 =====
    with st.spinner("正在加载多场比赛数据..."):
        temp_dir = tempfile.mkdtemp()
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        
        # 检查模块可用性
        if not _HAS_TEAM_TRACKER:
            st.error(f"❌ 球队追踪模块加载失败：{_TEAM_TRACKER_ERROR}")
            st.stop()
        
        if not _HAS_FIFA:
            st.error(f"❌ FIFA数据适配器不可用：{_FIFA_IMPORT_ERROR}")
            st.stop()
        
        # 处理上传文件：每个文件尝试解析为一场比赛
        csv_dirs = []
        match_idx = 0
        
        for f in uploaded_files:
            match_idx += 1
            match_dir = os.path.join(temp_dir, f"match_{match_idx}")
            os.makedirs(match_dir, exist_ok=True)
            
            fname_lower = f.name.lower()
            
            try:
                if fname_lower.endswith('.pdf'):
                    # PDF文件 → 先解析为CSV
                    if not _HAS_FIFA_PDF:
                        st.warning(f"⚠️ 跳过 {f.name}：PDF解析器不可用")
                        continue
                    pdf_path = os.path.join(match_dir, "match.pdf")
                    with open(pdf_path, "wb") as wf:
                        wf.write(f.getbuffer())
                    csv_dir = os.path.join(match_dir, "csv")
                    os.makedirs(csv_dir, exist_ok=True)
                    parse_result = parse_fifa_pdf(pdf_path, csv_dir)
                    if parse_result['success']:
                        csv_dirs.append(csv_dir)
                    else:
                        st.warning(f"⚠️ 跳过 {f.name}：PDF解析失败（{parse_result.get('error', '未知错误')[:40]}）")
                
                elif fname_lower.endswith('.zip'):
                    # ZIP文件 → 解压后判断
                    zip_path = os.path.join(match_dir, "uploaded.zip")
                    with open(zip_path, "wb") as wf:
                        wf.write(f.getbuffer())
                    extract_dir = os.path.join(match_dir, "extracted")
                    os.makedirs(extract_dir, exist_ok=True)
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        zf.extractall(extract_dir)
                    
                    # 找FIFA CSV目录
                    found = False
                    if is_fifa_csv_dir(extract_dir):
                        csv_dirs.append(extract_dir)
                        found = True
                    else:
                        for item in os.listdir(extract_dir):
                            sub_path = os.path.join(extract_dir, item)
                            if os.path.isdir(sub_path) and is_fifa_csv_dir(sub_path):
                                csv_dirs.append(sub_path)
                                found = True
                                break
                    if not found:
                        st.warning(f"⚠️ 跳过 {f.name}：未识别为FIFA比赛数据")
                
                elif fname_lower.endswith('.csv'):
                    # 单个CSV文件 → 先保存到目录，再判断是不是FIFA格式
                    # （多个CSV一起上传时，需要判断是不是同一场比赛的FIFA多文件）
                    # 这里简化处理：单个CSV不认为是一场完整FIFA比赛
                    st.warning(f"⚠️ 跳过 {f.name}：球队追踪需要完整比赛数据（PDF/ZIP/多文件CSV）")
                    continue
            
            except Exception as e:
                st.warning(f"⚠️ 处理 {f.name} 时出错：{str(e)[:50]}")
                continue
        
        # 特殊情况：多个CSV文件可能是同一场FIFA比赛的多文件
        # 重新处理：把所有CSV放到一个目录，判断是不是FIFA格式
        csv_files_only = [f for f in uploaded_files if f.name.lower().endswith('.csv')]
        if len(csv_files_only) >= 3 and len(csv_dirs) == 0:
            # 所有CSV放一起试试能不能组成一场FIFA比赛
            combined_dir = os.path.join(temp_dir, "combined_csv")
            os.makedirs(combined_dir, exist_ok=True)
            for f in csv_files_only:
                file_path = os.path.join(combined_dir, f.name)
                with open(file_path, "wb") as wf:
                    wf.write(f.getbuffer())
            if is_fifa_csv_dir(combined_dir):
                csv_dirs.append(combined_dir)
                st.info(f"✅ 检测到 {len(csv_files_only)} 个CSV为一场完整FIFA比赛")
        
        if len(csv_dirs) < 2:
            st.error(f"❌ 有效比赛数据不足（当前 {len(csv_dirs)} 场），球队追踪至少需要2场比赛。\n\n请上传更多FIFA比赛数据（PDF/ZIP格式最佳）。")
            st.stop()
        
        # 加载所有比赛
        match_data_list = load_multiple_matches(csv_dirs)
        
        if len(match_data_list) < 2:
            st.error("❌ 成功加载的比赛不足2场，请检查上传文件是否正确。")
            st.stop()
        
        # 检测共同球队
        common_teams = find_common_teams(match_data_list)
        
        if not common_teams:
            st.error("❌ 未找到在多场比赛中共同出现的球队。请确保上传的比赛中有同一支球队参加。")
            st.stop()
    
    # ===== 球队选择（侧边栏） =====
    with st.sidebar:
        st.divider()
        st.subheader("🏆 选择球队")
        target_team = st.selectbox(
            "要追踪的球队",
            common_teams,
            help="列出所有在多场比赛中出现的球队，按出场次数排序"
        )
        st.caption(f"共 {len(match_data_list)} 场比赛，{len(common_teams)} 支可追踪球队")
    
    # ===== 计算数据 =====
    with st.spinner(f"正在分析 {target_team} 的多场表现..."):
        overview = compute_team_overview(match_data_list, target_team)
        trends, match_labels = compute_trends(match_data_list, target_team)
        
        # 生成图表
        trend_chart_path = os.path.join(output_dir, "team_trend.png")
        attack_defense_chart_path = os.path.join(output_dir, "attack_defense_trend.png")
        
        try:
            plot_team_trend(trends, match_labels, trend_chart_path)
        except Exception as e:
            st.warning(f"⚠️ 趋势图生成失败：{e}")
            trend_chart_path = None
        
        try:
            plot_attack_defense_trend(trends, match_labels, attack_defense_chart_path)
        except Exception as e:
            st.warning(f"⚠️ 攻防对比图生成失败：{e}")
            attack_defense_chart_path = None
    
    # ===== 展示结果 =====
    render_section_header("🏆", f"{target_team} — 球队追踪总览", f"{overview.get('matches', 0)} 场比赛")
    
    # 概览卡片（第一排）
    ov_cols = st.columns(6)
    with ov_cols[0]:
        render_stat_card("场次", overview.get('matches', 0), f"{overview.get('wins', 0)}胜{overview.get('draws', 0)}平{overview.get('losses', 0)}负", home_color=True)
    with ov_cols[1]:
        render_stat_card("胜率", f"{overview.get('win_rate', 0):.1f}%", f"{overview.get('goal_diff', 0):+d} 净胜球", home_color=True)
    with ov_cols[2]:
        render_stat_card("总进球", overview.get('goals_for', 0), f"场均 {overview.get('goals_for', 0)/max(overview.get('matches', 1), 1):.1f}", home_color=True)
    with ov_cols[3]:
        render_stat_card("总失球", overview.get('goals_against', 0), f"场均 {overview.get('goals_against', 0)/max(overview.get('matches', 1), 1):.1f}", home_color=False)
    with ov_cols[4]:
        xg_per_game = overview.get('xg_total', 0) / max(overview.get('matches', 1), 1)
        render_stat_card("场均xG", f"{xg_per_game:.2f}", f"xG差 {overview.get('xg_diff', 0):+.2f}", home_color=True)
    with ov_cols[5]:
        avg_poss = overview.get('avg_possession', 0) or 0
        render_stat_card("场均控球", f"{avg_poss:.1f}%", f"传球成功率 {overview.get('avg_pass_accuracy', 0) or 0:.1f}%", home_color=True)
    
    # 趋势折线图
    render_section_header("📈", "趋势追踪", "Trend Analysis")
    if trend_chart_path and os.path.exists(trend_chart_path):
        show_chart_with_zoom(trend_chart_path, "球队多场表现趋势", zoom_level=1.0)
    else:
        st.info("暂无趋势图数据")
    
    # 攻防对比图
    render_section_header("⚔️", "攻防对比", "Attack vs Defense")
    if attack_defense_chart_path and os.path.exists(attack_defense_chart_path):
        show_chart_with_zoom(attack_defense_chart_path, "攻防对比趋势", zoom_level=1.0)
    else:
        st.info("暂无攻防对比数据")
    
    # 每场比赛结果列表
    render_section_header("📋", "比赛记录", "Match History")
    results = overview.get('results', [])
    if results:
        # 用表格展示每场比赛
        table_data = []
        for i, r in enumerate(results):
            result_color = {"胜": "#22c55e", "平": "#eab308", "负": "#ef4444"}.get(r['result'], "#94a3b8")
            table_data.append({
                "序号": i + 1,
                "对手": r['opponent'],
                "日期": r.get('match_date', ''),
                "比分": f"{r['goals_for']} - {r['goals_against']}",
                "结果": f"<span style='color:{result_color};font-weight:600'>{r['result']}</span>",
                "xG": f"{r['xg']:.2f}",
                "xGA": f"{r['xga']:.2f}",
                "控球率": f"{r['possession']:.1f}%" if r['possession'] else "-",
                "射门": r['shots'],
                "射正": r['shots_on_target'],
            })
        
        # 用自定义HTML表格展示
        table_html = """
        <div class="data-card" style="padding: 0; overflow: hidden;">
            <table style="width:100%; border-collapse: collapse; font-size: 0.875rem;">
                <thead>
                    <tr style="background: #0f172a; color: #f1f5f9;">
                        <th style="padding: 0.75rem 1rem; text-align: left; font-weight: 600; border-bottom: 2px solid #334155;">#</th>
                        <th style="padding: 0.75rem 1rem; text-align: left; font-weight: 600; border-bottom: 2px solid #334155;">对手</th>
                        <th style="padding: 0.75rem 1rem; text-align: center; font-weight: 600; border-bottom: 2px solid #334155;">比分</th>
                        <th style="padding: 0.75rem 1rem; text-align: center; font-weight: 600; border-bottom: 2px solid #334155;">结果</th>
                        <th style="padding: 0.75rem 1rem; text-align: center; font-weight: 600; border-bottom: 2px solid #334155;">xG</th>
                        <th style="padding: 0.75rem 1rem; text-align: center; font-weight: 600; border-bottom: 2px solid #334155;">xGA</th>
                        <th style="padding: 0.75rem 1rem; text-align: center; font-weight: 600; border-bottom: 2px solid #334155;">控球率</th>
                        <th style="padding: 0.75rem 1rem; text-align: center; font-weight: 600; border-bottom: 2px solid #334155;">射门</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for row in table_data:
            table_html += f"""
                    <tr style="border-bottom: 1px solid #1e293b;">
                        <td style="padding: 0.625rem 1rem; color: #94a3b8;">{row['序号']}</td>
                        <td style="padding: 0.625rem 1rem; color: #e2e8f0; font-weight: 500;">{row['对手']}</td>
                        <td style="padding: 0.625rem 1rem; text-align: center; color: #f1f5f9; font-weight: 600; font-variant-numeric: tabular-nums;">{row['比分']}</td>
                        <td style="padding: 0.625rem 1rem; text-align: center;">{row['结果']}</td>
                        <td style="padding: 0.625rem 1rem; text-align: center; color: #3b82f6; font-variant-numeric: tabular-nums;">{row['xG']}</td>
                        <td style="padding: 0.625rem 1rem; text-align: center; color: #f97316; font-variant-numeric: tabular-nums;">{row['xGA']}</td>
                        <td style="padding: 0.625rem 1rem; text-align: center; color: #0d9488;">{row['控球率']}</td>
                        <td style="padding: 0.625rem 1rem; text-align: center; color: #cbd5e1; font-variant-numeric: tabular-nums;">{row['射门']}</td>
                    </tr>
            """
        
        table_html += """
                </tbody>
            </table>
        </div>
        """
        st.markdown(table_html, unsafe_allow_html=True)
    
    st.caption(f"📊 数据来源：FIFA比赛报告（共 {len(match_data_list)} 场）")
    
    st.stop()

else:
    # ===== 单场分析模式（原有逻辑） =====
    with st.spinner("正在分析..."):
        temp_dir = tempfile.mkdtemp()
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
    
        is_fifa_data = False
        detected_format = "unknown"
    
        # ===== 智能识别格式并处理 =====
        if not uploaded_files or len(uploaded_files) == 0:
            st.error("请先上传数据文件")
            st.stop()
    
        # 收集所有文件：按扩展名分类
        pdf_files = [f for f in uploaded_files if f.name.lower().endswith('.pdf')]
        zip_files = [f for f in uploaded_files if f.name.lower().endswith('.zip')]
        csv_files = [f for f in uploaded_files if f.name.lower().endswith('.csv')]
    
        # ---- 情况1：PDF文件 → FIFA PDF模式 ----
        if len(pdf_files) > 0:
            detected_format = "fifa_pdf"
            if not _HAS_FIFA_PDF or not _HAS_FIFA:
                error_msgs = []
                if not _HAS_FIFA:
                    error_msgs.append(f"FIFA数据适配器加载失败：{_FIFA_IMPORT_ERROR}")
                if not _HAS_FIFA_PDF:
                    if not _PDFPLUMBER_AVAILABLE:
                        error_msgs.append(
                            "**缺少PDF解析依赖：pdfplumber**\n\n"
                            "请在终端运行以下命令安装：\n\n"
                            "```\npip install pdfplumber\n```\n\n"
                            "安装完成后刷新页面即可使用PDF解析功能。"
                        )
                    else:
                        error_msgs.append(f"PDF解析器加载失败：{_FIFA_PDF_IMPORT_ERROR}")
                st.error("❌ **PDF解析功能不可用**\n\n" + "\n\n---\n\n".join(error_msgs))
                st.stop()
        
            # 保存第一个PDF（只处理一个）
            pdf_file = pdf_files[0]
            pdf_path = os.path.join(temp_dir, "match_report.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_file.getbuffer())
        
            # 解析PDF
            csv_dir = os.path.join(temp_dir, "fifa_csv")
            os.makedirs(csv_dir, exist_ok=True)
            parse_result = parse_fifa_pdf(pdf_path, csv_dir)
        
            if not parse_result['success']:
                st.error(f"❌ **PDF解析失败**\n\n{parse_result.get('error', '未知错误')}\n\n请确认上传的是FIFA Training Centre比赛报告PDF。")
                st.stop()
        
            # 加载数据
            try:
                df, info, stats = load_fifa_from_csv(csv_dir, match_name)
                is_fifa_data = True
            except Exception as e:
                st.error(f"数据加载失败：{e}")
                st.stop()
    
        # ---- 情况2：ZIP文件 → 先解压再判断 ----
        elif len(zip_files) > 0:
            # 解压ZIP
            zip_path = os.path.join(temp_dir, "uploaded.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_files[0].getbuffer())
        
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
        
            # 判断是否为FIFA CSV目录
            csv_dir = extract_dir
            if _HAS_FIFA and not is_fifa_csv_dir(csv_dir):
                for item in os.listdir(csv_dir):
                    sub_path = os.path.join(csv_dir, item)
                    if os.path.isdir(sub_path) and is_fifa_csv_dir(sub_path):
                        csv_dir = sub_path
                        break
        
            if _HAS_FIFA and is_fifa_csv_dir(csv_dir):
                detected_format = "fifa_zip"
                try:
                    df, info, stats = load_fifa_from_csv(csv_dir, match_name)
                    is_fifa_data = True
                except Exception as e:
                    # FIFA加载失败，降级为单文件CSV处理
                    st.warning(f"FIFA格式加载失败（{str(e)[:40]}），已自动降级为单文件模式")
                    detected_format = "csv"
                    csv_list = [f for f in os.listdir(extract_dir) if f.lower().endswith('.csv')]
                    if not csv_list:
                        st.error("ZIP中未找到可用CSV文件")
                        st.stop()
                    csv_path = os.path.join(extract_dir, csv_list[0])
                    try:
                        df, info = auto_load(csv_path, match_name=match_name)
                        stats = compute_match_stats(df, info)
                    except Exception as e2:
                        st.error(f"数据加载失败：{e2}")
                        st.stop()
            else:
                # 不是FIFA，当单文件CSV处理（找第一个CSV）
                detected_format = "csv"
                csv_list = [f for f in os.listdir(extract_dir) if f.lower().endswith('.csv')]
                if not csv_list:
                    st.error("ZIP中未找到CSV文件")
                    st.stop()
                csv_path = os.path.join(extract_dir, csv_list[0])
                try:
                    df, info = auto_load(csv_path, match_name=match_name)
                    stats = compute_match_stats(df, info)
                except Exception as e:
                    st.error(f"数据加载失败：{e}")
                    st.stop()
    
        # ---- 情况3：多个CSV文件 → 先判断是不是FIFA一套 ----
        elif len(csv_files) > 1:
            # 先用文件名快速判断是否为FIFA格式（无需保存文件即可判断）
            csv_filenames = [f.name for f in csv_files]
            is_fifa_multi = _HAS_FIFA and detect_fifa_from_filenames(csv_filenames)
        
            # 保存到临时目录
            csv_dir = os.path.join(temp_dir, "fifa_csv")
            os.makedirs(csv_dir, exist_ok=True)
            for f in csv_files:
                file_path = os.path.join(csv_dir, f.name)
                with open(file_path, "wb") as wf:
                    wf.write(f.getbuffer())
        
            if is_fifa_multi:
                detected_format = "fifa_multi"
                try:
                    df, info, stats = load_fifa_from_csv(csv_dir, match_name)
                    is_fifa_data = True
                except Exception as e:
                    # FIFA加载失败，降级为单文件CSV处理
                    st.warning(f"FIFA格式加载失败（{str(e)[:40]}），已自动降级为单文件模式")
                    detected_format = "csv_multi_first"
                    first_csv = os.path.join(csv_dir, csv_files[0].name)
                    try:
                        result = auto_load(first_csv, match_name=match_name)
                        df, info = result
                        stats = compute_match_stats(df, info)
                    except Exception as e2:
                        st.error(f"数据加载失败：{e2}")
                        st.stop()
            else:
                # 不是FIFA多文件，取第一个CSV按单文件处理
                detected_format = "csv_multi_first"
                first_csv = os.path.join(csv_dir, csv_files[0].name)
                try:
                    result = auto_load(first_csv, match_name=match_name)
                    df, info = result
                    stats = compute_match_stats(df, info)
                except Exception as e:
                    st.error(f"数据加载失败：{e}")
                    st.stop()
    
        # ---- 情况4：单个CSV文件 → 自动识别 ----
        elif len(csv_files) == 1:
            detected_format = "csv_single"
            csv_path = os.path.join(temp_dir, "match_data.csv")
            with open(csv_path, "wb") as f:
                f.write(csv_files[0].getbuffer())
        
            try:
                df, info = auto_load(csv_path, match_name=match_name)
                stats = compute_match_stats(df, info)
            except Exception as e:
                st.error(f"数据加载失败：{e}")
                st.stop()
    
        else:
            st.error("未识别到有效数据文件，请上传PDF、CSV或ZIP格式")
            st.stop()

        # 3. 生成洞察
        if is_fifa_data and _HAS_FIFA:
            # FIFA模式：使用更丰富的FIFA专属战术洞察
            tactical_insights = generate_tactical_insights(stats, info)
            attack_insights = tactical_insights.get('attack', [])
            defense_insights = tactical_insights.get('defense', [])
            # 合并为扁平列表供报告引擎使用
            insights = attack_insights + defense_insights
        else:
            # 通用模式：使用标准洞察生成
            insights = generate_insights(stats, df, info)
            attack_insights = []
            defense_insights = []

        # 4. 生成图表（逐个图表try-except，单个失败不影响其他）
        chart_paths = {}
        try:
            chart_paths = generate_all_charts(df, info, stats, output_dir=output_dir)
        except Exception as e:
            st.warning(f"⚠️ 部分图表生成失败：{e}")
    
        # 5. 生成报告
        template_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'templates', f'{template_name}.json'
        )
        template = ReportTemplate(template_path)
    
        text_report = ""
        html_path = os.path.join(output_dir, 'report.html')
        try:
            text_report = generate_text_report(stats, insights, info, template)
            generate_html_report(stats, insights, info, chart_paths, template, output_path=html_path)
        except Exception as e:
            st.warning(f"⚠️ 报告生成异常：{e}")
            text_report = f"报告生成异常：{e}"

    # ========== 展示结果 ==========
    teams = list(stats.keys())
    if len(teams) >= 2:
        t1, t2 = teams[0], teams[1]
        s1, s2 = stats[t1], stats[t2]

        # ===== 赛事横幅 =====
        try:
            formation1 = s1.get('formation', '')
            formation2 = s2.get('formation', '')
            competition = match_name
            match_date = info.get('match_date', '') if info else ''
            render_match_banner(
                team_home=t1,
                team_away=t2,
                score_home=s1['goals'],
                score_away=s2['goals'],
                formation_home=formation1,
                formation_away=formation2,
                competition=competition,
                match_date=match_date
            )
        except Exception:
            # 降级：简单标题展示
            st.markdown(f"### {t1} {s1['goals']} — {s2['goals']} {t2}")
    
        # 数据源标识
        if is_fifa_data:
            format_labels = {
                'fifa_pdf': 'FIFA比赛报告（PDF自动解析）',
                'fifa_zip': 'FIFA比赛报告（ZIP导入）',
                'fifa_multi': 'FIFA比赛报告（多文件CSV导入）',
                'fifa_single': 'FIFA比赛报告（单文件CSV）',
            }
            label = format_labels.get(detected_format, 'FIFA比赛报告')
            st.caption(f"📊 数据来源：{label}")
        else:
            st.caption("📊 数据来源：事件流数据（完整功能）")

        # ===== 数据概览卡片 + PDF下载 =====
        render_section_header("📊", "数据概览", "Key Stats")
    
        # 第一排：6个核心指标卡片 + PDF下载按钮
        overview_cols = st.columns([1, 1, 1, 1, 1, 1, 1.2])
    
        # 卡片1：控球率
        with overview_cols[0]:
            try:
                render_stat_card(
                    "控球率",
                    f"{s1.get('possession_pct', 0):.0f}%",
                    f"vs {s2.get('possession_pct', 0):.0f}%",
                    home_color=True
                )
            except Exception:
                render_stat_card("控球率", "-", "数据不足")
    
        # 卡片2：射门
        with overview_cols[1]:
            try:
                render_stat_card(
                    "射门 / 射正",
                    f"{s1['shots_total']}/{s1['shots_on_target']}",
                    f"vs {s2['shots_total']}/{s2['shots_on_target']}",
                    home_color=True
                )
            except Exception:
                render_stat_card("射门", "-", "数据不足")
    
        # 卡片3：xG
        with overview_cols[2]:
            try:
                render_stat_card(
                    "预期进球 xG",
                    f"{s1['xg']:.2f}",
                    f"vs {s2['xg']:.2f}",
                    home_color=True
                )
            except Exception:
                render_stat_card("xG", "-", "数据不足")
    
        # 卡片4：传球成功率
        with overview_cols[3]:
            try:
                render_stat_card(
                    "传球成功率",
                    f"{s1['pass_accuracy']:.1f}%",
                    f"vs {s2['pass_accuracy']:.1f}%",
                    home_color=True
                )
            except Exception:
                render_stat_card("传球成功率", "-", "数据不足")
    
        # 卡片5：关键传球
        with overview_cols[4]:
            try:
                render_stat_card(
                    "关键传球",
                    str(s1['key_passes']),
                    f"vs {s2['key_passes']}",
                    home_color=True
                )
            except Exception:
                render_stat_card("关键传球", "-", "数据不足")
    
        # 卡片6：角球
        with overview_cols[5]:
            try:
                render_stat_card(
                    "角球",
                    str(s1['corners']),
                    f"vs {s2['corners']}",
                    home_color=True
                )
            except Exception:
                render_stat_card("角球", "-", "数据不足")
    
        # PDF下载卡片
        with overview_cols[6]:
            if _HAS_PDF_REPORT:
                try:
                    # 延迟导入，节省启动内存
                    generate_pdf_report, get_pdf_filename, import_err = _get_pdf_generator()
                    if import_err:
                        raise Exception(import_err)
                
                    pdf_filename = get_pdf_filename(teams[0], teams[1]) if len(teams) >= 2 else f"{match_name}_战术分析报告.pdf"
                    pdf_path = os.path.join(temp_dir, pdf_filename)
                    # 尝试生成PDF（放在spinner内）
                    generate_pdf_report(df, info, stats, pdf_path, chart_dir=temp_dir)
                    if os.path.exists(pdf_path):
                        with open(pdf_path, 'rb') as f:
                            pdf_data = f.read()
                        st.markdown("""
                        <div class="pdf-download-card">
                            <div class="pdf-download-title">📄 完整战术报告</div>
                            <div class="pdf-download-desc">A4格式 · 含所有图表与洞察</div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.download_button(
                            "下载 PDF 报告",
                            data=pdf_data,
                            file_name=pdf_filename,
                            mime="application/pdf",
                            use_container_width=True,
                            type="primary"
                        )
                except Exception as e:
                    st.markdown(f"""
                    <div class="data-card">
                        <div class="data-card-label">PDF报告</div>
                        <div class="data-card-value" style="font-size: 1rem; color: #64748b;">生成失败</div>
                        <div class="data-card-sub">{str(e)[:30]}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="data-card">
                    <div class="data-card-label">PDF报告</div>
                    <div class="data-card-value" style="font-size: 1rem; color: #64748b;">未启用</div>
                    <div class="data-card-sub">缺少reportlab依赖</div>
                </div>
                """, unsafe_allow_html=True)

        # ===== 核心数据对比表 =====
        render_section_header("📈", "核心数据对比")
    
        import pandas as pd
        try:
            stats_df = pd.DataFrame({
                '指标': ['阵型', '控球率', '传球成功率', '射门/射正', '进球', 'xG', '关键传球', '角球', '犯规'],
                t1: [
                    s1['formation'],
                    f"{s1.get('possession_pct',0):.1f}%",
                    f"{s1['pass_accuracy']:.1f}%",
                    f"{s1['shots_total']}/{s1['shots_on_target']}",
                    str(s1['goals']),
                    f"{s1['xg']:.2f}",
                    str(s1['key_passes']),
                    str(s1['corners']),
                    str(s1['fouls']),
                ],
                t2: [
                    s2['formation'],
                    f"{s2.get('possession_pct',0):.1f}%",
                    f"{s2['pass_accuracy']:.1f}%",
                    f"{s2['shots_total']}/{s2['shots_on_target']}",
                    str(s2['goals']),
                    f"{s2['xg']:.2f}",
                    str(s2['key_passes']),
                    str(s2['corners']),
                    str(s2['fouls']),
                ],
            })
            st.dataframe(stats_df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"核心数据表展示异常：{e}")

        # ===== 进攻分析板块 =====
        render_section_header("⚔️", "进攻分析", "Attack Analysis")
        st.caption("💡 每张图表下方可点击放大查看")
    
        # 第一排：射门位置图 + 传球网络图
        chart_display_row1 = [
            ('shot_map', '射门位置图'),
            ('pass_network', '传球网络图'),
        ]
        row1_cols = st.columns(2)
        for idx, (chart_id, chart_title) in enumerate(chart_display_row1):
            chart_file = chart_paths.get(chart_id)
            with row1_cols[idx]:
                show_chart_with_zoom(chart_file, chart_title)
    
        # 第二排：xG累积曲线 + 射门数据对比
        chart_display_row2 = [
            ('xg_flow', 'xG累积曲线'),
            ('shot_comparison', '射门数据对比'),
        ]
        row2_cols = st.columns(2)
        for idx, (chart_id, chart_title) in enumerate(chart_display_row2):
            chart_file = chart_paths.get(chart_id)
            with row2_cols[idx]:
                show_chart_with_zoom(chart_file, chart_title)

        # ===== 防守分析板块 =====
        render_section_header("🛡️", "防守分析", "Defense Analysis")
    
        chart_display_def = [
            ('pressure_heatmap', '防守热力图'),
            ('possession_timeline', '控球时间线'),
        ]
        def_cols = st.columns(2)
        for idx, (chart_id, chart_title) in enumerate(chart_display_def):
            chart_file = chart_paths.get(chart_id)
            with def_cols[idx]:
                show_chart_with_zoom(chart_file, chart_title)

        # ===== 综合数据板块 =====
        render_section_header("📊", "综合数据对比", "Stats Overview")
    
        chart_display_stats = [
            ('stats_bar', '核心数据对比柱状图'),
        ]
        stats_cols = st.columns(1)
        for idx, (chart_id, chart_title) in enumerate(chart_display_stats):
            chart_file = chart_paths.get(chart_id)
            with stats_cols[idx]:
                show_chart_with_zoom(chart_file, chart_title)

        # ===== FIFA专属战术分析板块 =====
        if is_fifa_data:
            render_section_header("🎯", "FIFA专属战术分析", "FIFA Tactical Insights")
            st.caption("基于FIFA比赛报告深度数据的专属战术图表")
        
            # 缺文件提示
            if info and info.get('fifa_extra', {}).get('missing_files'):
                missing = info['fifa_extra']['missing_files']
                st.info(f"📋 提示：缺少 {len(missing)} 个非核心数据文件（{', '.join(missing)}），对应图表将自动跳过")
        
            # 战术风格雷达图（大图单列）
            chart_display_radar = [('tactical_radar', '战术风格雷达图')]
            radar_cols = st.columns(1)
            for idx, (chart_id, chart_title) in enumerate(chart_display_radar):
                chart_file = chart_paths.get(chart_id)
                with radar_cols[idx]:
                    show_chart_with_zoom(chart_file, chart_title)
        
            # 防线穿透 + 传中战术
            chart_display_tactical = [
                ('line_breaks', '防线穿透分析'),
                ('cross_tactics', '传中战术分析'),
            ]
            tactical_cols = st.columns(2)
            for idx, (chart_id, chart_title) in enumerate(chart_display_tactical):
                chart_file = chart_paths.get(chart_id)
                with tactical_cols[idx]:
                    show_chart_with_zoom(chart_file, chart_title)
        
            # 体能五分区图
            chart_display_phys = [('physical_zones', '体能五分区图')]
            phys_cols = st.columns(1)
            for idx, (chart_id, chart_title) in enumerate(chart_display_phys):
                chart_file = chart_paths.get(chart_id)
                with phys_cols[idx]:
                    show_chart_with_zoom(chart_file, chart_title)

        # ===== 战术洞察板块 =====
        render_section_header("🔍", "战术洞察", "Tactical Insights")
    
        if is_fifa_data and attack_insights and defense_insights:
            # FIFA模式：分进攻端和防守端展示
            ins_cols = st.columns(2)
        
            with ins_cols[0]:
                st.markdown("#### ⚔ 进攻端洞察")
                for ins in attack_insights:
                    priority = str(ins.get('priority', '3'))
                    priority_icon = {"1": "🔴", "2": "🟡", "3": "⚪"}.get(priority, "·")
                    st.markdown(f"""
                    <div class="insight-card priority-{priority}">
                        <div style="font-weight: 600; color: #f1f5f9; margin-bottom: 0.25rem;">
                            {priority_icon} <span style="color: #94a3b8; font-size: 0.8rem; font-weight: 500;">[{ins['category']}]</span>
                        </div>
                        <div style="color: #e2e8f0; font-size: 0.9rem;">{ins['text']}</div>
                        {f'<div style="color: #94a3b8; font-size: 0.8rem; margin-top: 0.5rem;">{ins["suggestion"]}</div>' if ins.get('suggestion') else ''}
                    </div>
                    """, unsafe_allow_html=True)
        
            with ins_cols[1]:
                st.markdown("#### 🛡 防守端洞察")
                for ins in defense_insights:
                    priority = str(ins.get('priority', '3'))
                    priority_icon = {"1": "🔴", "2": "🟡", "3": "⚪"}.get(priority, "·")
                    st.markdown(f"""
                    <div class="insight-card priority-{priority}">
                        <div style="font-weight: 600; color: #f1f5f9; margin-bottom: 0.25rem;">
                            {priority_icon} <span style="color: #94a3b8; font-size: 0.8rem; font-weight: 500;">[{ins['category']}]</span>
                        </div>
                        <div style="color: #e2e8f0; font-size: 0.9rem;">{ins['text']}</div>
                        {f'<div style="color: #94a3b8; font-size: 0.8rem; margin-top: 0.5rem;">{ins["suggestion"]}</div>' if ins.get('suggestion') else ''}
                    </div>
                    """, unsafe_allow_html=True)
        else:
            # 通用模式：统一列表展示
            for ins in insights:
                priority = str(ins.get('priority', '3'))
                priority_icon = {"1": "🔴", "2": "🟡", "3": "⚪"}.get(priority, "·")
                st.markdown(f"""
                <div class="insight-card priority-{priority}">
                    <div style="font-weight: 600; color: #0f172a; margin-bottom: 0.25rem;">
                        {priority_icon} <span style="color: #64748b; font-size: 0.8rem; font-weight: 500;">[{ins['category']}]</span>
                    </div>
                    <div style="color: #334155; font-size: 0.9rem;">{ins['text']}</div>
                    {f'<div style="color: #64748b; font-size: 0.8rem; margin-top: 0.5rem;">💡 {ins["suggestion"]}</div>' if ins.get('suggestion') else ''}
                </div>
                """, unsafe_allow_html=True)

        # ===== 球员数据板块 =====
        render_section_header("👥", "球员数据", "Player Stats")
    
        player_cols = st.columns(2)
        for i, team in enumerate(teams):
            s = stats[team]
            team_color = "#0d9488" if i == 0 else "#f97316"
            with player_cols[i]:
                st.markdown(f"""
                <div style="font-weight: 600; color: {team_color}; margin-bottom: 0.75rem; font-size: 1rem;">
                    🏃 {team}
                </div>
                """, unsafe_allow_html=True)
            
                with st.expander(f"传球TOP5"):
                    if not s['pass_leaders'].empty:
                        for player, cnt in s['pass_leaders'].items():
                            st.markdown(f"- **{player}**: {cnt}次成功传球")
                    else:
                        st.info("无数据")
            
                with st.expander(f"射门TOP3"):
                    if not s['shot_leaders'].empty:
                        for player, cnt in s['shot_leaders'].items():
                            st.markdown(f"- **{player}**: {cnt}次射门")
                    else:
                        st.info("无数据")
            
                with st.expander(f"xG TOP3"):
                    if not s['xg_leaders'].empty:
                        for player, xg_val in s['xg_leaders'].items():
                            st.markdown(f"- **{player}**: {xg_val:.2f} xG")
                    else:
                        st.info("无数据")

        # ===== 下载报告板块 =====
        render_section_header("📥", "下载报告", "Downloads")
    
        # 其他格式（PDF已在顶部数据概览区提供主入口）
        dl_cols = st.columns(3)

        with dl_cols[0]:
            st.download_button(
                "📝 文字报告 (TXT)",
                data=text_report,
                file_name=f"{match_name}_报告.txt",
                mime="text/plain",
                use_container_width=True
            )

        with dl_cols[1]:
            if os.path.exists(html_path):
                with open(html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                st.download_button(
                    "🌐 HTML报告",
                    data=html_content,
                    file_name=f"{match_name}_报告.html",
                    mime="text/html",
                    use_container_width=True
                )

        with dl_cols[2]:
            # 打包所有图片为zip
            zip_path = os.path.join(temp_dir, "charts.zip")
            with zipfile.ZipFile(zip_path, 'w') as zf:
                for chart_id, chart_file in chart_paths.items():
                    if chart_file and os.path.exists(chart_file):
                        zf.write(chart_file, os.path.basename(chart_file))
            with open(zip_path, 'rb') as f:
                st.download_button(
                    "🖼️ 图表打包 (ZIP)",
                    data=f.read(),
                    file_name=f"{match_name}_图表.zip",
                    mime="application/zip",
                    use_container_width=True
                )
