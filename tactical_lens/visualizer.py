"""
visualizer.py — 可视化引擎
生成：射门位置图、传球网络图、射门对比、xG累积曲线、控球时间线、核心数据对比
风格：深色主题，与HTML报告一致
"""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 无头模式，服务器环境不出窗口
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap

# ========== 全局风格 ==========
BG_COLOR = '#0d1117'
PITCH_COLOR = '#1a2332'
LINE_COLOR = '#3d4f5f'
TEAM1_COLOR = '#00f5c4'
TEAM2_COLOR = '#4da6ff'
GOAL_COLOR = '#f0883e'
TEXT_COLOR = '#e6edf3'
GRID_COLOR = '#21262d'

plt.rcParams.update({
    'figure.facecolor': BG_COLOR,
    'axes.facecolor': PITCH_COLOR,
    'axes.edgecolor': LINE_COLOR,
    'axes.labelcolor': TEXT_COLOR,
    'text.color': TEXT_COLOR,
    'xtick.color': LINE_COLOR,
    'ytick.color': LINE_COLOR,
    'grid.color': GRID_COLOR,
    'font.family': ['Microsoft YaHei', 'sans-serif'],
    'font.size': 10,
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
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('射门位置图', fontsize=16, color=TEXT_COLOR, y=0.98)

    for idx, (team, color) in enumerate(zip(teams, [TEAM1_COLOR, TEAM2_COLOR])):
        ax = axes[idx]
        draw_pitch(ax)

        shots = df[(df['team'] == team) & (df['type'] == 'Shot')].copy()
        if shots.empty:
            ax.set_title(f'{team}\n（无射门数据）', fontsize=12, color=color, pad=10)
            continue

        # 坐标
        xs = shots['x'].values if 'x' in shots.columns else []
        ys = shots['y'].values if 'y' in shots.columns else []
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
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 射门位置图 → {output_path}")
        return output_path

    return fig


# ========== 传球网络图 ==========
def draw_pass_network(df, info, stats, output_path=None, min_passes=3):
    """传球网络图：节点=球员平均位置，边=传球次数，节点大小=传球量"""
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('传球网络图', fontsize=16, color=TEXT_COLOR, y=0.98)

    for idx, (team, color) in enumerate(zip(teams, [TEAM1_COLOR, TEAM2_COLOR])):
        ax = axes[idx]
        draw_pitch(ax)

        team_passes = df[(df['team'] == team) & (df['type'] == 'Pass')].copy()
        if team_passes.empty:
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
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 传球网络图 → {output_path}")
        return output_path

    return fig


# ========== 射门对比 ==========
def draw_shot_comparison(stats, output_path=None):
    """射门数据对比柱状图"""
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

    fig, ax = plt.subplots(figsize=(10, 5))
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
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 射门对比 → {output_path}")
        return output_path

    return fig


# ========== xG累积曲线 ==========
def draw_xg_flow(df, info, stats, output_path=None):
    """xG随时间累积曲线"""
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    fig, ax = plt.subplots(figsize=(12, 5))

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
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] xG累积曲线 → {output_path}")
        return output_path

    return fig


# ========== 控球时间线 ==========
def draw_possession_timeline(df, info, stats, output_path=None, window=5):
    """滚动控球率时间线（每5分钟窗口）"""
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

    fig, ax = plt.subplots(figsize=(12, 5))

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
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 控球时间线 → {output_path}")
        return output_path

    return fig


def _draw_possession_by_events(df, info, stats, output_path=None, window=5):
    """退化为按事件数画控球趋势"""
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

    fig, ax = plt.subplots(figsize=(12, 5))

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
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 节奏时间线 → {output_path}")
        return output_path

    return fig


# ========== 核心数据对比 ==========
def draw_stats_bar(stats, output_path=None):
    """核心数据对比水平柱状图"""
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
    ]

    labels = [m[0] for m in metrics]
    v1 = [m[1] for m in metrics]
    v2 = [m[2] for m in metrics]

    y = np.arange(len(labels))
    height = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
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
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 核心数据对比 → {output_path}")
        return output_path

    return fig


# ========== 批量出图 ==========
def generate_all_charts(df, info, stats, output_dir='./output'):
    """一键生成所有图表，返回 {chart_id: filepath} 字典"""
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
            chart_paths[chart_id] = None

    print(f"\n[可视化] 完成：{len([v for v in chart_paths.values() if v])}/{len(chart_configs)} 张图 → {output_dir}/")
    return chart_paths


# ========== 热力图（bonus）==========
def draw_pressure_heatmap(df, info, stats, team=None, output_path=None, bins=(12, 8)):
    """逼抢/防守行为热力图
    team: 指定队伍，None则画两队
    """
    teams = list(stats.keys())
    if len(teams) < 2:
        return None

    target_teams = [team] if team else teams
    n = len(target_teams)

    fig, axes = plt.subplots(1, n, figsize=(7 * n, 5))
    if n == 1:
        axes = [axes]

    fig.suptitle('防守行为热力图', fontsize=16, color=TEXT_COLOR, y=0.98)

    for idx, t in enumerate(target_teams):
        ax = axes[idx]
        draw_pitch(ax)

        color = TEAM1_COLOR if t == teams[0] else TEAM2_COLOR
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
        from scipy.ndimage import gaussian_filter
        heatmap = gaussian_filter(heatmap, sigma=1)

        extent = [0, 120, 0, 80]
        cmap = LinearSegmentedColormap.from_list('custom',
            [PITCH_COLOR, color, '#ffffff'], N=256)

        ax.imshow(heatmap.T, extent=extent, origin='lower', cmap=cmap,
                  alpha=0.6, aspect='auto', interpolation='bilinear')

        ax.set_title(f'{t}', fontsize=12, color=color, pad=10)

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close(fig)
        print(f"[可视化] 防守热力图 → {output_path}")
        return output_path

    return fig
