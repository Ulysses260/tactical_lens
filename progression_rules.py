"""
progression_rules.py — 推进规则引擎
基于坐标的纯规则判断，不需要训练模型
数据格式：StatsBomb CSV（x:0-120, y:0-80，右方=进攻方向）
"""
import numpy as np
import pandas as pd


# ============================================================
# 坐标常量（StatsBomb标准球场 120×80）
# ============================================================
PITCH_LENGTH = 120
PITCH_WIDTH = 80
HALFWAY = 60          # 中线
FINAL_THIRD = 80      # 进攻三区起始
OWN_THIRD_END = 40    # 防守三区结束
PENALTY_X = 102       # 禁区线x
PENALTY_Y_TOP = 18    # 禁区线上沿
PENALTY_Y_BOT = 62    # 禁区线下沿
GOAL_X = 120          # 球门x
GOAL_Y = 40           # 球门中心y


def dist_to_goal(x, y):
    """计算点到球门中心的距离"""
    return np.sqrt((GOAL_X - x) ** 2 + (GOAL_Y - y) ** 2)


# ============================================================
# 规则1: 推进传球 (Progressive Pass)
# ============================================================
# 三种主流定义，按你需求选一种：

def is_progressive_pass_wyscout(start_x, start_y, end_x, end_y):
    """Wyscout定义：分区阈值法
    - 起终点都在后场(前40%)：需推进≥30米
    - 起点后场→终点前场：需推进≥15米
    - 起终点都在前场(后40%)：需推进≥10米
    """
    if pd.isna(start_x) or pd.isna(end_x):
        return False

    start_in_own = start_x < HALFWAY
    end_in_opp = end_x >= HALFWAY
    forward_dist = end_x - start_x  # 向前推进距离（米）

    if start_in_own and not end_in_opp:
        # 起终点都在后场
        threshold = 30
    elif start_in_own and end_in_opp:
        # 后场→前场
        threshold = 15
    else:
        # 起终点都在前场
        threshold = 10

    return forward_dist >= threshold


def is_progressive_pass_opta(start_x, start_y, end_x, end_y):
    """Opta/学术定义（Deb et al. 2023）：
    - 向球门靠近≥20% + 至少向前5米
    - 排除定位球、传中、头球传球、起点在对方禁区的传球
    """
    if pd.isna(start_x) or pd.isna(end_x):
        return False

    start_dist = dist_to_goal(start_x, start_y)
    end_dist = dist_to_goal(end_x, end_y)
    pct_closer = (start_dist - end_dist) / start_dist  # 靠近百分比
    forward_dist = end_x - start_x

    # 排除起点在对方禁区的传球
    if start_x >= PENALTY_X and PENALTY_Y_TOP <= start_y <= PENALTY_Y_BOT:
        return False

    return pct_closer >= 0.20 and forward_dist >= 5


def is_progressive_pass_statsbomb(start_x, start_y, end_x, end_y):
    """StatsBomb/FBref定义：
    - 防守三区(前40%)起：需靠近球门≥30码(约27.4米)
    - 中场三区起：需靠近≥15码(约13.7米)
    - 进攻三区起：需靠近≥10码(约9.1米)
    只算完成的传球，不计算失败传球
    """
    if pd.isna(start_x) or pd.isna(end_x):
        return False

    start_dist = dist_to_goal(start_x, start_y)
    end_dist = dist_to_goal(end_x, end_y)
    closer = start_dist - end_dist  # 靠近球门的距离

    if start_x < OWN_THIRD_END:
        threshold = 27.4  # 30码≈27.4米
    elif start_x < FINAL_THIRD:
        threshold = 13.7  # 15码
    else:
        threshold = 9.1   # 10码

    return closer >= threshold


# 默认用Wyscout（最常用、最好理解）
is_progressive_pass = is_progressive_pass_wyscout


# ============================================================
# 规则2: 推进带球 (Progressive Carry)
# ============================================================
def is_progressive_carry_wyscout(start_x, start_y, end_x, end_y, min_move=1):
    """Wyscout定义：与推进传球相同的分区阈值
    额外条件：总移动距离>1米（排除位置编码误差）
    """
    if pd.isna(start_x) or pd.isna(end_x):
        return False

    total_dist = np.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)
    if total_dist < min_move:
        return False

    start_in_own = start_x < HALFWAY
    end_in_opp = end_x >= HALFWAY
    forward_dist = end_x - start_x

    if start_in_own and not end_in_opp:
        threshold = 30
    elif start_in_own and end_in_opp:
        threshold = 15
    else:
        threshold = 10

    return forward_dist >= threshold


def is_progressive_carry_pct(start_x, start_y, end_x, end_y, min_move=1):
    """Opta/学术定义：带球靠近球门≥10%
    """
    if pd.isna(start_x) or pd.isna(end_x):
        return False

    total_dist = np.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)
    if total_dist < min_move:
        return False

    start_dist = dist_to_goal(start_x, start_y)
    end_dist = dist_to_goal(end_x, end_y)
    if start_dist == 0:
        return False
    pct_closer = (start_dist - end_dist) / start_dist

    return pct_closer >= 0.10


is_progressive_carry = is_progressive_carry_wyscout


# ============================================================
# 规则3: 传入进攻三区 (Pass into Final Third)
# ============================================================
def is_pass_into_final_third(start_x, start_y, end_x, end_y):
    """传球终点进入进攻三区(x>=80)，且起点不在进攻三区"""
    if pd.isna(start_x) or pd.isna(end_x):
        return False
    return start_x < FINAL_THIRD and end_x >= FINAL_THIRD


# ============================================================
# 规则4: 传入禁区 (Pass into Penalty Area)
# ============================================================
def is_pass_into_box(start_x, start_y, end_x, end_y):
    """传球终点在禁区内，起点在禁区外"""
    if pd.isna(start_x) or pd.isna(end_x):
        return False

    end_in_box = (end_x >= PENALTY_X and
                  PENALTY_Y_TOP <= end_y <= PENALTY_Y_BOT)
    start_in_box = (start_x >= PENALTY_X and
                    PENALTY_Y_TOP <= start_y <= PENALTY_Y_BOT)
    return end_in_box and not start_in_box


# ============================================================
# 规则5: 向前传球 (Forward Pass)
# ============================================================
def is_forward_pass(start_x, start_y, end_x, end_y):
    """Opta定义：传球角度在进攻方向±45°内（即105°~-105°朝向球门）
    简化版：终点x > 起点x（纯粹向前）
    """
    if pd.isna(start_x) or pd.isna(end_x):
        return False
    return end_x > start_x


def is_backward_pass(start_x, start_y, end_x, end_y):
    """向后传球"""
    if pd.isna(start_x) or pd.isna(end_x):
        return False
    return end_x < start_x


def is_sideways_pass(start_x, start_y, end_x, end_y, min_lateral=12):
    """横向传球：横向移动>12米，向前距离<5米"""
    if pd.isna(start_x) or pd.isna(end_x):
        return False
    lateral = abs(end_y - start_y)
    forward = end_x - start_x
    return lateral >= min_lateral and abs(forward) < 5


# ============================================================
# 规则6: 深度推进 (Deep Progression)
# ============================================================
def is_deep_progression(start_x, start_y, end_x, end_y):
    """StatsBomb定义：传球或带球进入对方进攻三区
    起点：不在进攻三区；终点：在进攻三区
    """
    if pd.isna(start_x) or pd.isna(end_x):
        return False
    return start_x < FINAL_THIRD and end_x >= FINAL_THIRD


# ============================================================
# 规则7 & 8: 关键传球 & 直塞球
# ============================================================
# 这两个不需要坐标判断，直接读StatsBomb字段：
# - 关键传球：df['pass_shot_assist'] == True
# - 直塞球：df['pass_through_ball'] == True
# 示例用法见下方 apply_all_rules()


# ============================================================
# 规则9: 大范围转移 (Switch of Play)
# ============================================================
def is_switch_of_play(start_x, start_y, end_x, end_y, min_lateral=27.2):
    """Wyscout/Opta定义：横向移动>27.2米（约2个通道宽度），
    终点在边路通道，且不满足推进传球条件
    """
    if pd.isna(start_x) or pd.isna(end_x):
        return False

    lateral = abs(end_y - start_y)
    forward = end_x - start_x
    end_in_wide = end_y < 20 or end_y > 60  # 终点在边路

    # 不满足推进条件 + 横向移动够大 + 终点在边路
    not_progressive = not is_progressive_pass(start_x, start_y, end_x, end_y)
    return not_progressive and lateral >= min_lateral and end_in_wide


# ============================================================
# 规则10: 推进传球序列检测（你的原创想法！）
# ============================================================
def detect_progressive_sequences(df, team, min_passes=3, progress_threshold=15):
    """检测一支球队的推进传球序列

    核心逻辑：
    1. 按时间排序，找出同队连续完成的传球链
    2. 计算传球链起点到终点向球门靠近了多少米
    3. 靠近≥progress_threshold米的序列 = 推进序列（好配合/进攻亮点）
    4. 反向：对方推进序列集中区域 = 我方防守薄弱点

    参数：
        df: StatsBomb格式DataFrame
        team: 队伍名
        min_passes: 最少传球数（默认3）
        progress_threshold: 向球门靠近多少米才算推进序列（默认15米）

    返回：
        sequences: 推进序列列表，每条包含：
            - passes: 传球详情
            - start_x/y, end_x/y: 起终点
            - progress: 向球门靠近距离
            - is_progressive: 是否为推进序列
    """
    # 筛选该队完成的传球
    team_passes = df[
        (df['team'] == team) &
        (df['type'] == 'Pass') &
        (df['pass_outcome'].isna()) &  # 只算成功的传球
        (df['x'].notna()) &
        (df['pass_end_x'].notna())
    ].sort_values(['match_id', 'period', 'timestamp']).reset_index(drop=True)

    if team_passes.empty:
        return []

    # 构建传球链：同一控球权(possession)内的连续传球
    sequences = []
    if 'possession' in team_passes.columns:
        for poss_id, poss_group in team_passes.groupby('possession'):
            seq_passes = poss_group.to_dict('records')
            if len(seq_passes) < min_passes:
                continue

            # 尝试在控球链内找连续推进的子序列
            sub_seqs = _find_progressive_subsequences(
                seq_passes, min_passes, progress_threshold
            )
            sequences.extend(sub_seqs)
    else:
        # 没有possession字段时，按时间连续性分组
        sub_seqs = _find_progressive_subsequences(
            team_passes.to_dict('records'), min_passes, progress_threshold
        )
        sequences.extend(sub_seqs)

    return sequences


def _find_progressive_subsequences(passes, min_passes, progress_threshold):
    """在一条传球链内，滑动窗口找推进子序列"""
    results = []
    n = len(passes)

    for i in range(n):
        for j in range(i + min_passes - 1, n):
            sub = passes[i:j + 1]
            start_x = sub[0]['x']
            start_y = sub[0]['y']
            end_x = sub[-1]['pass_end_x']
            end_y = sub[-1]['pass_end_y']

            if pd.isna(start_x) or pd.isna(end_x):
                continue

            start_dist = dist_to_goal(start_x, start_y)
            end_dist = dist_to_goal(end_x, end_y)
            progress = start_dist - end_dist  # 正值=靠近球门

            results.append({
                'num_passes': len(sub),
                'start_x': start_x,
                'start_y': start_y,
                'end_x': end_x,
                'end_y': end_y,
                'progress': progress,
                'is_progressive': progress >= progress_threshold,
                'first_passer': sub[0].get('player', 'Unknown'),
                'last_passer': sub[-1].get('player', 'Unknown'),
            })

    # 只返回推进序列，且去掉被更长子序列包含的短序列
    progressive = [s for s in results if s['is_progressive']]

    # 去重：如果短序列完全被长序列覆盖，只保留最长的
    filtered = []
    progressive.sort(key=lambda s: (-s['num_passes'], -s['progress']))
    used_starts = set()
    for seq in progressive:
        key = (seq['start_x'], seq['start_y'])
        if key not in used_starts:
            filtered.append(seq)
            used_starts.add(key)

    return filtered


# ============================================================
# 规则11: 防守薄弱区域检测
# ============================================================
def detect_defensive_vulnerabilities(df, own_team, grid_x=6, grid_y=4,
                                     min_sequences=2):
    """基于对方推进序列的终点分布，找出防守薄弱区域

    逻辑：对方推进序列的终点集中在哪个区域 → 那个区域就是防守薄弱点

    参数：
        df: StatsBomb DataFrame
        own_team: 我方队伍名（检测对方的推进来暴露我方弱点）
        grid_x/y: 将球场分成几格
        min_sequences: 一个格子至少有多少条推进序列终点才算薄弱

    返回：
        weak_zones: 薄弱区域列表
    """
    teams = df['team'].dropna().unique().tolist()
    opp_teams = [t for t in teams if t != own_team]

    all_end_points = []
    for opp in opp_teams:
        seqs = detect_progressive_sequences(df, opp)
        for seq in seqs:
            if seq['is_progressive']:
                all_end_points.append((seq['end_x'], seq['end_y']))

    if not all_end_points:
        return []

    # 将终点分到网格
    zone_size_x = PITCH_LENGTH / grid_x
    zone_size_y = PITCH_WIDTH / grid_y

    zone_counts = {}
    for ex, ey in all_end_points:
        zx = min(int(ex / zone_size_x), grid_x - 1)
        zy = min(int(ey / zone_size_y), grid_y - 1)
        key = (zx, zy)
        zone_counts[key] = zone_counts.get(key, 0) + 1

    # 找出超过阈值的区域
    weak_zones = []
    for (zx, zy), count in zone_counts.items():
        if count >= min_sequences:
            cx = (zx + 0.5) * zone_size_x
            cy = (zy + 0.5) * zone_size_y
            weak_zones.append({
                'zone': (zx, zy),
                'center_x': cx,
                'center_y': cy,
                'sequence_count': count,
                'description': f"区域({cx:.0f},{cy:.0f})被推进{count}次",
            })

    weak_zones.sort(key=lambda z: -z['sequence_count'])
    return weak_zones


# ============================================================
# 规则12: PPDA (Passes Per Defensive Action)
# ============================================================
def compute_ppda(df, team, defensive_actions=None):
    """PPDA：对手每完成一次防守动作前，平均传了多少脚球
    数值越低 = 压迫越凶
    欧洲顶级高位压迫球队 PPDA ≈ 7-9；低位防守 ≈ 15-20

    参数：
        df: StatsBomb DataFrame
        team: 要计算PPDA的队伍
        defensive_actions: 防守事件类型列表
    """
    if defensive_actions is None:
        defensive_actions = ['Pressure', 'Foul Committed', 'Block',
                             'Interception', 'Tackle']

    teams = df['team'].dropna().unique().tolist()
    opp = [t for t in teams if t != team]
    if not opp:
        return None
    opp = opp[0]

    # 对手在我方防守三区及中场的传球数
    opp_passes = df[
        (df['team'] == opp) &
        (df['type'] == 'Pass') &
        (df['x'] < FINAL_THIRD)  # 对手在我方防守区/中场的传球
    ]

    # 我方防守动作数
    team_defs = df[
        (df['team'] == team) &
        (df['type'].isin(defensive_actions))
    ]

    n_passes = len(opp_passes)
    n_defs = len(team_defs)

    if n_defs == 0:
        return None
    return n_passes / n_defs


# ============================================================
# 一键应用所有规则
# ============================================================
def apply_all_rules(df, team):
    """对一支队伍应用所有规则，返回标注后的传球DataFrame"""

    team_df = df[(df['team'] == team) & (df['type'] == 'Pass')].copy()

    # 只处理有坐标的传球
    mask = team_df['x'].notna() & team_df['pass_end_x'].notna()
    passes = team_df[mask].copy()

    # 逐条传球标注
    passes['is_progressive_pass'] = passes.apply(
        lambda r: is_progressive_pass(r['x'], r['y'],
                                       r['pass_end_x'], r['pass_end_y']),
        axis=1
    )
    passes['is_pass_into_final_third'] = passes.apply(
        lambda r: is_pass_into_final_third(r['x'], r['y'],
                                            r['pass_end_x'], r['pass_end_y']),
        axis=1
    )
    passes['is_pass_into_box'] = passes.apply(
        lambda r: is_pass_into_box(r['x'], r['y'],
                                    r['pass_end_x'], r['pass_end_y']),
        axis=1
    )
    passes['is_forward_pass'] = passes.apply(
        lambda r: is_forward_pass(r['x'], r['y'],
                                   r['pass_end_x'], r['pass_end_y']),
        axis=1
    )
    passes['is_backward_pass'] = passes.apply(
        lambda r: is_backward_pass(r['x'], r['y'],
                                    r['pass_end_x'], r['pass_end_y']),
        axis=1
    )
    passes['is_sideways_pass'] = passes.apply(
        lambda r: is_sideways_pass(r['x'], r['y'],
                                    r['pass_end_x'], r['pass_end_y']),
        axis=1
    )
    passes['is_deep_progression'] = passes.apply(
        lambda r: is_deep_progression(r['x'], r['y'],
                                       r['pass_end_x'], r['pass_end_y']),
        axis=1
    )
    passes['is_switch_of_play'] = passes.apply(
        lambda r: is_switch_of_play(r['x'], r['y'],
                                     r['pass_end_x'], r['pass_end_y']),
        axis=1
    )

    # 字段型指标
    if 'pass_shot_assist' in passes.columns:
        passes['is_key_pass'] = passes['pass_shot_assist'] == True
    else:
        passes['is_key_pass'] = False

    if 'pass_through_ball' in passes.columns:
        passes['is_through_ball'] = passes['pass_through_ball'] == True
    else:
        passes['is_through_ball'] = False

    # 带球推进
    carries = df[
        (df['team'] == team) &
        (df['carry_end_x'].notna()) &
        (df['x'].notna())
    ].copy()
    if not carries.empty:
        carries['is_progressive_carry'] = carries.apply(
            lambda r: is_progressive_carry(r['x'], r['y'],
                                            r['carry_end_x'], r['carry_end_y']),
            axis=1
        )

    # 汇总统计
    summary = {
        'progressive_passes': int(passes['is_progressive_pass'].sum()),
        'passes_into_final_third': int(passes['is_pass_into_final_third'].sum()),
        'passes_into_box': int(passes['is_pass_into_box'].sum()),
        'forward_passes': int(passes['is_forward_pass'].sum()),
        'backward_passes': int(passes['is_backward_pass'].sum()),
        'sideways_passes': int(passes['is_sideways_pass'].sum()),
        'deep_progressions': int(passes['is_deep_progression'].sum()),
        'switches_of_play': int(passes['is_switch_of_play'].sum()),
        'key_passes': int(passes['is_key_pass'].sum()),
        'through_balls': int(passes['is_through_ball'].sum()),
        'progressive_carries': int(carries['is_progressive_carry'].sum()) if not carries.empty else 0,
        'total_passes': len(passes),
    }

    # PPDA
    ppda = compute_ppda(df, team)
    if ppda is not None:
        summary['ppda'] = round(ppda, 1)

    # 推进序列
    sequences = detect_progressive_sequences(df, team)
    summary['progressive_sequences'] = len(sequences)

    # 防守薄弱区域
    weak_zones = detect_defensive_vulnerabilities(df, team)
    summary['defensive_weak_zones'] = weak_zones

    return {
        'passes_annotated': passes,
        'carries_annotated': carries,
        'summary': summary,
        'progressive_sequences': sequences,
    }


# ============================================================
# 快速测试（可直接 python progression_rules.py）
# ============================================================
if __name__ == '__main__':
    # 测试单个传球
    print("=== 推进传球测试 ===")
    # 后场内推进35米 → 超过阈值30米，是推进传球
    print(f"后场内 35m: {is_progressive_pass(20, 40, 55, 40)}")    # True (35>30)
    # 后场→前场，推进20米 → 超过阈值15米，是推进传球
    print(f"后场→前场 20m: {is_progressive_pass(30, 40, 70, 40)}")   # True (20>15)
    # 后场→前场，推进10米 → 不够（阈值15米）
    print(f"后场→前场 10m: {is_progressive_pass(45, 40, 55, 40)}")   # False (10<30)
    # 前场短传推进12米 → 应该是（阈值10米）
    print(f"前场推进 12m: {is_progressive_pass(85, 40, 97, 40)}")   # True
    # 传入禁区
    print(f"传入禁区: {is_pass_into_box(80, 40, 105, 40)}")         # True
    # 传入进攻三区
    print(f"传入进攻三区: {is_pass_into_final_third(60, 40, 85, 40)}")  # True
    # 大范围转移
    print(f"大范围转移: {is_switch_of_play(50, 15, 55, 65)}")       # True
