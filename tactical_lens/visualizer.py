"""
visualizer.py — 可视化引擎
生成：射门位置图、传球网络图、射门对比、xG累积曲线、控球时间线、核心数据对比
风格：深色主题，与HTML报告一致

修复说明：
- 新增中文字体自动检测与适配（解决Streamlit Cloud Linux环境中文乱码）
- 新增FIFA模式防守热力图（使用球员级防守数据+近似坐标绘制）
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # 无头模式，服务器环境不出窗口
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap
from matplotlib import font_manager

# ========== 全局风格 ==========
BG_COLOR = '#0d1117'
PITCH_COLOR = '#1a2332'
LINE_COLOR = '#3d4f5f'
TEAM1_COLOR = '#00f5c4'
TEAM2_COLOR = '#4da6ff'
GOAL_COLOR = '#f0883e'
TEXT_COLOR = '#e6edf3'
GRID_COLOR = '#21262d'


# ========== 中文字体适配 ==========

def _setup_chinese_font():
    """自动检测并配置中文字体，解决Linux/Streamlit Cloud环境中文乱码问题
    
    检测优先级（从高到低）：
    1. 项目目录下 fonts/ 文件夹中的字体文件（随项目部署，最可靠）
    2. 系统已安装的中文字体（Noto Sans CJK, WenQuanYi, SimHei等）
    3. matplotlib默认sans-serif（英文降级，中文显示方框但不报错）
    """
    # ---- 第1优先级：项目 fonts/ 目录下的字体文件 ----
    project_font_dirs = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts'),
        os.path.join(os.getcwd(), 'fonts'),
    ]
    
    # 支持的字体文件名（按优先级排序）
    font_file_patterns = [
        'NotoSansSC-Regular.otf',
        'NotoSansCJKsc-Regular.otf',
        'NotoSansCJK-Regular.ttc',
        'NotoSansSC-Regular.ttf',
        'SourceHanSansSC-Regular.otf',
        'wenquanyi_micro_hei.ttf',
        'wqy-microhei.ttc',
        'msyh.ttc',
        'simhei.ttf',
    ]
    
    for font_dir in project_font_dirs:
        if not os.path.isdir(font_dir):
            continue
        for pattern in font_file_patterns:
            font_path = os.path.join(font_dir, pattern)
            if os.path.exists(font_path):
                try:
                    font_manager.fontManager.addfont(font_path)
                    prop = font_manager.FontProperties(fname=font_path)
                    font_name = prop.get_name()
                    plt.rcParams['font.family'] = [font_name, 'sans-serif']
                    plt.rcParams['axes.unicode_minus'] = False
                    print(f"[可视化] 加载项目字体: {font_path} → {font_name}")
                    return True
                except Exception as e:
                    print(f"[可视化] 加载项目字体失败 {font_path}: {e}")
    
    # ---- 第2优先级：系统已安装的中文字体 ----
    chinese_font_names = [
        'Noto Sans CJK SC',
        'Noto Sans SC',
        'Noto Sans CJK JP',
        'WenQuanYi Micro Hei',
        'WenQuanYi Zen Hei',
        'Microsoft YaHei',
        'SimHei',
        'PingFang SC',
        'Heiti SC',
        'Source Han Sans CN',
        'Droid Sans Fallback',
    ]
    
    available_fonts = {f.name for f in font_manager.fontManager.ttflist}
    
    for font_name in chinese_font_names:
        if font_name in available_fonts:
            plt.rcParams['font.family'] = [font_name, 'sans-serif']
            plt.rcParams['axes.unicode_minus'] = False
            print(f"[可视化] 使用系统中文字体: {font_name}")
            return True
    
    # ---- 第3优先级：扫描系统字体目录 ----
    system_font_dirs = [
        '/usr/share/fonts/opentype/noto',
        '/usr/share/fonts/truetype/wqy',
        '/usr/share/fonts/noto-cjk',
        '/usr/share/fonts/truetype/noto',
        '/System/Library/Fonts',
        'C:/Windows/Fonts',
    ]
    
    for font_dir in system_font_dirs:
        if not os.path.isdir(font_dir):
            continue
        try:
            for fname in os.listdir(font_dir):
                if fname.lower().endswith(('.otf', '.ttf', '.ttc')):
                    fpath = os.path.join(font_dir, fname)
                    try:
                        font_manager.fontManager.addfont(fpath)
                    except Exception:
                        pass
        except Exception:
            pass
    
    # 重新扫描后再检查一次
    available_fonts = {f.name for f in font_manager.fontManager.ttflist}
    for font_name in chinese_font_names:
        if font_name in available_fonts:
            plt.rcParams['font.family'] = [font_name, 'sans-serif']
            plt.rcParams['axes.unicode_minus'] = False
            print(f"[可视化] 使用系统中文字体(扫描后): {font_name}")
            return True
    
    # ---- 最终降级：使用默认sans-serif，中文可能显示为方框但不报错 ----
    plt.rcParams['font.family'] = ['DejaVu Sans', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False
    print(f"[可视化] 警告：未找到中文字体，图表中文可能显示为方框（建议在项目fonts/目录放置中文字体文件）")
    return False


# 初始化字体配置
_font_setup_done = False

def _ensure_font_setup():
    """确保字体配置已初始化（延迟初始化，避免导入时耗时）"""
    global _font_setup_done
    if not _font_setup_done:
        _setup_chinese_font()
        _font_setup_done = True


# 基础rcParams（字体在首次绘图时动态设置）
plt.rcParams.update({
    'figure.facecolor': BG_COLOR,
    'axes.facecolor': PITCH_COLOR,
    'axes.edgecolor': LINE_COLOR,
    'axes.labelcolor': TEXT_COLOR,
    'text.color': TEXT_COLOR,
    'xtick.color': LINE_COLOR,
    'ytick.color': LINE_COLOR,
    'grid.color': GRID_COLOR,
    'font.size': 10,
    'axes.unicode_minus': False,
})


# ========== 球场绘制 ==========
def draw_pitch(ax, pitch_type='statsbomb'):
    """在ax上画标准足球场
    StatsBomb坐标系：x∈[0,120], y∈[0,80]
    """
    if pitch_type == 'statsbomb':
        # 外框
        ax.plot([0, 0, 120, 120, 0], [0, 80, 80, 0, 0], color=LINE_COLOR, lw=1.5)
        # 中线
        ax.plot([60, 60], [0, 80], color=LINE_COLOR, lw=1)
        # 中圈
        circle = plt.Circle((60, 40), 9.15, fill=False, color=LINE_COLOR, lw=1)
        ax.add_patch(circle)
        # 中点
        ax.plot(60, 40, 'o', color=LINE_COLOR, markersize=3)
        # 左禁区
        ax.plot([0, 18, 18, 0], [18, 18, 62, 62], color=LINE_COLOR, lw=1)
        # 左小禁区
        ax.plot([0, 6, 6, 0], [30, 30, 50, 50], color=LINE_COLOR, lw=1)
        # 左罚球点
        ax.plot(12, 40, 'o', color=LINE_COLOR, markersize=3)
        # 左罚球弧
        left_arc = patches.Arc((12, 40), 2*9.15, 2*9.15, angle=0, theta1=-53, theta2=53, color=LINE_COLOR, lw=1)
        ax.add_patch(left_arc)
        # 右禁区
        ax.plot([120, 102, 102, 120], [18, 18, 62, 62], color=LINE_COLOR, lw=1)
        # 右小禁区
        ax.plot([120, 114, 114, 120], [30, 30, 50, 50], color=LINE_COLOR, lw=1)
        # 右罚球点
        ax.plot(108, 40, 'o', color=LINE_COLOR, markersize=3)
        # 右罚球弧
        right_arc = patches.Arc((108, 40), 2*9.15, 2*9.15, angle=0, theta1=127, theta2=233, color=LINE_COLOR, lw=1)
        ax.add_patch(right_arc)
        # 角球弧
        for cx, cy, t1, t2 in [(0, 0, 0, 90), (0, 80, 270, 360), (120, 0, 90, 180), (120, 80, 180, 270)]:
            arc = patches.Arc((cx, cy), 2, 2, angle=0, theta1=t1, theta2=t2, color=LINE_COLOR, lw=1)
            ax.add_patch(arc)
        # 球门
        ax.plot([-2, 0], [36, 36], color=LINE_COLOR, lw=1.5)
        ax.plot([-2, 0], [44, 44], color=LINE_COLOR, lw=1.5)
        ax.plot([-2, -2], [36, 44], color=LINE_COLOR, lw=1.5)
        ax.plot([120, 122], [36, 36], color=LINE_COLOR, lw=1.5)
        ax.plot([120, 122], [44, 44], color=LINE_COLOR, lw=1.5)
        ax.plot([122, 122], [36, 44], color=LINE_COLOR, lw=1.5)

        ax.set_xlim(-5, 125)
        ax.set_ylim(-5, 85)
        ax.set_aspect('equal')
        ax.axis('off')


# ========== 射门位置图 ==========
def draw_shot_map(df, info, stats, output_path=None):
    """射门位置图：进球/射正/射偏/xG大小"""
    _ensure_font_setup()
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    fig.suptitle('射门位置图', fontsize=16, color=TEXT_COLOR, y=0.98)

    for idx, (team, color) in enumerate(zip(teams, [TEAM1_COLOR, TEAM2_COLOR])):
        ax = axes[idx]
        draw_pitch(ax)

        shots = df[(df['team'] == team) & (df['type'] == 'Shot')].copy()
        if shots.empty:
            ax.set_title(f'{team}\n（无射门数据）', fontsize=12, color=color, pad=10)
            continue

        # 坐标
        has_coords = 'x' in shots.columns and 'y' in shots.columns and shots['x'].notna().any()
        
        if not has_coords:
            # FIFA模式：无精确坐标，在禁区附近随机分布展示
            goals_count = stats[team]['goals']
            xg_total = stats[team]['xg']
            shots_total = stats[team]['shots_total']
            
            # 在禁区前沿展示射门数量（示意性分布）
            ax.text(60, 45, f'⚽ 射门 {shots_total} 次', ha='center', fontsize=14, color=color, fontweight='bold')
            ax.text(60, 38, f'🎯 射正 {stats[team]["shots_on_target"]} 次', ha='center', fontsize=12, color=color)
            ax.text(60, 31, f'⭐ 进球 {goals_count} 个', ha='center', fontsize=12, color=GOAL_COLOR)
            ax.text(60, 24, f'📊 xG {xg_total:.2f}', ha='center', fontsize=12, color=color)
            
            # 画一些示意性的点
            np.random.seed(42)
            outcomes = shots['shot_outcome'].values
            xgs = shots['shot_statsbomb_xg'].fillna(0.1).values
            
            for i, (outcome, xg_val) in enumerate(zip(outcomes, xgs)):
                # 随机分布在对方禁区附近
                base_x = 95 + np.random.uniform(-10, 15)
                base_y = 20 + np.random.uniform(0, 40)
                marker_size = max(xg_val * 300, 30)
                
                if outcome == 'Goal':
                    ax.scatter(base_x, base_y, s=marker_size, c=GOAL_COLOR, marker='*',
                               edgecolors='white', linewidths=0.8, zorder=5, alpha=0.9)
                elif outcome == 'Saved':
                    ax.scatter(base_x, base_y, s=marker_size, c=color, marker='o',
                               edgecolors='white', linewidths=0.5, zorder=4, alpha=0.7)
                else:
                    ax.scatter(base_x, base_y, s=marker_size, c=color, marker='o',
                               edgecolors=LINE_COLOR, linewidths=0.3, zorder=3, alpha=0.4)
            
            ax.set_title(f'{team}\n{goals_count}球 | xG {xg_total:.2f} | {shots_total}次射门',
                          fontsize=12, color=color, pad=10)
            continue

        xs = shots['x'].values
        ys = shots['y'].values
        xgs = shots['shot_statsbomb_xg'].values if 'shot_statsbomb_xg' in shots.columns else np.ones(len(shots)) * 0.1
        outcomes = shots['shot_outcome'].values if 'shot_outcome' in shots.columns else []

        for i in range(len(xs)):
            if np.isnan(xs[i]) or np.isnan(ys[i]):
                continue
            xg_val = xgs[i] if not np.isnan(xgs[i]) else 0.1
            marker_size = max(xg_val * 300, 30)
            outcome = outcomes[i] if i < len(outcomes) else ''

            if outcome == 'Goal':
                ax.scatter(xs[i], ys[i], s=marker_size, c=GOAL_COLOR, marker='*',
                           edgecolors='white', linewidths=0.8, zorder=5, alpha=0.9)
            elif outcome == 'Saved':
                ax.scatter(xs[i], ys[i], s=marker_size, c=color, marker='o',
                           edgecolors='white', linewidths=0.5, zorder=4, alpha=0.7)
            else:
                ax.scatter(xs[i], ys[i], s=marker_size, c=color, marker='o',
                           edgecolors=LINE_COLOR, linewidths=0.3, zorder=3, alpha=0.4)

        goals_count = stats[team]['goals']
        xg_total = stats[team]['xg']
        shots_total = stats[team]['shots_total']
        ax.set_title(f'{team}\n{goals_count}球 | xG {xg_total:.2f} | {shots_total}次射门',
                      fontsize=12, color=color, pad=10)

    # 图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='*', color='w', markerfacecolor=GOAL_COLOR, markersize=12, label='进球', linestyle='None'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=TEAM1_COLOR, markersize=8, label='射正', linestyle='None'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='gray', markersize=8, label='射偏/被封', linestyle='None', alpha=0.5),
    ]
    fig.legend(handles=legend_elements, loc='lower center', ncol=3, frameon=False,
               fontsize=10, bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 射门位置图 → {output_path}")
        return output_path

    return fig


# ========== 传球网络图 ==========
def draw_pass_network(df, info, stats, output_path=None, min_passes=3):
    """传球网络图：节点=球员平均位置，边=传球次数，节点大小=传球量"""
    _ensure_font_setup()
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    fig.suptitle('传球网络图', fontsize=16, color=TEXT_COLOR, y=0.98)

    for idx, (team, color) in enumerate(zip(teams, [TEAM1_COLOR, TEAM2_COLOR])):
        ax = axes[idx]
        draw_pitch(ax)

        team_passes = df[(df['team'] == team) & (df['type'] == 'Pass')].copy()
        
        # 检查是否有FIFA传球网络数据（info['fifa_extra']）
        fifa_pn = None
        if info and info.get('source') == 'fifa' and info.get('fifa_extra', {}).get('passing_network'):
            # FIFA模式：从传球网络CSV获取数据（在适配器中已存入info）
            pass
            
        if team_passes.empty:
            # 尝试从stats和球员排行展示
            pass_leaders = stats[team].get('pass_leaders', pd.Series(dtype=int))
            formation = stats[team].get('formation', 'N/A')
            acc = stats[team]['pass_accuracy']
            
            if not pass_leaders.empty:
                ax.set_title(f'{team} | {formation}\n传球成功率 {acc:.0f}%',
                              fontsize=12, color=color, pad=10)
                
                # 展示传球TOP5球员（文字形式）
                y_pos = 65
                ax.text(60, 75, '传球TOP5', ha='center', fontsize=11, color=color, fontweight='bold')
                for i, (player, cnt) in enumerate(pass_leaders.head(5).items()):
                    short_name = player.split()[-1] if ' ' in str(player) else str(player)
                    ax.text(60, y_pos - i * 8, f'{i+1}. {short_name}: {cnt}次', 
                            ha='center', fontsize=9, color=TEXT_COLOR)
            else:
                ax.set_title(f'{team}\n（无传球数据）', fontsize=12, color=color, pad=10)
            continue

        # 需要有player列和坐标
        if 'player' not in team_passes.columns:
            ax.set_title(f'{team}\n（缺少球员字段）', fontsize=12, color=color, pad=10)
            continue

        # 球员平均位置
        valid = team_passes.dropna(subset=['x', 'y']) if 'x' in team_passes.columns else pd.DataFrame()
        if valid.empty:
            ax.set_title(f'{team}\n（缺少坐标数据）', fontsize=12, color=color, pad=10)
            continue

        player_pos = valid.groupby('player').agg({'x': 'mean', 'y': 'mean'}).to_dict('index')
        player_pass_count = valid.groupby('player').size().to_dict()

        # 传球对统计
        pass_pairs = {}
        completed = team_passes[team_passes['pass_outcome'].isna()].copy()
        if 'pass_recipient' in completed.columns:
            for _, row in completed.dropna(subset=['pass_recipient']).iterrows():
                pair = (row['player'], row['pass_recipient'])
                pass_pairs[pair] = pass_pairs.get(pair, 0) + 1

        # 画边
        for (p1, p2), cnt in pass_pairs.items():
            if cnt < min_passes:
                continue
            if p1 in player_pos and p2 in player_pos:
                x1, y1 = player_pos[p1]['x'], player_pos[p1]['y']
                x2, y2 = player_pos[p2]['x'], player_pos[p2]['y']
                lw = min(cnt / 3, 5)
                alpha = min(0.3 + cnt / 30, 0.8)
                ax.plot([x1, x2], [y1, y2], color=color, lw=lw, alpha=alpha, zorder=2)

        # 画节点
        for player, pos in player_pos.items():
            cnt = player_pass_count.get(player, 1)
            size = max(cnt * 3, 50)
            ax.scatter(pos['x'], pos['y'], s=size, c=color, edgecolors='white',
                       linewidths=0.8, zorder=4, alpha=0.9)
            # 球员名缩写
            short_name = player.split()[-1] if ' ' in str(player) else str(player)
            ax.annotate(short_name, (pos['x'], pos['y']),
                        textcoords="offset points", xytext=(0, 8),
                        fontsize=7, ha='center', color=TEXT_COLOR, alpha=0.8)

        formation = stats[team].get('formation', 'N/A')
        acc = stats[team]['pass_accuracy']
        ax.set_title(f'{team} | {formation}\n传球成功率 {acc:.0f}%',
                      fontsize=12, color=color, pad=10)

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 传球网络图 → {output_path}")
        return output_path

    return fig


# ========== 射门对比 ==========
def draw_shot_comparison(stats, output_path=None):
    """射门数据对比柱状图"""
    _ensure_font_setup()
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    t1, t2 = teams[0], teams[1]
    s1, s2 = stats[t1], stats[t2]

    metrics = ['射门', '射正', '进球', 'xG×10', '关键传球']
    v1 = [s1['shots_total'], s1['shots_on_target'], s1['goals'], s1['xg'] * 10, s1['key_passes']]
    v2 = [s2['shots_total'], s2['shots_on_target'], s2['goals'], s2['xg'] * 10, s2['key_passes']]

    x = np.arange(len(metrics))
    width = 0.35

    fig, ax = plt.subplots(figsize=(12, 8))
    bars1 = ax.bar(x - width/2, v1, width, label=t1, color=TEAM1_COLOR, alpha=0.85, edgecolor='none')
    bars2 = ax.bar(x + width/2, v2, width, label=t2, color=TEAM2_COLOR, alpha=0.85, edgecolor='none')

    # 数值标注
    for bar in bars1:
        h = bar.get_height()
        if h > 0:
            ax.text(bar.get_x() + bar.get_width()/2., h + 0.3, f'{h:.0f}',
                    ha='center', va='bottom', fontsize=9, color=TEAM1_COLOR)
    for bar in bars2:
        h = bar.get_height()
        if h > 0:
            ax.text(bar.get_x() + bar.get_width()/2., h + 0.3, f'{h:.0f}',
                    ha='center', va='bottom', fontsize=9, color=TEAM2_COLOR)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.legend(frameon=False, fontsize=11)
    ax.set_title('射门数据对比', fontsize=14, pad=15)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 射门对比 → {output_path}")
        return output_path

    return fig


# ========== xG累积曲线 ==========
def draw_xg_flow(df, info, stats, output_path=None):
    """xG随时间累积曲线"""
    _ensure_font_setup()
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    fig, ax = plt.subplots(figsize=(12, 8))

    for team, color in zip(teams, [TEAM1_COLOR, TEAM2_COLOR]):
        shots = df[(df['team'] == team) & (df['type'] == 'Shot')].copy()
        if shots.empty:
            continue

        # 时间列
        time_col = None
        for col in ['minute', 'match_minute', 'period_minute']:
            if col in shots.columns:
                time_col = col
                break

        if time_col is None:
            continue

        shots = shots.sort_values(time_col)
        xg_col = 'shot_statsbomb_xg' if 'shot_statsbomb_xg' in shots.columns else None

        if xg_col is None:
            continue

        times = shots[time_col].values
        xgs = shots[xg_col].fillna(0).cumsum().values

        # 分上下半场
        half2_start = 45
        has_half2 = any(t > half2_start for t in times) if len(times) > 0 else False

        # 画线
        all_times = np.concatenate([[0], times])
        all_xgs = np.concatenate([[0], xgs])
        ax.plot(all_times, all_xgs, color=color, lw=2, label=team, alpha=0.9)
        ax.fill_between(all_times, all_xgs, alpha=0.1, color=color)

        # 进球标记
        goal_shots = shots[shots['shot_outcome'] == 'Goal']
        for _, row in goal_shots.iterrows():
            ax.scatter(row[time_col], row[xg_col], s=100, c=GOAL_COLOR,
                       marker='*', edgecolors='white', linewidths=0.8, zorder=5)
            ax.annotate('⚽', (row[time_col], row[xg_col]),
                        textcoords="offset points", xytext=(5, 8),
                        fontsize=10, color=GOAL_COLOR)

    # 半场线
    ax.axvline(x=45, color=LINE_COLOR, lw=1, linestyle='--', alpha=0.6)
    ax.text(22.5, ax.get_ylim()[1] * 0.95, '上半场', ha='center', fontsize=9, color=LINE_COLOR, alpha=0.7)
    if has_half2:
        ax.text(67.5, ax.get_ylim()[1] * 0.95, '下半场', ha='center', fontsize=9, color=LINE_COLOR, alpha=0.7)

    ax.set_xlabel('分钟')
    ax.set_ylabel('累积 xG')
    ax.set_title('xG 累积曲线', fontsize=14, pad=15)
    ax.legend(frameon=False, fontsize=11)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(alpha=0.3)

    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] xG累积曲线 → {output_path}")
        return output_path

    return fig


# ========== 控球时间线 ==========
def draw_possession_timeline(df, info, stats, output_path=None, window=5):
    """滚动控球率时间线（每5分钟窗口）"""
    _ensure_font_setup()
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    time_col = None
    for col in ['minute', 'match_minute', 'period_minute']:
        if col in df.columns:
            time_col = col
            break

    if time_col is None or 'possession_team' not in df.columns:
        # 没有possession_team，退化为用事件数代替
        return _draw_possession_by_events(df, info, stats, output_path, window)

    fig, ax = plt.subplots(figsize=(12, 8))

    max_min = int(df[time_col].max())
    bins = list(range(0, max_min + window, window))

    for team, color in zip(teams, [TEAM1_COLOR, TEAM2_COLOR]):
        team_df = df[df['possession_team'] == team]
        counts, edges = np.histogram(team_df[time_col].dropna(), bins=bins)
        centers = [(edges[i] + edges[i+1]) / 2 for i in range(len(counts))]
        ax.plot(centers, counts, color=color, lw=2, label=team, alpha=0.85)
        ax.fill_between(centers, counts, alpha=0.1, color=color)

    ax.axvline(x=45, color=LINE_COLOR, lw=1, linestyle='--', alpha=0.6)
    ax.set_xlabel('分钟')
    ax.set_ylabel('控球事件数')
    ax.set_title(f'控球时间线（{window}分钟窗口）', fontsize=14, pad=15)
    ax.legend(frameon=False, fontsize=11)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(alpha=0.3)

    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 控球时间线 → {output_path}")
        return output_path

    return fig


def _draw_possession_by_events(df, info, stats, output_path=None, window=5):
    """退化为按事件数画控球趋势"""
    _ensure_font_setup()
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    time_col = None
    for col in ['minute', 'match_minute', 'period_minute']:
        if col in df.columns:
            time_col = col
            break
    if time_col is None:
        return None

    fig, ax = plt.subplots(figsize=(12, 8))

    max_min = int(df[time_col].max())
    bins = list(range(0, max_min + window, window))

    for team, color in zip(teams, [TEAM1_COLOR, TEAM2_COLOR]):
        team_df = df[df['team'] == team]
        counts, edges = np.histogram(team_df[time_col].dropna(), bins=bins)
        centers = [(edges[i] + edges[i+1]) / 2 for i in range(len(counts))]
        ax.plot(centers, counts, color=color, lw=2, label=team, alpha=0.85)
        ax.fill_between(centers, counts, alpha=0.1, color=color)

    ax.axvline(x=45, color=LINE_COLOR, lw=1, linestyle='--', alpha=0.6)
    ax.set_xlabel('分钟')
    ax.set_ylabel('事件数')
    ax.set_title(f'比赛节奏时间线（{window}分钟窗口）', fontsize=14, pad=15)
    ax.legend(frameon=False, fontsize=11)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(alpha=0.3)

    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 节奏时间线 → {output_path}")
        return output_path

    return fig


# ========== 核心数据对比 ==========
def draw_stats_bar(stats, output_path=None):
    """核心数据对比水平柱状图"""
    _ensure_font_setup()
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    t1, t2 = teams[0], teams[1]
    s1, s2 = stats[t1], stats[t2]

    metrics = [
        ('控球率 %', s1.get('possession_pct', 0), s2.get('possession_pct', 0)),
        ('传球成功率 %', s1['pass_accuracy'], s2['pass_accuracy']),
        ('射正率 %', 
         s1['shots_on_target'] / max(s1['shots_total'], 1) * 100,
         s2['shots_on_target'] / max(s2['shots_total'], 1) * 100),
        ('射门', s1['shots_total'], s2['shots_total']),
        ('犯规', s1['fouls'], s2['fouls']),
        ('角球', s1['corners'], s2['corners']),
        ('关键传球', s1['key_passes'], s2['key_passes']),
    ]

    labels = [m[0] for m in metrics]
    v1 = [m[1] for m in metrics]
    v2 = [m[2] for m in metrics]

    y = np.arange(len(labels))
    height = 0.35

    fig, ax = plt.subplots(figsize=(12, 8))
    bars1 = ax.barh(y - height/2, v1, height, label=t1, color=TEAM1_COLOR, alpha=0.85)
    bars2 = ax.barh(y + height/2, v2, height, label=t2, color=TEAM2_COLOR, alpha=0.85)

    # 数值标注
    for bar in bars1:
        w = bar.get_width()
        ax.text(w + 0.5, bar.get_y() + bar.get_height()/2., f'{w:.1f}',
                ha='left', va='center', fontsize=9, color=TEAM1_COLOR)
    for bar in bars2:
        w = bar.get_width()
        ax.text(w + 0.5, bar.get_y() + bar.get_height()/2., f'{w:.1f}',
                ha='left', va='center', fontsize=9, color=TEAM2_COLOR)

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.legend(frameon=False, fontsize=11)
    ax.set_title('核心数据对比', fontsize=14, pad=15)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x', alpha=0.3)

    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 核心数据对比 → {output_path}")
        return output_path

    return fig


# ========== 热力图 ==========
def draw_pressure_heatmap(df, info, stats, team=None, output_path=None, bins=(12, 8)):
    """逼抢/防守行为热力图
    
    支持两种模式：
    1. StatsBomb模式：有精确坐标，绘制2D热力图
    2. FIFA模式：使用球员级防守数据+近似坐标，绘制散点热力图
    
    team: 指定队伍，None则画两队
    """
    _ensure_font_setup()
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    # 检测是否为FIFA数据
    is_fifa = info and info.get('source') == 'fifa'
    
    target_teams = [team] if team else teams
    n = len(target_teams)

    fig, axes = plt.subplots(1, n, figsize=(14, 7))
    if n == 1:
        axes = [axes]

    fig.suptitle('防守行为热力图', fontsize=16, color=TEXT_COLOR, y=0.98)

    for idx, t in enumerate(target_teams):
        ax = axes[idx]
        draw_pitch(ax)

        color = TEAM1_COLOR if t == teams[0] else TEAM2_COLOR
        
        # ---- FIFA模式：使用球员级防守数据 + 近似坐标 ----
        if is_fifa:
            player_defense = None
            fifa_extra = info.get('fifa_extra', {})
            if 'player_defense_stats' in fifa_extra:
                player_defense = fifa_extra['player_defense_stats'].get(t)
            
            if player_defense is not None and not player_defense.empty:
                # 有球员防守数据，绘制散点热力图
                def_df = player_defense.copy()
                
                if 'approx_x' in def_df.columns and 'approx_y' in def_df.columns:
                    # 有近似坐标，画热力圈
                    valid = def_df.dropna(subset=['approx_x', 'approx_y'])
                    
                    if not valid.empty:
                        max_score = valid['defense_score'].max() if 'defense_score' in valid.columns else 1
                        max_score = max(max_score, 1)
                        
                        for _, row in valid.iterrows():
                            x = row['approx_x']
                            y = row['approx_y']
                            score = row.get('defense_score', 5)
                            
                            # 圆圈大小和透明度随防守强度变化
                            radius = max(3, min(12, score / max_score * 12))
                            alpha = min(0.7, 0.2 + score / max_score * 0.5)
                            
                            circle = plt.Circle((x, y), radius, color=color, 
                                               alpha=alpha, zorder=3)
                            ax.add_patch(circle)
                            
                            # 球员名
                            player_name = row.get('player_name', '')
                            short_name = player_name.split()[-1] if ' ' in str(player_name) else str(player_name)
                            if score > max_score * 0.3:  # 只标注防守贡献大的球员
                                ax.annotate(short_name, (x, y),
                                           textcoords="offset points", xytext=(0, 0),
                                           fontsize=7, ha='center', color='white', 
                                           fontweight='bold', alpha=0.9, zorder=5)
                        
                        ax.set_title(f'{t}\n（球员防守强度分布）', fontsize=12, color=color, pad=10)
                    else:
                        ax.set_title(f'{t}\n（无有效位置数据）', fontsize=12, color=color, pad=10)
                else:
                    # 无近似坐标，展示防守数据排行
                    if 'defense_score' in def_df.columns:
                        top_def = def_df.nlargest(5, 'defense_score')
                        ax.text(60, 70, '防守TOP5', ha='center', fontsize=12, color=color, fontweight='bold')
                        for i, (_, row) in enumerate(top_def.iterrows()):
                            name = row.get('player_name', '')
                            short_name = name.split()[-1] if ' ' in str(name) else str(name)
                            score = row.get('defense_score', 0)
                            y_pos = 58 - i * 10
                            ax.text(60, y_pos, f'{i+1}. {short_name}: {int(score)}分',
                                   ha='center', fontsize=10, color=TEXT_COLOR)
                        ax.set_title(f'{t}\n（防守数据排行）', fontsize=12, color=color, pad=10)
                    else:
                        ax.set_title(f'{t}\n（无防守数据）', fontsize=12, color=color, pad=10)
            else:
                ax.set_title(f'{t}\n（无防守位置数据）', fontsize=12, color=color, pad=10)
            continue
        
        # ---- StatsBomb模式：有精确坐标 ----
        def_types = ['Pressure', 'Foul Committed', 'Block', 'Interception']
        def_events = df[(df['team'] == t) & (df['type'].isin(def_types))].copy()

        if def_events.empty or 'x' not in def_events.columns:
            ax.set_title(f'{t}\n（无防守位置数据）', fontsize=12, color=color, pad=10)
            continue

        valid = def_events.dropna(subset=['x', 'y'])
        if valid.empty:
            ax.set_title(f'{t}\n（无有效坐标）', fontsize=12, color=color, pad=10)
            continue

        # 热力图
        heatmap, xedges, yedges = np.histogram2d(
            valid['x'], valid['y'], bins=bins,
            range=[[0, 120], [0, 80]]
        )

        # 平滑
        try:
            from scipy.ndimage import gaussian_filter
            heatmap = gaussian_filter(heatmap, sigma=1)
        except ImportError:
            pass

        extent = [0, 120, 0, 80]
        cmap = LinearSegmentedColormap.from_list('custom',
            [PITCH_COLOR, color, '#ffffff'], N=256)

        ax.imshow(heatmap.T, extent=extent, origin='lower', cmap=cmap,
                  alpha=0.6, aspect='auto', interpolation='bilinear')

        ax.set_title(f'{t}', fontsize=12, color=color, pad=10)

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 防守热力图 → {output_path}")
        return output_path

    return fig


# ========== 战术风格雷达图（FIFA专属） ==========
def draw_tactical_radar(df, info, stats, output_path=None):
    """战术风格雷达图：对比两队攻防战术风格
    
    FIFA专属图表，StatsBomb模式返回None。
    采用双子图设计：左侧进攻雷达（7维），右侧防守雷达（7维），避免14个标签重叠。
    百分比归一化，展示各维度占比。
    """
    _ensure_font_setup()
    
    # 仅FIFA模式支持
    if not info or info.get('source') != 'fifa':
        return None
    
    fifa_extra = info.get('fifa_extra', {})
    radar_data = fifa_extra.get('tactical_radar', {})
    if not radar_data:
        return None
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None
    
    t1, t2 = teams[0], teams[1]
    if t1 not in radar_data or t2 not in radar_data:
        return None
    
    attack_dims = radar_data[t1]['attack_dims']
    defense_dims = radar_data[t1]['defense_dims']
    
    # 获取两队各维度数值
    t1_attack = [radar_data[t1]['attack'].get(d, 0) for d in attack_dims]
    t2_attack = [radar_data[t2]['attack'].get(d, 0) for d in attack_dims]
    t1_defense = [radar_data[t1]['defense'].get(d, 0) for d in defense_dims]
    t2_defense = [radar_data[t2]['defense'].get(d, 0) for d in defense_dims]
    
    # 计算全局最大值，保持两图刻度一致便于对比
    all_values = t1_attack + t2_attack + t1_defense + t2_defense
    global_max = max(all_values) if all_values else 100
    r_limit = global_max * 1.15
    
    # ===== 双子图布局：左进攻，右防守 =====
    fig, (ax_attack, ax_defense) = plt.subplots(
        1, 2, figsize=(16, 9), 
        subplot_kw=dict(polar=True)
    )
    fig.patch.set_facecolor(BG_COLOR)
    
    # ---- 辅助函数：绘制单个雷达图 ----
    def _draw_radar(ax, dims, t1_vals, t2_vals, title, icon):
        n = len(dims)
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        angles_closed = angles + angles[:1]
        t1_closed = t1_vals + t1_vals[:1]
        t2_closed = t2_vals + t2_vals[:1]
        
        ax.set_facecolor(PITCH_COLOR)
        
        # 绘制两队雷达
        ax.plot(angles_closed, t1_closed, color=TEAM1_COLOR, lw=2.5, label=t1, alpha=0.9)
        ax.fill(angles_closed, t1_closed, color=TEAM1_COLOR, alpha=0.15)
        ax.plot(angles_closed, t2_closed, color=TEAM2_COLOR, lw=2.5, label=t2, alpha=0.9)
        ax.fill(angles_closed, t2_closed, color=TEAM2_COLOR, alpha=0.15)
        
        # 设置轴标签（增大字体和间距，避免重叠）
        ax.set_xticks(angles)
        ax.set_xticklabels(dims, color=TEXT_COLOR, fontsize=11)
        
        # 设置径向网格
        ax.set_ylim(0, r_limit)
        ax.set_yticks(np.linspace(0, global_max, 5))
        ax.set_yticklabels([f'{int(v)}' for v in np.linspace(0, global_max, 5)],
                          color=LINE_COLOR, fontsize=8)
        ax.grid(color=LINE_COLOR, alpha=0.3)
        ax.spines['polar'].set_color(LINE_COLOR)
        
        # 标题
        ax.set_title(f'{icon} {title}', fontsize=15, color=TEXT_COLOR, 
                    pad=30, fontweight='bold')
    
    # 绘制进攻雷达
    _draw_radar(ax_attack, attack_dims, t1_attack, t2_attack, '进攻端', '⚔')
    
    # 绘制防守雷达
    _draw_radar(ax_defense, defense_dims, t1_defense, t2_defense, '防守端', '🛡')
    
    # 统一图例（放在两图中间上方）
    handles, labels = ax_attack.get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=2, 
              frameon=False, fontsize=13, bbox_to_anchor=(0.5, 0.98),
              labelcolor=TEXT_COLOR)
    
    # 总标题
    fig.suptitle('战术风格雷达图', fontsize=18, color=TEXT_COLOR, y=0.97, fontweight='bold')
    
    plt.tight_layout(rect=[0, 0, 1, 0.92])
    
    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 战术风格雷达图 → {output_path}")
        return output_path
    
    return fig


# ========== 防线穿透分析（FIFA专属） ==========
def draw_line_breaks(df, info, stats, output_path=None):
    """防线穿透分析：突破尝试、成功、成功率、进球 + 球员TOP3
    
    FIFA专属图表，StatsBomb模式返回None。
    形式：分组柱状图对比两队 + 球员TOP3排行。
    """
    _ensure_font_setup()
    
    # 仅FIFA模式支持
    if not info or info.get('source') != 'fifa':
        return None
    
    fifa_extra = info.get('fifa_extra', {})
    lb_data = fifa_extra.get('line_breaks', {})
    if not lb_data:
        return None
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None
    
    t1, t2 = teams[0], teams[1]
    if t1 not in lb_data or t2 not in lb_data:
        return None
    
    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor(BG_COLOR)
    
    # 上半部分：分组柱状图
    ax1 = fig.add_subplot(2, 1, 1)
    ax1.set_facecolor(PITCH_COLOR)
    
    metrics = ['尝试次数', '成功次数', '突破后进球']
    v1 = [lb_data[t1]['attempts'], lb_data[t1]['completed'], lb_data[t1]['goals']]
    v2 = [lb_data[t2]['attempts'], lb_data[t2]['completed'], lb_data[t2]['goals']]
    
    x = np.arange(len(metrics))
    width = 0.35
    
    bars1 = ax1.bar(x - width/2, v1, width, label=t1, color=TEAM1_COLOR, alpha=0.85, edgecolor='none')
    bars2 = ax1.bar(x + width/2, v2, width, label=t2, color=TEAM2_COLOR, alpha=0.85, edgecolor='none')
    
    # 数值标注
    for bar in bars1:
        h = bar.get_height()
        if h > 0:
            ax1.text(bar.get_x() + bar.get_width()/2., h + 0.3, f'{h:.0f}',
                    ha='center', va='bottom', fontsize=10, color=TEAM1_COLOR, fontweight='bold')
    for bar in bars2:
        h = bar.get_height()
        if h > 0:
            ax1.text(bar.get_x() + bar.get_width()/2., h + 0.3, f'{h:.0f}',
                    ha='center', va='bottom', fontsize=10, color=TEAM2_COLOR, fontweight='bold')
    
    # 成功率标注
    ax1.text(0, max(v1[0], v2[0]) * 0.5, 
             f'成功率: {lb_data[t1]["success_rate"]:.1f}%', 
             ha='center', fontsize=10, color=TEAM1_COLOR, fontweight='bold')
    ax1.text(0 + width/2 + 0.15, max(v1[0], v2[0]) * 0.4, 
             f'{lb_data[t2]["success_rate"]:.1f}%', 
             ha='left', fontsize=10, color=TEAM2_COLOR, fontweight='bold')
    
    ax1.set_xticks(x)
    ax1.set_xticklabels(metrics, fontsize=11)
    ax1.legend(frameon=False, fontsize=11)
    ax1.set_title('防线穿透分析', fontsize=14, pad=15, color=TEXT_COLOR)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['left'].set_color(LINE_COLOR)
    ax1.spines['bottom'].set_color(LINE_COLOR)
    ax1.tick_params(colors=TEXT_COLOR)
    ax1.grid(axis='y', alpha=0.3)
    
    # 下半部分：球员TOP3排行
    ax2 = fig.add_subplot(2, 1, 2)
    ax2.set_facecolor(PITCH_COLOR)
    ax2.set_title('突破球员TOP3（按成功次数）', fontsize=12, pad=10, color=TEXT_COLOR)
    
    # 两队TOP3并排展示
    top1 = lb_data[t1].get('top_players', [])
    top2 = lb_data[t2].get('top_players', [])
    
    # 左侧：T1
    ax2.text(0.25, 1.02, t1, ha='center', fontsize=11, color=TEAM1_COLOR, 
             fontweight='bold', transform=ax2.transAxes)
    # 右侧：T2
    ax2.text(0.75, 1.02, t2, ha='center', fontsize=11, color=TEAM2_COLOR, 
             fontweight='bold', transform=ax2.transAxes)
    
    y_positions = [0.7, 0.45, 0.2]
    
    for i in range(3):
        y = y_positions[i]
        
        # 队1球员
        if i < len(top1):
            p = top1[i]
            short_name = p['name'].split()[-1] if ' ' in str(p['name']) else str(p['name'])
            text = f"{i+1}. {short_name} — {p['completed']}次成功 ({p['attempts']}次尝试)"
            if p['goals'] > 0:
                text += f" ⚽{p['goals']}"
            ax2.text(0.25, y, text, ha='center', fontsize=10, color=TEXT_COLOR,
                    transform=ax2.transAxes)
        else:
            ax2.text(0.25, y, f'{i+1}. —', ha='center', fontsize=10, color=LINE_COLOR,
                    transform=ax2.transAxes)
        
        # 队2球员
        if i < len(top2):
            p = top2[i]
            short_name = p['name'].split()[-1] if ' ' in str(p['name']) else str(p['name'])
            text = f"{i+1}. {short_name} — {p['completed']}次成功 ({p['attempts']}次尝试)"
            if p['goals'] > 0:
                text += f" ⚽{p['goals']}"
            ax2.text(0.75, y, text, ha='center', fontsize=10, color=TEXT_COLOR,
                    transform=ax2.transAxes)
        else:
            ax2.text(0.75, y, f'{i+1}. —', ha='center', fontsize=10, color=LINE_COLOR,
                    transform=ax2.transAxes)
    
    ax2.axis('off')
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    
    plt.tight_layout()
    
    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 防线穿透分析 → {output_path}")
        return output_path
    
    return fig


# ========== 传中战术分析（FIFA专属） ==========
def draw_cross_tactics(df, info, stats, output_path=None):
    """传中战术分析：6种传中类型分布对比 + 成功率
    
    FIFA专属图表，StatsBomb模式返回None。
    形式：双饼图/堆叠柱对比两队传中类型分布，底部展示成功率。
    """
    _ensure_font_setup()
    
    # 仅FIFA模式支持
    if not info or info.get('source') != 'fifa':
        return None
    
    fifa_extra = info.get('fifa_extra', {})
    cross_data = fifa_extra.get('cross_tactics', {})
    if not cross_data:
        return None
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None
    
    t1, t2 = teams[0], teams[1]
    if t1 not in cross_data or t2 not in cross_data:
        return None
    
    # 传中类型和颜色
    cross_types_en = ['inswing', 'outswing', 'driven', 'lofted', 'cutback', 'push_cross']
    cn_names = cross_data[t1].get('type_names_cn', {})
    cross_type_colors = ['#00f5c4', '#4da6ff', '#f0883e', '#a78bfa', '#34d399', '#fbbf24']
    
    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor(BG_COLOR)
    
    # 左侧饼图：T1
    ax1 = fig.add_subplot(1, 3, 1)
    t1_types = cross_data[t1]['type_distribution']
    t1_vals = [t1_types.get(ct, 0) for ct in cross_types_en]
    t1_labels = [cn_names.get(ct, ct) for ct in cross_types_en]
    
    # 过滤掉0值
    t1_nonzero = [(l, v, c) for l, v, c in zip(t1_labels, t1_vals, cross_type_colors) if v > 0]
    if t1_nonzero:
        labels1, vals1, colors1 = zip(*t1_nonzero)
        wedges1, texts1, autotexts1 = ax1.pie(
            vals1, labels=labels1, colors=colors1, autopct='%1.0f%%',
            startangle=90, textprops={'color': TEXT_COLOR, 'fontsize': 9},
            pctdistance=0.75, wedgeprops={'edgecolor': BG_COLOR, 'linewidth': 2}
        )
        for at in autotexts1:
            at.set_fontsize(8)
            at.set_fontweight('bold')
    else:
        ax1.text(0.5, 0.5, '无类型数据', ha='center', va='center', color=LINE_COLOR, fontsize=12)
    
    ax1.set_title(f'{t1}\n传中类型分布', fontsize=12, color=TEAM1_COLOR, pad=10)
    
    # 右侧饼图：T2
    ax2 = fig.add_subplot(1, 3, 2)
    t2_types = cross_data[t2]['type_distribution']
    t2_vals = [t2_types.get(ct, 0) for ct in cross_types_en]
    
    t2_nonzero = [(l, v, c) for l, v, c in zip(t1_labels, t2_vals, cross_type_colors) if v > 0]
    if t2_nonzero:
        labels2, vals2, colors2 = zip(*t2_nonzero)
        wedges2, texts2, autotexts2 = ax2.pie(
            vals2, labels=labels2, colors=colors2, autopct='%1.0f%%',
            startangle=90, textprops={'color': TEXT_COLOR, 'fontsize': 9},
            pctdistance=0.75, wedgeprops={'edgecolor': BG_COLOR, 'linewidth': 2}
        )
        for at in autotexts2:
            at.set_fontsize(8)
            at.set_fontweight('bold')
    else:
        ax2.text(0.5, 0.5, '无类型数据', ha='center', va='center', color=LINE_COLOR, fontsize=12)
    
    ax2.set_title(f'{t2}\n传中类型分布', fontsize=12, color=TEAM2_COLOR, pad=10)
    
    # 右侧：传中成功率对比
    ax3 = fig.add_subplot(1, 3, 3)
    ax3.set_facecolor(PITCH_COLOR)
    
    t1_rate = cross_data[t1]['success_rate']
    t2_rate = cross_data[t2]['success_rate']
    t1_total = cross_data[t1]['total_attempted']
    t2_total = cross_data[t2]['total_attempted']
    t1_comp = cross_data[t1]['total_completed']
    t2_comp = cross_data[t2]['total_completed']
    
    teams_names = [t1, t2]
    rates = [t1_rate, t2_rate]
    bar_colors = [TEAM1_COLOR, TEAM2_COLOR]
    
    bars = ax3.barh(teams_names, rates, color=bar_colors, alpha=0.85, height=0.5)
    
    for i, (bar, rate) in enumerate(zip(bars, rates)):
        w = bar.get_width()
        ax3.text(w + 1, bar.get_y() + bar.get_height()/2., f'{rate:.1f}%',
                ha='left', va='center', fontsize=11, color=bar_colors[i], fontweight='bold')
    
    ax3.set_xlim(0, 100)
    ax3.set_xlabel('成功率 %', color=TEXT_COLOR)
    ax3.set_title('传中成功率', fontsize=12, color=TEXT_COLOR, pad=10)
    ax3.spines['top'].set_visible(False)
    ax3.spines['right'].set_visible(False)
    ax3.spines['left'].set_color(LINE_COLOR)
    ax3.spines['bottom'].set_color(LINE_COLOR)
    ax3.tick_params(colors=TEXT_COLOR)
    ax3.grid(axis='x', alpha=0.3)
    
    # 底部添加总传中数信息
    fig.text(0.5, 0.02, 
             f'总传中数：{t1} {t1_total}次（成功{t1_comp}） | {t2} {t2_total}次（成功{t2_comp}）',
             ha='center', fontsize=10, color=LINE_COLOR)
    
    plt.tight_layout(rect=[0, 0.05, 1, 0.95])
    
    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 传中战术分析 → {output_path}")
        return output_path
    
    return fig


# ========== 体能五分区图（FIFA专属） ==========
def draw_physical_zones(df, info, stats, output_path=None):
    """体能五分区图：5个强度分区距离分布 + 冲刺次数 + 最高速度TOP3
    
    FIFA专属图表，StatsBomb模式返回None。
    形式：堆叠柱状图 + 冲刺次数对比 + 最高速度TOP3球员。
    """
    _ensure_font_setup()
    
    # 仅FIFA模式支持
    if not info or info.get('source') != 'fifa':
        return None
    
    fifa_extra = info.get('fifa_extra', {})
    phys_data = fifa_extra.get('physical_zones', {})
    if not phys_data:
        return None
    
    teams = list(stats.keys())
    if len(teams) < 2:
        return None
    
    t1, t2 = teams[0], teams[1]
    if t1 not in phys_data or t2 not in phys_data:
        return None
    
    # 五分区
    zone_keys = ['zone1_walk', 'zone2_jog', 'zone3_run', 'zone4_low_sprint', 'zone5_high_sprint']
    cn_names = phys_data[t1].get('zone_names_cn', {})
    zone_colors = ['#6b7280', '#3b82f6', '#22c55e', '#f59e0b', '#ef4444']
    
    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor(BG_COLOR)
    
    # 上半部分：堆叠柱状图
    ax1 = fig.add_subplot(2, 1, 1)
    ax1.set_facecolor(PITCH_COLOR)
    
    # 获取两队各分区距离（转换为公里）
    t1_zones = [phys_data[t1]['zones'].get(z, 0) / 1000 for z in zone_keys]
    t2_zones = [phys_data[t2]['zones'].get(z, 0) / 1000 for z in zone_keys]
    
    zone_labels = [cn_names.get(z, z) for z in zone_keys]
    
    # 堆叠柱状图（水平方向，两队并列）
    y_positions = [1, 0]
    team_labels = [t1, t2]
    team_colors_zones = [[TEAM1_COLOR]*5, [TEAM2_COLOR]*5]
    
    # 绘制堆叠条
    left1 = np.zeros(1)
    left2 = np.zeros(1)
    for i in range(len(zone_keys)):
        # 队1
        ax1.barh([1], [t1_zones[i]], left=left1[0], height=0.4, 
                color=zone_colors[i], alpha=0.85, label=zone_labels[i] if left1[0] == 0 else "")
        left1[0] += t1_zones[i]
        
        # 队2
        ax1.barh([0], [t2_zones[i]], left=left2[0], height=0.4, 
                color=zone_colors[i], alpha=0.85)
        left2[0] += t2_zones[i]
    
    ax1.set_yticks([1, 0])
    ax1.set_yticklabels([t1, t2], fontsize=11)
    ax1.set_xlabel('距离 (km)', color=TEXT_COLOR)
    ax1.set_title('体能五分区分布（全队总距离）', fontsize=14, pad=15, color=TEXT_COLOR)
    ax1.legend(loc='upper right', bbox_to_anchor=(1, 1), frameon=False, fontsize=9, ncol=5)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['left'].set_color(LINE_COLOR)
    ax1.spines['bottom'].set_color(LINE_COLOR)
    ax1.tick_params(colors=TEXT_COLOR)
    ax1.grid(axis='x', alpha=0.3)
    
    # 添加总距离标注
    t1_total = phys_data[t1]['total_distance'] / 1000
    t2_total = phys_data[t2]['total_distance'] / 1000
    ax1.text(left1[0] + 0.2, 1, f'{t1_total:.1f} km', va='center', 
             fontsize=10, color=TEAM1_COLOR, fontweight='bold')
    ax1.text(left2[0] + 0.2, 0, f'{t2_total:.1f} km', va='center', 
             fontsize=10, color=TEAM2_COLOR, fontweight='bold')
    
    # 下半部分：冲刺次数对比 + 最高速度TOP3
    ax2 = fig.add_subplot(2, 1, 2)
    ax2.set_facecolor(PITCH_COLOR)
    
    # 左侧：冲刺次数对比
    t1_sprints = phys_data[t1]['sprints_count']
    t2_sprints = phys_data[t2]['sprints_count']
    t1_hsr = phys_data[t1]['high_speed_runs']
    t2_hsr = phys_data[t2]['high_speed_runs']
    
    sprint_metrics = ['冲刺次数\n(zone4+5)', '高速跑次数\n(zone3+)']
    t1_sprint_vals = [t1_sprints, t1_hsr]
    t2_sprint_vals = [t2_sprints, t2_hsr]
    
    x_sprint = np.arange(len(sprint_metrics))
    width = 0.3
    
    ax2.bar(x_sprint - width/2, t1_sprint_vals, width, label=t1, color=TEAM1_COLOR, alpha=0.85)
    ax2.bar(x_sprint + width/2, t2_sprint_vals, width, label=t2, color=TEAM2_COLOR, alpha=0.85)
    
    ax2.set_xticks(x_sprint)
    ax2.set_xticklabels(sprint_metrics, fontsize=10)
    ax2.set_ylabel('次数', color=TEXT_COLOR)
    ax2.legend(frameon=False, fontsize=10, loc='upper left')
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.spines['left'].set_color(LINE_COLOR)
    ax2.spines['bottom'].set_color(LINE_COLOR)
    ax2.tick_params(colors=TEXT_COLOR)
    ax2.grid(axis='y', alpha=0.3)
    
    # 右侧：最高速度TOP3
    top1 = phys_data[t1].get('top_speed_players', [])
    top2 = phys_data[t2].get('top_speed_players', [])
    
    # 在右侧添加文本区
    ax2_right = ax2.twinx()
    ax2_right.set_facecolor(PITCH_COLOR)
    ax2_right.set_ylim(ax2.get_ylim())
    ax2_right.set_yticks([])
    ax2_right.spines['top'].set_visible(False)
    ax2_right.spines['right'].set_visible(False)
    ax2_right.spines['left'].set_visible(False)
    
    y_max = max(t1_sprints, t2_sprints, t1_hsr, t2_hsr)
    
    ax2.text(1.55, y_max * 0.95, '⚡ 最高速度 TOP3', 
             ha='left', fontsize=11, color='#f0883e', fontweight='bold')
    
    for i in range(3):
        y_pos = y_max * (0.75 - i * 0.2)
        
        # 队1
        if i < len(top1):
            p = top1[i]
            short_name = p['name'].split()[-1] if ' ' in str(p['name']) else str(p['name'])
            ax2.text(1.3, y_pos, f'{i+1}. {short_name}: {p["top_speed"]:.1f} km/h',
                    ha='left', fontsize=9, color=TEAM1_COLOR)
        else:
            ax2.text(1.3, y_pos, f'{i+1}. —', ha='left', fontsize=9, color=LINE_COLOR)
        
        # 队2
        if i < len(top2):
            p = top2[i]
            short_name = p['name'].split()[-1] if ' ' in str(p['name']) else str(p['name'])
            ax2.text(1.85, y_pos, f'{i+1}. {short_name}: {p["top_speed"]:.1f} km/h',
                    ha='left', fontsize=9, color=TEAM2_COLOR)
        else:
            ax2.text(1.85, y_pos, f'{i+1}. —', ha='left', fontsize=9, color=LINE_COLOR)
    
    # 队名标题
    ax2.text(1.3, y_max * 0.88, t1, ha='left', fontsize=10, color=TEAM1_COLOR, fontweight='bold')
    ax2.text(1.85, y_max * 0.88, t2, ha='left', fontsize=10, color=TEAM2_COLOR, fontweight='bold')
    
    plt.tight_layout()
    
    if output_path:
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 体能五分区图 → {output_path}")
        return output_path
    
    return fig


# ========== 批量出图 ==========
def generate_all_charts(df, info, stats, output_dir='./output'):
    """一键生成所有图表，返回 {chart_id: filepath} 字典"""
    _ensure_font_setup()
    
    os.makedirs(output_dir, exist_ok=True)

    chart_paths = {}

    chart_configs = [
        ('shot_map', draw_shot_map, '射门位置图'),
        ('pass_network', draw_pass_network, '传球网络图'),
        ('shot_comparison', draw_shot_comparison, '射门对比'),
        ('xg_flow', draw_xg_flow, 'xG累积曲线'),
        ('possession_timeline', draw_possession_timeline, '控球时间线'),
        ('stats_bar', draw_stats_bar, '核心数据对比'),
        ('pressure_heatmap', draw_pressure_heatmap, '防守热力图'),
        # FIFA专属P0图表（非FIFA模式函数内部返回None）
        ('tactical_radar', draw_tactical_radar, '战术风格雷达图'),
        ('line_breaks', draw_line_breaks, '防线穿透分析'),
        ('cross_tactics', draw_cross_tactics, '传中战术分析'),
        ('physical_zones', draw_physical_zones, '体能五分区图'),
    ]

    for chart_id, func, name in chart_configs:
        path = os.path.join(output_dir, f'{chart_id}.png')
        try:
            import inspect
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())

            if 'stats' in params and 'df' not in params:
                # 只需要stats的函数（如draw_shot_comparison, draw_stats_bar）
                result = func(stats, output_path=path)
            else:
                # 需要df+info+stats的函数
                result = func(df, info, stats, output_path=path)

            if result:
                chart_paths[chart_id] = path
        except Exception as e:
            print(f"[可视化] {name}生成失败：{e}")
            import traceback
            traceback.print_exc()
            chart_paths[chart_id] = None

    print(f"\n[可视化] 完成：{len([v for v in chart_paths.values() if v])}/{len(chart_configs)} 张图 → {output_dir}/")
    return chart_paths
