"""
app.py — 战术透镜 Streamlit 网页版
启动：streamlit run app.py
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


# ========== 页面配置 ==========
st.set_page_config(
    page_title="战术透镜",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 侧边栏 ==========
with st.sidebar:
    st.title("⚽ 战术透镜")
    st.caption("v4 — 比赛分析报告生成器")
    st.divider()

    st.subheader("📂 上传数据")
    uploaded_file = st.file_uploader(
        "上传CSV文件",
        type=['csv'],
        help="支持 StatsBomb / Catapult / 自定义CSV格式"
    )

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
├── stats_engine.py   统计引擎
├── visualizer.py     可视化引擎
├── report_engine.py  报告引擎
└── templates/        报告模板
    ├── default.json  完整报告
    ├── concise.json  精简速报
    └── coach.json    教练版
""", language=None)

    st.divider()
    st.caption("数据来源：StatsBomb Open Data")

# ========== 主区域 ==========
st.title("⚽ 战术透镜 — 比赛分析报告")

if uploaded_file is None:
    st.info("👈 在左侧上传CSV数据文件开始分析")
    st.markdown("""
    ---
    ### 支持的数据格式

    | 格式 | 说明 | 关键字段 |
    |------|------|----------|
    | **StatsBomb** | 专业赛事事件数据 | type, team, location, shot_statsbomb_xg |
    | **Catapult** | 体育科学追踪数据 | 距离, 高强度跑, 冲刺 |
    | **自定义CSV** | 任意比赛数据 | 至少需要 team 列 |

    ### 使用流程
    1. 上传CSV → 自动识别格式
    2. 选择模板 → 完整/精简/教练版
    3. 自动生成 → 图表 + 洞察 + 报告
    """)
    st.stop()

# ========== 分析流程 ==========
with st.spinner("正在分析..."):
    # 保存上传文件到临时目录
    temp_dir = tempfile.mkdtemp()
    csv_path = os.path.join(temp_dir, "match_data.csv")
    with open(csv_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    output_dir = os.path.join(temp_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    # 1. 加载数据
    try:
        df, info = auto_load(csv_path, match_name=match_name)
    except Exception as e:
        st.error(f"数据加载失败：{e}")
        st.stop()

    # 2. 计算统计
    stats = compute_match_stats(df, info)

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
    <div style="text-align:center; padding:20px 0;">
        <span style="font-size:24px; color:#00f5c4; font-weight:bold;">{t1} {s1['goals']}</span>
        <span style="font-size:24px; color:#8b949e;"> — </span>
        <span style="font-size:24px; color:#4da6ff; font-weight:bold;">{s2['goals']} {t2}</span>
        <br><span style="color:#8b949e;">{match_name}</span>
    </div>
    """, unsafe_allow_html=True)

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

    # 图表展示
    st.subheader("📈 战术图表")
    chart_display = [
        ('shot_map', '射门位置图'),
        ('pass_network', '传球网络图'),
        ('xg_flow', 'xG累积曲线'),
        ('pressure_heatmap', '防守热力图'),
    ]
    chart_cols = st.columns(2)
    for idx, (chart_id, chart_title) in enumerate(chart_display):
        chart_file = chart_paths.get(chart_id)
        if chart_file and os.path.exists(chart_file):
            with chart_cols[idx % 2]:
                st.image(chart_file, caption=chart_title, use_container_width=True)

    chart_display2 = [
        ('shot_comparison', '射门数据对比'),
        ('possession_timeline', '控球时间线'),
        ('stats_bar', '核心数据对比'),
    ]
    chart_cols2 = st.columns(3)
    for idx, (chart_id, chart_title) in enumerate(chart_display2):
        chart_file = chart_paths.get(chart_id)
        if chart_file and os.path.exists(chart_file):
            with chart_cols2[idx % 3]:
                st.image(chart_file, caption=chart_title, use_container_width=True)

    # 战术洞察
    st.subheader("🔍 战术洞察")
    for ins in insights:
        priority_icon = {"1": "🔴", "2": "🟡", "3": "⚪"}.get(str(ins['priority']), "·")
        st.markdown(f"**{priority_icon} [{ins['category']}]** {ins['text']}")
        if ins.get('suggestion'):
            st.caption(f"→ {ins['suggestion']}")

    # 球员排行
    st.subheader("👥 球员数据")
    for team in teams:
        s = stats[team]
        with st.expander(f"{team} 传球TOP5"):
            if not s['pass_leaders'].empty:
                for player, cnt in s['pass_leaders'].items():
                    st.markdown(f"- **{player}**: {cnt}次成功传球")
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
