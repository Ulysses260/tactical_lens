"""
app.py — 战术透镜 Streamlit 网页版
启动：streamlit run app.py

v5 更新说明：
- 新增「FIFA比赛报告(PDF)」直接上传功能 — 最优体验，传一个PDF就完事
- 新增FIFA PDF解析器 (fifa_pdf_parser.py)，自动解析12个数据表
- 数据格式选项顺序：FIFA PDF > FIFA ZIP > 单文件CSV
- 默认选中FIFA PDF
- 解析失败时友好提示，不崩溃
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
from visualizer import generate_all_charts
from report_engine import generate_text_report, generate_html_report, ReportTemplate

# 尝试导入FIFA适配器
try:
    from fifa_adapter import load_fifa_from_csv, is_fifa_csv_dir
    _HAS_FIFA = True
except ImportError:
    _HAS_FIFA = False

# 尝试导入FIFA PDF解析器
try:
    from fifa_pdf_parser import parse_fifa_pdf
    _HAS_FIFA_PDF = True
except ImportError:
    _HAS_FIFA_PDF = False
    _FIFA_PDF_IMPORT_ERROR = None
    try:
        import pdfplumber  # noqa: F401
    except ImportError as e:
        _FIFA_PDF_IMPORT_ERROR = f"缺少pdfplumber依赖: {e}"


# ========== 页面配置 ==========
st.set_page_config(
    page_title="战术透镜",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 深色主题CSS ==========
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
    }
    /* 深色主题增强 */
    .stApp {
        background-color: #0d1117;
    }
    /* 数据表格深色主题 */
    .stDataFrame {
        background-color: #161b22;
    }
    /* 放大按钮样式 */
    .zoom-expander summary {
        color: #4da6ff;
        font-size: 0.85rem;
        cursor: pointer;
    }
    .zoom-expander summary:hover {
        color: #00f5c4;
    }
    /* 标题颜色 */
    h1, h2, h3 {
        color: #e6edf3 !important;
    }
    /* 侧边栏 */
    .css-1d391kg {
        background-color: #161b22;
    }
    /* 比分展示 */
    .score-display {
        text-align: center;
        padding: 20px 0;
    }
    .score-team1 {
        font-size: 24px;
        color: #00f5c4;
        font-weight: bold;
    }
    .score-team2 {
        font-size: 24px;
        color: #4da6ff;
        font-weight: bold;
    }
    .score-divider {
        font-size: 24px;
        color: #8b949e;
        margin: 0 10px;
    }
    .score-sub {
        color: #8b949e;
        margin-top: 8px;
    }
    /* PDF解析进度提示 */
    .pdf-parse-info {
        color: #8b949e;
        font-size: 0.85rem;
        margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)


# ========== 侧边栏 ==========
with st.sidebar:
    st.title("⚽ 战术透镜")
    st.caption("v5 — 比赛分析报告生成器")
    st.divider()

    st.subheader("📂 上传数据")
    
    # ===== 智能上传：一个框搞定所有格式 =====
    # 支持多文件，自动识别格式（FIFA PDF / FIFA CSV / StatsBomb / Catapult）
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

    template_map = {
        "default - 完整报告": "default",
        "concise - 精简速报": "concise",
        "coach - 教练版": "coach",
    }
    template_name = template_map[template_choice]

    st.divider()

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
    
    # 缩略图展示
    st.image(chart_path, caption=chart_title, use_container_width=True)
    
    # 放大查看（折叠面板）
    with st.expander(f"🔍 点击放大查看 — {chart_title}"):
        st.image(chart_path, caption=chart_title, use_container_width=True, clamp=False)
        st.caption("💡 提示：右键图片可保存或在新标签页中查看原图")


# ========== 主区域 ==========
st.title("⚽ 战术透镜 — 比赛分析报告")

# 判断是否有上传
has_data = uploaded_files is not None and len(uploaded_files) > 0

if not has_data:
    st.info("👈 拖拽文件到左侧上传框，自动识别格式，开始分析")
    st.markdown("""
    ---
    ### 支持的数据格式

    | 格式 | 说明 | 特点 |
    |------|------|------|
    | **FIFA比赛报告PDF** ⭐ | FIFA官方PDF直接上传，自动解析 | 一个PDF = 12项完整数据 = 11张图表 |
    | **FIFA多文件CSV** | FIFA导出的CSV文件，有几个传几个 | 缺数据的图表自动降级，不报错 |
    | **StatsBomb** | 专业赛事事件数据 | 最完整的逐事件分析 |
    | **Catapult** | 体育科学追踪数据 | 体能分析专用 |
    | **ZIP打包** | 任意格式打包上传 | 自动解压识别 |

    ### 使用流程
    1. 拖拽文件到左侧上传框（PDF / CSV / ZIP 都可以）
    2. 选择报告模板（完整 / 精简 / 教练版）
    3. 自动识别格式 → 生成图表 + 洞察 + 报告
    
    ### ⭐ 最推荐：FIFA PDF直接传
    拿到FIFA Training Centre比赛报告PDF，直接拖进来：
    - 自动解析比赛信息、阵容、射门、传中、防守、体能等12项数据
    - 生成战术风格雷达图、防线穿透分析等11张图表
    - 无需手动转换、无需打包、无需选格式
    """)
    st.stop()

# ========== 分析流程 ==========
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
            st.error(f"❌ PDF解析不可用：{_FIFA_PDF_IMPORT_ERROR if not _HAS_FIFA_PDF else 'FIFA适配器未加载'}")
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
                st.error(f"数据加载失败：{e}")
                st.stop()
        else:
            # 不是FIFA，当单文件CSV处理（找第一个CSV）
            detected_format = "csv"
            csv_list = [f for f in os.listdir(extract_dir) if f.lower().endswith('.csv')]
            if not csv_list:
                st.error("ZIP中未找到CSV文件")
                st.stop()
            csv_path = os.path.join(extract_dir, csv_list[0])
            result = auto_load(csv_path, match_name=match_name)
            if len(result) == 3:
                df, info, stats = result
                is_fifa_data = True
            else:
                df, info = result
                stats = compute_match_stats(df, info)
    
    # ---- 情况3：多个CSV文件 → 先判断是不是FIFA一套 ----
    elif len(csv_files) > 1:
        # 保存到临时目录
        csv_dir = os.path.join(temp_dir, "fifa_csv")
        os.makedirs(csv_dir, exist_ok=True)
        for f in csv_files:
            file_path = os.path.join(csv_dir, f.name)
            with open(file_path, "wb") as wf:
                wf.write(f.getbuffer())
        
        # 判断是否为FIFA格式
        if _HAS_FIFA and is_fifa_csv_dir(csv_dir):
            detected_format = "fifa_multi"
            try:
                df, info, stats = load_fifa_from_csv(csv_dir, match_name)
                is_fifa_data = True
            except Exception as e:
                st.error(f"数据加载失败：{e}")
                st.stop()
        else:
            # 不是FIFA多文件，取第一个CSV处理
            detected_format = "csv_multi_first"
            first_csv = os.path.join(csv_dir, csv_files[0].name)
            result = auto_load(first_csv, match_name=match_name)
            if len(result) == 3:
                df, info, stats = result
                is_fifa_data = True
            else:
                df, info = result
                stats = compute_match_stats(df, info)
    
    # ---- 情况4：单个CSV文件 → 自动识别 ----
    elif len(csv_files) == 1:
        detected_format = "csv_single"
        csv_path = os.path.join(temp_dir, "match_data.csv")
        with open(csv_path, "wb") as f:
            f.write(csv_files[0].getbuffer())
        
        try:
            result = auto_load(csv_path, match_name=match_name)
            if len(result) == 3:
                df, info, stats = result
                is_fifa_data = True
                detected_format = "fifa_single"
            else:
                df, info = result
                stats = compute_match_stats(df, info)
        except Exception as e:
            st.error(f"数据加载失败：{e}")
            st.stop()
    
    else:
        st.error("未识别到有效数据文件，请上传PDF、CSV或ZIP格式")
        st.stop()

    # 3. 生成洞察
    insights = generate_insights(stats, df, info)

    # 4. 生成图表
    chart_paths = generate_all_charts(df, info, stats, output_dir=output_dir)

    # 5. 生成报告
    template_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'templates', f'{template_name}.json'
    )
    template = ReportTemplate(template_path)
    text_report = generate_text_report(stats, insights, info, template)
    html_path = os.path.join(output_dir, 'report.html')
    generate_html_report(stats, insights, info, chart_paths, template, output_path=html_path)

# ========== 展示结果 ==========
teams = list(stats.keys())
if len(teams) >= 2:
    t1, t2 = teams[0], teams[1]
    s1, s2 = stats[t1], stats[t2]

    # 比分
    st.markdown(f"""
    <div class="score-display">
        <span class="score-team1">{t1} {s1['goals']}</span>
        <span class="score-divider">—</span>
        <span class="score-team2">{s2['goals']} {t2}</span>
        <div class="score-sub">{match_name}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # 数据源标识（智能识别结果）
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

    # 核心数据表
    st.subheader("📊 核心数据")
    import pandas as pd
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

    # 图表展示 — 第一排（2列，大图）
    st.subheader("📈 战术图表")
    st.caption("💡 每张图表下方可点击放大查看")
    
    chart_display_row1 = [
        ('shot_map', '射门位置图'),
        ('pass_network', '传球网络图'),
    ]
    row1_cols = st.columns(2)
    for idx, (chart_id, chart_title) in enumerate(chart_display_row1):
        chart_file = chart_paths.get(chart_id)
        with row1_cols[idx]:
            show_chart_with_zoom(chart_file, chart_title)
    
    # 图表展示 — 第二排（2列）
    chart_display_row2 = [
        ('xg_flow', 'xG累积曲线'),
        ('pressure_heatmap', '防守热力图'),
    ]
    row2_cols = st.columns(2)
    for idx, (chart_id, chart_title) in enumerate(chart_display_row2):
        chart_file = chart_paths.get(chart_id)
        with row2_cols[idx]:
            show_chart_with_zoom(chart_file, chart_title)
    
    # 图表展示 — 第三排（3列，小图）
    chart_display_row3 = [
        ('shot_comparison', '射门数据对比'),
        ('possession_timeline', '控球时间线'),
        ('stats_bar', '核心数据对比'),
    ]
    row3_cols = st.columns(3)
    for idx, (chart_id, chart_title) in enumerate(chart_display_row3):
        chart_file = chart_paths.get(chart_id)
        with row3_cols[idx]:
            show_chart_with_zoom(chart_file, chart_title)

    # ===== FIFA专属P0图表（仅FIFA模式展示） =====
    if is_fifa_data:
        st.subheader("🎯 FIFA专属战术分析")
        st.caption("基于FIFA比赛报告深度数据的专属战术图表")
        
        # FIFA图表 — 第四排（1列，战术雷达大图）
        chart_display_row4 = [
            ('tactical_radar', '战术风格雷达图'),
        ]
        row4_cols = st.columns(1)
        for idx, (chart_id, chart_title) in enumerate(chart_display_row4):
            chart_file = chart_paths.get(chart_id)
            with row4_cols[idx]:
                show_chart_with_zoom(chart_file, chart_title)
        
        # FIFA图表 — 第五排（2列）
        chart_display_row5 = [
            ('line_breaks', '防线穿透分析'),
            ('cross_tactics', '传中战术分析'),
        ]
        row5_cols = st.columns(2)
        for idx, (chart_id, chart_title) in enumerate(chart_display_row5):
            chart_file = chart_paths.get(chart_id)
            with row5_cols[idx]:
                show_chart_with_zoom(chart_file, chart_title)
        
        # FIFA图表 — 第六排（1列，体能大图）
        chart_display_row6 = [
            ('physical_zones', '体能五分区图'),
        ]
        row6_cols = st.columns(1)
        for idx, (chart_id, chart_title) in enumerate(chart_display_row6):
            chart_file = chart_paths.get(chart_id)
            with row6_cols[idx]:
                show_chart_with_zoom(chart_file, chart_title)

    # 战术洞察
    st.subheader("🔍 战术洞察")
    for ins in insights:
        priority_icon = {"1": "🔴", "2": "🟡", "3": "⚪"}.get(str(ins['priority']), "·")
        st.markdown(f"**{priority_icon} [{ins['category']}]** {ins['text']}")
        if ins.get('suggestion'):
            st.caption(f"→ {ins['suggestion']}")

    # 球员排行
    st.subheader("👥 球员数据")
    player_cols = st.columns(2)
    for i, team in enumerate(teams):
        s = stats[team]
        with player_cols[i]:
            with st.expander(f"🏃 {team} 传球TOP5"):
                if not s['pass_leaders'].empty:
                    for player, cnt in s['pass_leaders'].items():
                        st.markdown(f"- **{player}**: {cnt}次成功传球")
                else:
                    st.info("无数据")
            
            with st.expander(f"⚽ {team} 射门TOP3"):
                if not s['shot_leaders'].empty:
                    for player, cnt in s['shot_leaders'].items():
                        st.markdown(f"- **{player}**: {cnt}次射门")
                else:
                    st.info("无数据")
            
            with st.expander(f"📊 {team} xG TOP3"):
                if not s['xg_leaders'].empty:
                    for player, xg_val in s['xg_leaders'].items():
                        st.markdown(f"- **{player}**: {xg_val:.2f} xG")
                else:
                    st.info("无数据")

    # 下载区
    st.subheader("📥 下载报告")
    dl_cols = st.columns(3)

    with dl_cols[0]:
        st.download_button(
            "📄 文字报告 (TXT)",
            data=text_report,
            file_name=f"{match_name}_报告.txt",
            mime="text/plain"
        )

    with dl_cols[1]:
        if os.path.exists(html_path):
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            st.download_button(
                "🌐 HTML报告",
                data=html_content,
                file_name=f"{match_name}_报告.html",
                mime="text/html"
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
                mime="application/zip"
            )
