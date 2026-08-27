"""
app_enhanced.py — 增强版 Streamlit app（集成新的诊断 + 训练系统）

只需替换 app.py 中的导入和主逻辑部分即可。
这个文件展示如何使用新的 format_detector、problem_analyzer、training_standards
"""

import streamlit as st
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tactical_lens'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from format_detector import load_data
from problem_analyzer import ProblemAnalyzer
from training_standards import get_training_plan
from stats_engine import compute_match_stats

# ========== 页面配置 ==========
st.set_page_config(
    page_title="战术透镜 - 增强版",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.problem-critical { color: #ef4444; font-weight: bold; }
.problem-warning { color: #f97316; font-weight: bold; }
.problem-info { color: #2563eb; font-weight: bold; }
.training-module { 
    background-color: #f0fdf4; 
    padding: 12px; 
    border-radius: 8px; 
    margin: 8px 0;
    border-left: 4px solid #10b981;
}
</style>
""", unsafe_allow_html=True)

# ========== 侧边栏 ==========
with st.sidebar:
    st.title("⚽ 战术透镜")
    st.markdown("---")
    
    mode = st.radio(
        "选择功能",
        [
            "📊 快速分析（新）",
            "🎓 问题诊断（新）",
            "📋 训练计划（新）",
            "📄 生成报告（原有）",
        ]
    )

# ========== 主界面 ==========
st.title("⚽ 战术透镜 - 智能战术分析平台")
st.markdown("**基于国际足球数据标准 + 国际主流训练体系**")

if mode == "📊 快速分析（新）":
    st.header("📊 快速数据分析")
    
    st.markdown("""
    ### 第 1 步：上传比赛数据
    支持格式：
    - 📄 FIFA PDF（推荐，自动提取全部数据）
    - 📋 StatsBomb CSV（逐事件数据）
    - 📁 FIFA 多文件 ZIP（12 个数据表）
    - 📊 Catapult CSV（体能数据）
    - 📝 自定义 CSV（任何格式）
    """)
    
    uploaded_file = st.file_uploader("上传比赛数据", type=["pdf", "csv", "zip"])
    
    if uploaded_file:
        st.info("🔄 正在加载和检测文件格式...")
        
        # 保存临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            tmp_path = tmp_file.name
        
        try:
            # 自动检测格式并加载
            from format_detector import detect_format
            result = detect_format(tmp_path)
            
            st.success(f"✅ 格式识别成功：{result.format_type.value} (置信度: {result.confidence:.1%})")
            
            # 加载数据
            df, info = load_data(tmp_path)
            
            st.markdown("### 📊 比赛信息")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("队伍数", len(info.get("teams", [])))
            with col2:
                st.metric("事件数", len(df))
            with col3:
                st.metric("数据来源", info.get("source", "unknown").upper())
            
            # 保存到 session 用于后续步骤
            st.session_state.df = df
            st.session_state.info = info
            
            st.markdown("---")
            st.success("✅ 数据加载成功！请前往「问题诊断」或「训练计划」查看分析结果")
            
        except Exception as e:
            st.error(f"❌ 加载失败：{str(e)}")
        finally:
            os.unlink(tmp_path)


elif mode == "🎓 问题诊断（新）":
    st.header("🎓 自动战术问题诊断")
    
    st.markdown("""
    ### 系统基于以下国际基准进行诊断：
    - **英超 2022-23 赛季平均数据**（StatsBomb）
    - **西甲平均水平**
    - **UEFA 官方指标体系**
    """)
    
    # 从 session 读取数据，或让用户输入统计数据
    if "df" in st.session_state:
        st.info("✅ 已加载数据，正在计算统计...")
        
        try:
            # 计算统计（使用现有的 stats_engine）
            stats = compute_match_stats(st.session_state.df, st.session_state.info)
            
            # 假设有两队
            teams = list(stats.keys())
            if len(teams) >= 2:
                team1, team2 = teams[0], teams[1]
                stats1, stats2 = stats[team1], stats[team2]
                
                st.markdown(f"### 👥 比赛对阵")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"#### {team1}")
                with col2:
                    st.markdown(f"#### {team2}")
                
                # 进行诊断
                st.markdown("### 🔍 智能诊断结果")
                
                analyzer = ProblemAnalyzer()
                problems = analyzer.analyze(stats1, stats2, team1, team2)
                problems_dict = analyzer.to_dict()
                
                # 分别显示两队的问题
                for team_name in [team1, team2]:
                    st.markdown(f"#### {team_name} - 识别的战术问题")
                    
                    team_problems = [p for p in problems_dict if p["team"] == team_name]
                    
                    if team_problems:
                        for i, problem in enumerate(team_problems[:5], 1):  # 显示 Top 5
                            # 按严重度着色
                            severity = problem["severity"]
                            if severity >= 4:
                                severity_color = "critical"
                                severity_emoji = "🔴"
                            elif severity >= 3:
                                severity_color = "warning"
                                severity_emoji = "🟠"
                            else:
                                severity_color = "info"
                                severity_emoji = "🟡"
                            
                            st.markdown(f"""
                            <div style="border-left: 4px solid {'#ef4444' if severity >= 4 else '#f97316'}; padding: 12px; margin: 8px 0; background-color: #f9fafb;">
                                <b>{severity_emoji} {i}. {problem['title']}</b> (严重度: {severity}/5)
                                <br/>{problem['description']}
                                <br/><small>当前值: {problem['current']:.2f} | 国际基准: {problem['benchmark']:.2f} | 差异: {problem['variance_pct']:.1f}%</small>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.info(f"✅ {team_name} 暂无明显问题")
                    
                    st.markdown("---")
                
                # 保存问题用于下一步
                st.session_state.problems = problems_dict
                st.session_state.stats = {team1: stats1, team2: stats2}
        
        except Exception as e:
            st.error(f"❌ 诊断失败：{str(e)}")
    
    else:
        st.warning("⚠️ 请先在「快速分析」中上传比赛数据")


elif mode == "📋 训练计划（新）":
    st.header("📋 推荐训练计划")
    
    st.markdown("""
    ### 基于诊断结果生成周训练计划
    - 集成 **UEFA Level A**、**Liverpool FC**、**Barcelona La Masia** 方法论
    - 包含 13 个国际标准训练模块
    - 自动按问题优先度排序
    """)
    
    if "problems" in st.session_state:
        st.info("✅ 已诊断问题，正在生成训练计划...")
        
        try:
            # 为两队分别生成计划
            for team_name in list(st.session_state.stats.keys()):
                st.markdown(f"### {team_name} - 推荐训练计划")
                
                # 获取该队的问题
                team_problems = [p for p in st.session_state.problems if p["team"] == team_name]
                
                if team_problems:
                    # 生成训练计划
                    training_plan = get_training_plan(team_problems, top_n=3)
                    
                    # 显示周训练日程
                    st.markdown("#### 📅 周训练日程")
                    schedule_data = []
                    for day_info in training_plan.get("weekly_schedule", []):
                        schedule_data.append([
                            day_info["day"],
                            day_info["focus"],
                            f"{day_info['duration_min']}min"
                        ])
                    
                    st.table({
                        "星期": [s[0] for s in schedule_data],
                        "训练主题": [s[1] for s in schedule_data],
                        "时长": [s[2] for s in schedule_data],
                    })
                    
                    # 显示关键训练模块
                    st.markdown("#### 🎯 关键训练模块（按优先度）")
                    
                    for i, training in enumerate(training_plan.get("recommended_training", [])[:3], 1):
                        st.markdown(f"""
                        <div class="training-module">
                            <b>{i}. {training['problem']}</b> (优先度: {training['severity']}/5)
                        </div>
                        """, unsafe_allow_html=True)
                        
                        for module in training.get("modules", [])[:1]:
                            st.markdown(f"""
                            - **{module['name']}** ({module['duration']}min, {module['intensity']} 强度)
                            - 参考：{module['reference']}
                            - 教练要点：{' → '.join(module['coaching_points'][:2])}
                            """)
                    
                    # 显示周训练总时长
                    st.success(f"✅ 周训练总时长：{training_plan.get('total_duration_min', 0)} 分钟")
                    
                else:
                    st.info(f"✅ {team_name} 暂无需要改进的问题")
                
                st.markdown("---")
            
            # 下载按钮
            st.markdown("#### 📥 导出训练计划")
            import json
            plan_json = json.dumps(st.session_state.problems, ensure_ascii=False, indent=2)
            st.download_button(
                label="下载诊断结果 (JSON)",
                data=plan_json,
                file_name="tactical_diagnosis.json",
                mime="application/json"
            )
        
        except Exception as e:
            st.error(f"❌ 生成训练计划失败：{str(e)}")
    
    else:
        st.warning("⚠️ 请先在「问题诊断」中分析数据")


elif mode == "📄 生成报告（原有）":
    st.header("📄 生成 PDF 报告")
    st.info("此功能保持不变，使用原有的 report_generator.py")
    
    if "df" in st.session_state and "stats" in st.session_state:
        if st.button("生成 PDF 报告"):
            st.info("🔄 正在生成报告（可能需要 30-60 秒）...")
            
            try:
                # 这里调用现有的 report_generator
                from report_generator import generate_pdf_report
                
                output_path = "/tmp/tactical_report.pdf"
                generate_pdf_report(
                    st.session_state.df,
                    st.session_state.info,
                    st.session_state.stats,
                    output_path
                )
                
                with open(output_path, "rb") as f:
                    st.download_button(
                        label="📥 下载 PDF 报告",
                        data=f.read(),
                        file_name="tactical_analysis_report.pdf",
                        mime="application/pdf"
                    )
                st.success("✅ 报告生成成功！")
            
            except Exception as e:
                st.error(f"❌ 生成报告失败：{str(e)}")
    
    else:
        st.warning("⚠️ 请先在「快速分析」中上传比赛数据")

# ========== 页脚 ==========
st.markdown("---")
st.markdown("""
### 📚 系统说明

**这是 Tactical Lens 的增强版本，新增功能：**
- ✅ 自动格式识别（FIFA PDF、StatsBomb CSV、Catapult CSV 等）
- ✅ 智能问题诊断（6 种关键战术问题，与国际水平对标）
- ✅ 周训练计划（基于 UEFA、Liverpool、Barcelona 方法论）

**原有功能保持不变：**
- 📊 可视化图表
- 📄 PDF 报告生成
- 📈 球队追踪

**文档：** 
- 中文总结：`中文总结.md`
- 英文指南：`IMPLEMENTATION_GUIDE.md`
""")
