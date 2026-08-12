"""
fifa_adapter.py — FIFA比赛报告数据适配器
功能：将FIFA PDF转出的CSV数据（12个文件）转换为战术透镜平台统一格式，
      使FIFA数据能够被stats_engine、visualizer等模块消费。

适配器模式：新增独立适配器，不改动现有StatsBomb/Catapult逻辑
输出格式：(df, info, stats) 三元组，与stats_engine输出格式兼容

输入CSV文件（csv_dir目录下）：
  01_match_info.csv          — 比赛基本信息（队伍、比分、日期、场馆）
  02_lineups.csv             — 首发与替补阵容
  03_key_stats.csv           — 核心统计（控球、射门、传球、xG等）
  04_phases_of_play.csv      — 比赛阶段占比
  05_attempts_at_goal.csv    — 射门明细（含时间、球员、结果、部位、来源）
  06_crosses.csv             — 传中数据
  07_offers_to_receive.csv   — 接球申请数据
  08_in_possession_distributions.csv — 控球分布（传球、过人、突破等）
  09_in_possession_offers.csv        — 控球时接球申请分布
  10_out_of_possession.csv   — 防守数据（抢断、拦截、压迫等）
  11_physical_data.csv       — 体能数据
  12_passing_network.csv     — 传球网络（球员对传球次数）

限制说明：
  FIFA数据为聚合/摘要数据，非逐事件流数据。因此：
  - 射门事件可完整还原（含时间、球员、结果），但无坐标
  - 传球、防守等只有汇总数据，无法还原逐事件
  - 无x, y坐标数据，所有依赖坐标的图表精度受限
"""
import os
import re
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np


# ========== 辅助函数 ==========

def _read_csv_safe(filepath):
    """安全读取CSV，处理BOM和换行符"""
    if not os.path.exists(filepath):
        return pd.DataFrame()
    df = pd.read_csv(filepath, encoding='utf-8-sig')
    # 去除列名中的BOM和空白
    df.columns = [c.strip().lstrip('\ufeff') for c in df.columns]
    # 去除字符串字段中的\r
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].str.replace('\r', '', regex=False).str.strip()
    return df


def _parse_pct(s):
    """解析百分数字符串 "37.5%" → 37.5"""
    if pd.isna(s):
        return None
    s = str(s).strip()
    if not s:
        return None
    m = re.match(r'([\d.]+)\s*%', s)
    if m:
        return float(m.group(1))
    try:
        return float(s)
    except ValueError:
        return None


def _parse_attempts(s):
    """解析"10(3)"格式 → (总数, 括号内数)"""
    if pd.isna(s):
        return None, None
    s = str(s).strip()
    m = re.match(r'(\d+)\s*\((\d+)\)', s)
    if m:
        return int(m.group(1)), int(m.group(2))
    try:
        return int(s), None
    except ValueError:
        return None, None


def _parse_fraction(s):
    """解析 "2/1" 格式 → (2, 1)"""
    if pd.isna(s):
        return None, None
    s = str(s).strip()
    m = re.match(r'(\d+)\s*/\s*(\d+)', s)
    if m:
        return int(m.group(1)), int(m.group(2))
    try:
        return int(s), None
    except ValueError:
        return None, None


def _map_shot_outcome(fifa_outcome):
    """FIFA射门结果 → StatsBomb风格shot_outcome映射
    
    FIFA取值：
      On Target - Goal          → Goal（进球）
      On Target - Saved         → Saved（被扑）
      Deflected On Target - Saved → Saved（折射后被扑）
      Incomplete - Blocked      → Blocked（被封堵）
      Off Target                → Off T（偏出）
      Incomplete - Player On Ball Error → Off T（控球失误）
    """
    if pd.isna(fifa_outcome):
        return 'Unknown'
    o = str(fifa_outcome).strip().lower()
    if 'goal' in o:
        return 'Goal'
    elif 'saved' in o:
        return 'Saved'
    elif 'blocked' in o:
        return 'Blocked'
    elif 'off target' in o or 'error' in o:
        return 'Off T'
    else:
        return 'Unknown'


def _map_body_part(fifa_body_part):
    """FIFA射门部位 → StatsBomb风格shot_body_part"""
    if pd.isna(fifa_body_part):
        return None
    b = str(fifa_body_part).strip()
    mapping = {
        'Left Foot': 'Left Foot',
        'Right Foot': 'Right Foot',
        'Head': 'Head',
    }
    return mapping.get(b, b)


def _estimate_xg_per_shot(shots_df, total_xg):
    """根据射门结果类型估算每脚射门的xG，使总和等于球队总xG
    
    基准权重（基于典型xG分布）：
      Goal: 0.50   （进球通常来自高质量机会）
      Saved: 0.25  （射正被扑的机会质量中等）
      Blocked: 0.08（被封堵通常质量较低）
      Off T: 0.08  （射偏通常质量较低）
    """
    if total_xg <= 0 or shots_df.empty:
        return np.zeros(len(shots_df))
    
    outcome_weights = {
        'Goal': 0.50,
        'Saved': 0.25,
        'Blocked': 0.08,
        'Off T': 0.08,
        'Unknown': 0.10,
    }
    
    weights = np.array([outcome_weights.get(o, 0.1) for o in shots_df['shot_outcome']])
    weight_sum = weights.sum()
    
    if weight_sum == 0:
        return np.full(len(shots_df), total_xg / len(shots_df))
    
    # 归一化使总和等于 total_xg
    xg_values = weights / weight_sum * total_xg
    return xg_values


def _compute_attack_defense_ratio(pass_count, defense_score, shot_count):
    """计算球员的攻防水准比率，用于位置分类
    
    返回值越高越偏向进攻，越低越偏向防守
    """
    if pass_count == 0 and defense_score == 0 and shot_count == 0:
        return 0.5  # 中性
    
    # 进攻指标：射门数 * 10 + 传球数 * 0.5
    attack_score = shot_count * 10 + pass_count * 0.3
    # 防守指标：防守得分
    def_score = defense_score + pass_count * 0.1  # 后卫传球也多
    
    total = attack_score + def_score
    if total == 0:
        return 0.5
    return attack_score / total


def _classify_outfield_players(players_data, n_defenders_target=4, n_midfielders_target=3, n_forwards_target=3):
    """对非门将球员进行位置分类
    
    使用攻防比率排序法：
    1. 计算每个球员的攻防比率
    2. 按比率从低到高排序
    3. 前N个为后卫，中间M个为中场，后K个为前锋
    
    参数:
        players_data: [{name, passes, defense, shots, clearances, shirt}, ...]
        n_defenders_target: 目标后卫数
        n_midfielders_target: 目标中场数
        n_forwards_target: 目标前锋数
    
    返回: {name: position}
    """
    if not players_data:
        return {}
    
    n = len(players_data)
    total_outfield = n_defenders_target + n_midfielders_target + n_forwards_target
    
    # 按实际人数调整比例
    if n <= total_outfield:
        # 人少就按比例分配
        n_df = max(1, round(n * n_defenders_target / total_outfield))
        n_fw = max(1, round(n * n_forwards_target / total_outfield))
        n_mf = max(0, n - n_df - n_fw)
    else:
        n_df = n_defenders_target
        n_fw = n_forwards_target
        n_mf = n_midfielders_target
    
    # 计算攻防比率
    for p in players_data:
        p['ad_ratio'] = _compute_attack_defense_ratio(
            p['passes'], p['defense'], p['shots']
        )
    
    # 按攻防比率从低到高排序（防守型在前）
    sorted_players = sorted(players_data, key=lambda x: x['ad_ratio'])
    
    positions = {}
    for i, p in enumerate(sorted_players):
        if i < n_df:
            positions[p['name']] = 'DF'
        elif i < n_df + n_mf:
            positions[p['name']] = 'MF'
        else:
            positions[p['name']] = 'FW'
    
    return positions


def _identify_goalkeeper(player_features, known_gk=None):
    """从球员中识别门将
    
    识别优先级：
    1. lineups中已知的GK
    2. 号码为1, 12, 13, 16, 22, 23等典型门将号码 + 解围数高
    3. 解围数远高于其他球员
    """
    if known_gk and known_gk in player_features:
        return known_gk
    
    gk_numbers = {1, 12, 13, 16, 22, 23, 30}
    
    # 先找号码匹配 + 解围/防守特征匹配的
    candidates = []
    for name, feat in player_features.items():
        if feat['shirt'] in gk_numbers:
            score = feat['clearances'] * 2 + feat['passes'] * 0.1
            candidates.append((name, score))
    
    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
    
    # 兜底：解围最多的
    max_clr = -1
    best = None
    for name, feat in player_features.items():
        if feat['clearances'] > max_clr:
            max_clr = feat['clearances']
            best = name
    return best


def _derive_formation_enhanced(lineups_df, pos_dist_df, defense_df, attempts_df, team):
    """增强版阵型推导：从多数据源汇总球员并推断位置
    
    步骤：
    1. 从lineups获取已知首发位置
    2. 从控球分布数据筛选出数据量最高的11人作为首发
    3. 识别门将
    4. 对剩余10名非门将球员按攻防比率分类为DF/MF/FW
    5. 输出标准阵型格式（如"4-3-3"）
    
    返回: "4-3-3" 格式的阵型字符串
    """
    # 1. 从lineups获取已知位置
    known_positions = {}
    known_starters = set()
    if not lineups_df.empty:
        starters = lineups_df[
            (lineups_df['team'] == team) & 
            (lineups_df['role'] == 'starting')
        ]
        for _, row in starters.iterrows():
            name = row.get('player_name', '')
            pos = row.get('position', '')
            if name and pos and pos in ['GK', 'DF', 'MF', 'FW']:
                known_positions[name] = pos
                known_starters.add(name)
    
    # 2. 构建所有球员的特征数据
    player_features = {}
    
    # 传球数据
    if not pos_dist_df.empty:
        team_pos = pos_dist_df[pos_dist_df['team'] == team]
        for _, row in team_pos.iterrows():
            name = row.get('player_name', '')
            if not name:
                continue
            if name not in player_features:
                player_features[name] = {'name': name, 'passes': 0, 'defense': 0, 'shots': 0, 'clearances': 0, 'shirt': 0}
            player_features[name]['passes'] = int(row.get('passes_completed', 0))
            try:
                player_features[name]['shirt'] = int(row.get('shirt_number', 0))
            except (ValueError, TypeError):
                pass
    
    # 防守数据
    if not defense_df.empty:
        team_def = defense_df[defense_df['team'] == team]
        for _, row in team_def.iterrows():
            name = row.get('player_name', '')
            if not name:
                continue
            if name not in player_features:
                player_features[name] = {'name': name, 'passes': 0, 'defense': 0, 'shots': 0, 'clearances': 0, 'shirt': 0}
            
            tackles_made, tackles_won = _parse_fraction(row.get('tackles_made_won', '0/0'))
            blocks = int(row.get('blocks', 0))
            interceptions = int(row.get('interceptions', 0))
            clearances = int(row.get('clearances', 0))
            
            defense_score = (tackles_won or 0) * 2 + blocks + interceptions * 2
            player_features[name]['defense'] = defense_score
            player_features[name]['clearances'] = clearances
            
            if player_features[name]['shirt'] == 0:
                try:
                    player_features[name]['shirt'] = int(row.get('shirt_number', 0))
                except (ValueError, TypeError):
                    pass
    
    # 射门数据
    if not attempts_df.empty:
        team_att = attempts_df[attempts_df['team'] == team]
        for _, row in team_att.iterrows():
            name = row.get('player_name', '')
            if not name:
                continue
            if name not in player_features:
                player_features[name] = {'name': name, 'passes': 0, 'defense': 0, 'shots': 0, 'clearances': 0, 'shirt': 0}
            player_features[name]['shots'] += 1
            if player_features[name]['shirt'] == 0:
                try:
                    player_features[name]['shirt'] = int(row.get('shirt_number', 0))
                except (ValueError, TypeError):
                    pass
    
    if not player_features:
        return 'N/A'
    
    # 3. 筛选首发11人
    # 已知首发优先，其余按数据量（传球数+防守+射门）补充
    all_player_list = list(player_features.values())
    
    # 按活跃度排序
    all_player_list.sort(
        key=lambda x: x['passes'] * 2 + x['defense'] + x['shots'] * 5, 
        reverse=True
    )
    
    # 已知的门将必须算
    known_gk_name = None
    for name, pos in known_positions.items():
        if pos == 'GK':
            known_gk_name = name
            break
    
    # 先选出已知首发
    starting_xi = {}
    for name in known_starters:
        if name in player_features:
            starting_xi[name] = player_features[name]
    
    # 如果已知首发不足11人，按活跃度补充
    if len(starting_xi) < 11:
        for p in all_player_list:
            if len(starting_xi) >= 11:
                break
            if p['name'] not in starting_xi:
                starting_xi[p['name']] = p
    
    # 4. 识别门将
    gk_name = _identify_goalkeeper(
        {name: feat for name, feat in starting_xi.items()},
        known_gk=known_gk_name
    )
    
    # 5. 非门将球员
    outfield_players = []
    for name, feat in starting_xi.items():
        if name != gk_name:
            outfield_players.append(feat)
    
    # 6. 对非门将球员分类
    # 先使用已知位置
    classified = {}
    unclassified = []
    
    for p in outfield_players:
        name = p['name']
        if name in known_positions and known_positions[name] in ['DF', 'MF', 'FW']:
            classified[name] = known_positions[name]
        else:
            unclassified.append(p)
    
    # 统计已知各位置人数
    n_known_df = sum(1 for v in classified.values() if v == 'DF')
    n_known_mf = sum(1 for v in classified.values() if v == 'MF')
    n_known_fw = sum(1 for v in classified.values() if v == 'FW')
    
    # 目标10名非门将球员，按标准4-3-3分配剩余名额
    target_df = max(n_known_df, 4)
    target_fw = max(n_known_fw, 3)
    target_mf = 10 - target_df - target_fw
    
    if target_mf < 1:
        # 调整，确保至少1个中场
        target_mf = 1
        if n_known_df > n_known_fw:
            target_df = 10 - target_mf - target_fw
        else:
            target_fw = 10 - target_mf - target_df
    
    # 需要补充的数量
    need_df = max(0, target_df - n_known_df)
    need_mf = max(0, target_mf - n_known_mf)
    need_fw = max(0, target_fw - n_known_fw)
    
    # 实际需要分类的人数
    total_need = need_df + need_mf + need_fw
    if len(unclassified) < total_need:
        # 人不够，按比例缩减
        ratio = len(unclassified) / max(total_need, 1)
        need_df = max(0, round(need_df * ratio))
        need_fw = max(0, round(need_fw * ratio))
        need_mf = max(0, len(unclassified) - need_df - need_fw)
    
    # 对未分类球员按攻防比率分类
    if unclassified:
        new_classified = _classify_outfield_players(
            unclassified,
            n_defenders_target=need_df,
            n_midfielders_target=need_mf,
            n_forwards_target=need_fw
        )
        classified.update(new_classified)
    
    # 7. 统计各位置人数
    df_count = sum(1 for v in classified.values() if v == 'DF')
    mf_count = sum(1 for v in classified.values() if v == 'MF')
    fw_count = sum(1 for v in classified.values() if v == 'FW')
    
    # 8. 构建阵型字符串（标准格式：后卫-中场-前锋）
    formation_parts = []
    if df_count > 0:
        formation_parts.append(str(df_count))
    if mf_count > 0:
        formation_parts.append(str(mf_count))
    if fw_count > 0:
        formation_parts.append(str(fw_count))
    
    formation = '-'.join(formation_parts) if formation_parts else 'N/A'
    
    return formation


def _extract_fouls_from_defense(defense_df, team):
    """从防守数据中估算犯规次数
    
    FIFA数据没有直接的犯规统计，使用以下指标估算：
    - possession_interrupted（控球中断）：很大一部分由犯规造成
    - 抢断失败（tackles_made - tackles_won）：失败的抢断容易造成犯规
    
    估算公式：犯规 ≈ 控球中断数 * 0.3 + 抢断失败数 * 0.5
    并确保数值在合理范围内
    """
    if defense_df.empty:
        return 0
    
    team_def = defense_df[defense_df['team'] == team]
    if team_def.empty:
        return 0
    
    total_interrupted = 0
    total_tackles_made = 0
    total_tackles_won = 0
    
    for _, row in team_def.iterrows():
        # 控球中断
        interrupted = int(row.get('possession_interrupted', 0))
        total_interrupted += interrupted
        
        # 抢断
        made, won = _parse_fraction(row.get('tackles_made_won', '0/0'))
        total_tackles_made += made or 0
        total_tackles_won += won or 0
    
    # 估算犯规次数
    tackle_fouls = max(0, total_tackles_made - total_tackles_won) * 0.4
    other_fouls = total_interrupted * 0.2
    estimated_fouls = int(tackle_fouls + other_fouls)
    
    # 确保合理性：一场比赛通常犯规在8-20次之间
    estimated_fouls = max(5, min(estimated_fouls, 25))
    
    return estimated_fouls


def _extract_key_passes(pos_dist_df, team):
    """从控球分布数据中提取关键传球（近似值）
    
    使用 line_breaks_completed（突破防线完成传球）作为关键传球的近似，
    因为关键传球的核心特征是"创造得分机会的传球"，而突破防线的传球
    最接近这一定义。
    """
    if pos_dist_df.empty:
        return 0
    
    team_pos = pos_dist_df[pos_dist_df['team'] == team]
    if team_pos.empty:
        return 0
    
    total_line_breaks = 0
    for _, row in team_pos.iterrows():
        lb = int(row.get('line_breaks_completed', 0))
        total_line_breaks += lb
    
    return total_line_breaks


# ========== P0新图表数据提取函数 ==========

def _extract_tactical_radar_data(phases_df, teams):
    """从比赛阶段数据中提取战术雷达图数据
    
    进攻维度（7个）：
      - 组织: Build Up Unopposed + Build Up Opposed
      - 推进: Progression
      - 最后三分之一: Final Third
      - 反击: Counter Attack
      - 长传: Long Ball
      - 定位球: Set Piece
      - 进攻转换: Attacking Transition
    
    防守维度（7个）：
      - 高位压迫: High Press
      - 高位防线: High Block
      - 中位压迫: Mid Press
      - 中位防线: Mid Block
      - 低位防线: Low Block
      - 反抢: Counter-press
      - 防守转换: Defensive Transition
    
    返回: {
        team: {
            'attack': {dim_name: pct},
            'defense': {dim_name: pct},
            'attack_dims': [...],
            'defense_dims': [...],
        }
    }
    """
    if phases_df.empty:
        return {}
    
    result = {}
    attack_dim_map = {
        '组织': ['Build Up Unopposed', 'Build Up Opposed'],
        '推进': ['Progression'],
        '最后三分之一': ['Final Third'],
        '反击': ['Counter Attack'],
        '长传': ['Long Ball'],
        '定位球': ['Set Piece'],
        '进攻转换': ['Attacking Transition'],
    }
    defense_dim_map = {
        '高位压迫': ['High Press'],
        '高位防线': ['High Block'],
        '中位压迫': ['Mid Press'],
        '中位防线': ['Mid Block'],
        '低位防线': ['Low Block'],
        '反抢': ['Counter-press'],
        '防守转换': ['Defensive Transition'],
    }
    
    in_possession = phases_df[phases_df['phase_category'] == 'In Possession']
    out_possession = phases_df[phases_df['phase_category'] == 'Out of Possession']
    
    for team_key, team_name in [('home', teams[0]), ('away', teams[1])]:
        pct_col = 'home_pct' if team_key == 'home' else 'away_pct'
        
        # 进攻维度
        attack_values = {}
        for dim_name, phase_names in attack_dim_map.items():
            total = 0
            for pn in phase_names:
                row = in_possession[in_possession['phase_name'] == pn]
                if not row.empty:
                    val = _parse_pct(row.iloc[0][pct_col])
                    if val is not None:
                        total += val
            attack_values[dim_name] = round(total, 1)
        
        # 防守维度
        defense_values = {}
        for dim_name, phase_names in defense_dim_map.items():
            total = 0
            for pn in phase_names:
                row = out_possession[out_possession['phase_name'] == pn]
                if not row.empty:
                    val = _parse_pct(row.iloc[0][pct_col])
                    if val is not None:
                        total += val
            defense_values[dim_name] = round(total, 1)
        
        result[team_name] = {
            'attack': attack_values,
            'defense': defense_values,
            'attack_dims': list(attack_dim_map.keys()),
            'defense_dims': list(defense_dim_map.keys()),
        }
    
    return result


def _extract_line_breaks_data(pos_dist_df, teams):
    """从控球分布数据中提取防线穿透分析数据
    
    返回: {
        team: {
            'attempts': int,      # 突破尝试次数
            'completed': int,     # 成功次数
            'success_rate': float, # 成功率
            'goals': int,          # 突破后进球
            'top_players': [{name, attempts, completed, goals}]  # TOP3
        }
    }
    """
    if pos_dist_df.empty:
        return {}
    
    result = {}
    
    for team in teams:
        team_data = pos_dist_df[pos_dist_df['team'] == team].copy()
        if team_data.empty:
            result[team] = {'attempts': 0, 'completed': 0, 'success_rate': 0, 'goals': 0, 'top_players': []}
            continue
        
        total_attempts = int(team_data['line_breaks_attempted'].sum())
        total_completed = int(team_data['line_breaks_completed'].sum())
        total_goals = int(team_data['line_break_goals'].sum())
        success_rate = round(total_completed / max(total_attempts, 1) * 100, 1)
        
        # 球员TOP3（按成功突破数排序）
        player_stats = team_data[team_data['line_breaks_completed'] > 0].copy()
        player_stats = player_stats.sort_values('line_breaks_completed', ascending=False).head(3)
        
        top_players = []
        for _, row in player_stats.iterrows():
            top_players.append({
                'name': row.get('player_name', ''),
                'attempts': int(row.get('line_breaks_attempted', 0)),
                'completed': int(row.get('line_breaks_completed', 0)),
                'goals': int(row.get('line_break_goals', 0)),
            })
        
        result[team] = {
            'attempts': total_attempts,
            'completed': total_completed,
            'success_rate': success_rate,
            'goals': total_goals,
            'top_players': top_players,
        }
    
    return result


def _extract_cross_tactics_data(crosses_df, pos_dist_df, teams):
    """从传中数据中提取传中战术分析数据
    
    6种传中类型：inswing(内旋)、outswing(外旋)、driven(平抽)、
                 lofted(高吊)、cutback(倒三角)、push_cross(推传中)
    
    返回: {
        team: {
            'type_distribution': {type_name: count},  # 各类型传中数
            'type_names_cn': {type_en: type_cn},      # 中文名映射
            'total_attempted': int,
            'total_completed': int,
            'success_rate': float,
        }
    }
    """
    # 两个数据源都为空时返回空字典
    if crosses_df.empty and pos_dist_df.empty:
        return {}
    
    result = {}
    
    type_names_cn = {
        'inswing': '内旋',
        'outswing': '外旋',
        'driven': '平抽',
        'lofted': '高吊',
        'cutback': '倒三角',
        'push_cross': '推传中',
    }
    
    cross_types = ['inswing', 'outswing', 'driven', 'lofted', 'cutback', 'push_cross']
    
    for team in teams:
        type_dist = {}
        total_attempted = 0
        total_completed = 0
        
        # 先从控球分布数据获取总数（更全面准确）
        if not pos_dist_df.empty:
            team_pos = pos_dist_df[pos_dist_df['team'] == team]
            if not team_pos.empty:
                if 'crosses_attempted' in team_pos.columns:
                    total_attempted = int(team_pos['crosses_attempted'].sum())
                if 'crosses_completed' in team_pos.columns:
                    total_completed = int(team_pos['crosses_completed'].sum())
        
        # 从传中明细数据获取类型分布
        if not crosses_df.empty:
            team_crosses = crosses_df[crosses_df['team'] == team]
            type_total = 0
            for ct in cross_types:
                if ct in team_crosses.columns:
                    cnt = int(team_crosses[ct].sum())
                    type_dist[ct] = cnt
                    type_total += cnt
            # 如果pos_dist没有总数，用类型分布总和
            if total_attempted == 0:
                total_attempted = type_total
        
        success_rate = round(total_completed / max(total_attempted, 1) * 100, 1)
        
        result[team] = {
            'type_distribution': type_dist,
            'type_names_cn': type_names_cn,
            'total_attempted': total_attempted,
            'total_completed': total_completed,
            'success_rate': success_rate,
        }
    
    return result


def _extract_physical_zones_data(physical_df, teams):
    """从体能数据中提取五分区体能数据
    
    5个分区：zone1_walk(走)、zone2_jog(慢跑)、zone3_run(跑)、
             zone4_low_sprint(低速冲刺)、zone5_high_sprint(高速冲刺)
    
    返回: {
        team: {
            'zones': {zone_name: distance_m},
            'zone_names_cn': {zone_en: zone_cn},
            'total_distance': float,
            'sprints_count': int,       # zone4+5冲刺次数
            'high_speed_runs': int,     # 高速跑次数
            'top_speed_players': [{name, top_speed}]  # 最高速度TOP3
        }
    }
    """
    result = {}
    
    zone_names_cn = {
        'zone1_walk': '走',
        'zone2_jog': '慢跑',
        'zone3_run': '跑',
        'zone4_low_sprint': '低速冲刺',
        'zone5_high_sprint': '高速冲刺',
    }
    
    zones = ['zone1_walk_m', 'zone2_jog_m', 'zone3_run_m', 'zone4_low_sprint_m', 'zone5_high_sprint_m']
    
    for team in teams:
        zone_dist = {}
        total_distance = 0.0
        total_sprints = 0
        total_high_speed_runs = 0
        
        if physical_df.empty:
            result[team] = {
                'zones': zone_dist,
                'zone_names_cn': zone_names_cn,
                'total_distance': 0,
                'sprints_count': 0,
                'high_speed_runs': 0,
                'top_speed_players': [],
            }
            continue
        
        team_phys = physical_df[physical_df['team'] == team].copy()
        if team_phys.empty:
            result[team] = {
                'zones': zone_dist,
                'zone_names_cn': zone_names_cn,
                'total_distance': 0,
                'sprints_count': 0,
                'high_speed_runs': 0,
                'top_speed_players': [],
            }
            continue
        
        # 各分区距离（全队总和）
        for z in zones:
            if z in team_phys.columns:
                dist = float(team_phys[z].sum())
                key = z.replace('_m', '')
                zone_dist[key] = round(dist, 1)
                total_distance += dist
        
        # 冲刺次数
        if 'sprints_zone4_5' in team_phys.columns:
            total_sprints = int(team_phys['sprints_zone4_5'].sum())
        if 'high_speed_runs_zone3' in team_phys.columns:
            total_high_speed_runs = int(team_phys['high_speed_runs_zone3'].sum())
        
        # 最高速度TOP3
        top_speed_players = []
        if 'top_speed_kmh' in team_phys.columns:
            top_speeds = team_phys.nlargest(3, 'top_speed_kmh')
            for _, row in top_speeds.iterrows():
                top_speed_players.append({
                    'name': row.get('player_name', ''),
                    'top_speed': round(float(row.get('top_speed_kmh', 0)), 1),
                })
        
        result[team] = {
            'zones': zone_dist,
            'zone_names_cn': zone_names_cn,
            'total_distance': round(total_distance, 1),
            'sprints_count': total_sprints,
            'high_speed_runs': total_high_speed_runs,
            'top_speed_players': top_speed_players,
        }
    
    return result


def _build_player_defense_stats(defense_df, pos_dist_df, team):
    """构建球员级防守数据，用于FIFA模式防守热力图
    
    返回 DataFrame，包含：player_name, defense_score, tackles, blocks, 
    interceptions, clearances, pressing, approx_x, approx_y
    """
    if defense_df.empty:
        return pd.DataFrame()
    
    team_def = defense_df[defense_df['team'] == team].copy()
    if team_def.empty:
        return pd.DataFrame()
    
    # 计算防守综合得分
    defense_scores = []
    for _, row in team_def.iterrows():
        tackles_made, tackles_won = _parse_fraction(row.get('tackles_made_won', '0/0'))
        blocks = int(row.get('blocks', 0))
        interceptions = int(row.get('interceptions', 0))
        clearances = int(row.get('clearances', 0))
        pressing = int(row.get('pressing_direct', 0)) + int(row.get('pressing_indirect', 0))
        
        score = (tackles_won or 0) * 3 + blocks * 2 + interceptions * 3 + pressing * 0.5
        
        defense_scores.append({
            'player_name': row.get('player_name', ''),
            'defense_score': score,
            'tackles_won': tackles_won or 0,
            'blocks': blocks,
            'interceptions': interceptions,
            'clearances': clearances,
            'pressing': pressing,
        })
    
    df = pd.DataFrame(defense_scores)
    
    # 估算球员场上位置（用于热力图近似坐标）
    # 基于防守数据特征粗略分配x坐标（从后到前）
    if not df.empty:
        n = len(df)
        # 按解围数+防守得分排序，解围多的在后场
        df_sorted = df.sort_values(['clearances', 'defense_score'], ascending=[False, False]).reset_index(drop=True)
        
        # 分配近似坐标（StatsBomb坐标系：x∈[0,120], y∈[0,80]）
        # 后卫在x=30附近，中场在x=60，前锋在x=90
        positions = []
        for i in range(n):
            # 根据防守类型判断大致位置
            row = df_sorted.iloc[i]
            if row['clearances'] > 10:  # 门将/后卫
                x = 20 + (i % 3) * 15
                y = 20 + (i // 3) * 20
            elif row['interceptions'] > 2:  # 中场
                x = 50 + (i % 3) * 10
                y = 15 + (i // 3) * 25
            else:  # 前锋
                x = 80 + (i % 3) * 10
                y = 20 + (i // 3) * 20
            
            positions.append({'approx_x': min(max(x, 5), 115), 'approx_y': min(max(y, 5), 75)})
        
        pos_df = pd.DataFrame(positions)
        df_sorted = pd.concat([df_sorted, pos_df], axis=1)
        df = df_sorted
    
    return df


# ========== 主适配器函数 ==========

def load_fifa_from_csv(csv_dir, match_name=None):
    """加载FIFA比赛报告CSV目录，返回统一格式 (df, info, stats)
    
    参数：
        csv_dir: FIFA CSV文件所在目录路径
        match_name: 比赛名称，为空则从match_info中自动生成
    
    返回：
        df: DataFrame — 事件流（仅射门事件可还原，其余字段留空/NA）
        info: dict — 比赛元信息，含limited_features标记受限功能
        stats: dict — 与stats_engine输出格式一致的统计字典
    
    示例：
        df, info, stats = load_fifa_from_csv('/path/to/csv_output/', '加拿大vs摩洛哥')
    
    缺文件降级规则：
        - 核心文件（match_info, lineups, key_stats, attempts_at_goal）缺失 → 抛出ValueError
        - 非核心文件缺失 → 跳过对应图表，不崩溃
    """
    # ---- 步骤0：目录存在性检查 ----
    if not os.path.isdir(csv_dir):
        raise ValueError(f"CSV目录不存在: {csv_dir}")
    
    # ---- 步骤1：读取所有CSV文件（关键词匹配，兼容有无编号前缀） ----
    all_csvs = [f for f in os.listdir(csv_dir) if f.lower().endswith('.csv')]
    
    def _find_csv(keyword):
        """在目录中找包含指定关键词的CSV文件（不区分大小写）"""
        kw = keyword.lower()
        for fname in all_csvs:
            if kw in fname.lower():
                return os.path.join(csv_dir, fname)
        return None
    
    # 核心文件（缺失则报错）
    # 注意：match_info不是必须的，队名可以从lineups/key_stats/attempts等文件推断
    CORE_FILES = {
        'lineups': 'lineups',
        'key_stats': 'key_stats',
        'attempts': 'attempts_at_goal',
    }
    
    # 非核心文件（缺失则跳过对应图表）
    OPTIONAL_FILES = {
        'match_info': 'match_info',
        'phases': 'phases_of_play',
        'crosses': 'crosses',
        'offers': 'offers_to_receive',
        'possession_dist': 'in_possession_distributions',
        'possession_offers': 'in_possession_offers',
        'defense': 'out_of_possession',
        'physical': 'physical_data',
        'passing_network': 'passing_network',
    }
    
    # 加载所有文件（核心+非核心统一加载，缺失的为空DataFrame）
    all_files = {**CORE_FILES, **OPTIONAL_FILES}
    csv_files = {}
    for key, keyword in all_files.items():
        csv_files[key] = _find_csv(keyword)
    
    data = {}
    for key, filepath in csv_files.items():
        if filepath is not None:
            data[key] = _read_csv_safe(filepath)
        else:
            data[key] = pd.DataFrame()
    
    # 检查：至少需要能推断出球队名的数据
    # 从有team列的文件中提取队名，按优先级尝试
    teams = None
    team_source = None
    for key in ['lineups', 'attempts', 'defense', 'physical', 'possession_dist']:
        df = data.get(key, pd.DataFrame())
        if not df.empty and 'team' in df.columns:
            unique_teams = df['team'].dropna().unique().tolist()
            if len(unique_teams) >= 2:
                teams = unique_teams[:2]
                team_source = key
                break
    
    # 如果有key_stats但没有team列数据，从key_stats推断（home/away模式）
    if teams is None and not data['key_stats'].empty:
        ks_df = data['key_stats']
        # key_stats通常有home_team/away_team列或home_value/away_value
        for col in ks_df.columns:
            if 'home' in col.lower() and 'team' in col.lower():
                home_team = str(ks_df[col].iloc[0]) if len(ks_df) > 0 else '主队'
            if 'away' in col.lower() and 'team' in col.lower():
                away_team = str(ks_df[col].iloc[0]) if len(ks_df) > 0 else '客队'
        # 如果从列名能判断，尝试命名
        if 'home_value' in ks_df.columns and 'away_value' in ks_df.columns:
            teams = ['主队', '客队']
            team_source = 'key_stats_placeholder'
    
    if teams is None or len(teams) < 2:
        raise ValueError(
            "无法从文件中识别出两支球队。请确保上传的文件中包含lineups、attempts、key_stats等至少一个能区分两队的文件。"
        )
    
    missing_count = sum(1 for key in CORE_FILES if csv_files[key] is None)
    if missing_count >= 2:  # 3个核心文件缺2个以上才报错
        missing_core = [CORE_FILES[k] for k in CORE_FILES if csv_files[k] is None]
        print(f"[FIFA适配器] 警告：核心文件缺失较多（{', '.join(missing_core)}），部分功能将不可用")
    
    missing_optional = [OPTIONAL_FILES[k] for k in OPTIONAL_FILES if csv_files.get(k) is None]
    if missing_optional:
        print(f"[FIFA适配器] 以下文件缺失，对应图表将跳过：{', '.join(missing_optional)}")
    
    # ---- 步骤2：解析比赛基本信息 ----
    match_info_df = data['match_info']
    info_dict = dict(zip(match_info_df['field'], match_info_df['value'])) \
        if not match_info_df.empty else {}
    
    # 优先用match_info的队名，没有则用前面推断出的teams
    if info_dict.get('home_team') and info_dict.get('away_team'):
        home_team = info_dict['home_team']
        away_team = info_dict['away_team']
    elif teams and len(teams) >= 2:
        home_team, away_team = teams[0], teams[1]
    else:
        home_team, away_team = '主队', '客队'
    
    # 比分优先从match_info取，没有则从key_stats的Goals行取
    home_score = int(info_dict.get('home_score', 0))
    away_score = int(info_dict.get('away_score', 0))
    
    # 如果match_info没比分，尝试从key_stats里取
    if (home_score == 0 and away_score == 0) and not data['key_stats'].empty:
        ks_df = data['key_stats']
        goals_row = ks_df[ks_df['stat_name'].astype(str).str.contains('Goal', case=False, na=False)]
        if not goals_row.empty:
            try:
                home_score = int(float(goals_row.iloc[0]['home_value']))
                away_score = int(float(goals_row.iloc[0]['away_value']))
            except (ValueError, TypeError, KeyError):
                pass
    
    if match_name is None:
        match_name = f"{home_team} vs {away_team}"
    
    teams = [home_team, away_team]
    
    # ---- 步骤3：解析核心统计数据 ----
    key_stats_df = data['key_stats']
    team_stats = {team: {} for team in teams}
    
    if not key_stats_df.empty:
        for _, row in key_stats_df.iterrows():
            stat_name = row['stat_name']
            home_val = row['home_value']
            away_val = row['away_value']
            
            if stat_name == 'Total Possession':
                team_stats[home_team]['possession_pct'] = _parse_pct(home_val)
                team_stats[away_team]['possession_pct'] = _parse_pct(away_val)
            
            elif stat_name == 'Goals':
                team_stats[home_team]['goals'] = int(home_val) if str(home_val).isdigit() else 0
                team_stats[away_team]['goals'] = int(away_val) if str(away_val).isdigit() else 0
            
            elif stat_name == 'xG (Expected Goals)':
                try:
                    team_stats[home_team]['xg'] = float(home_val)
                except (ValueError, TypeError):
                    team_stats[home_team]['xg'] = 0
                try:
                    team_stats[away_team]['xg'] = float(away_val)
                except (ValueError, TypeError):
                    team_stats[away_team]['xg'] = 0
            
            elif stat_name == 'Attempts at Goal (On Target)':
                h_total, h_on_target = _parse_attempts(home_val)
                a_total, a_on_target = _parse_attempts(away_val)
                team_stats[home_team]['shots_total'] = h_total or 0
                team_stats[home_team]['shots_on_target'] = h_on_target or 0
                team_stats[away_team]['shots_total'] = a_total or 0
                team_stats[away_team]['shots_on_target'] = a_on_target or 0
            
            elif stat_name == 'Total Passes (Complete)':
                h_total, h_completed = _parse_attempts(home_val)
                a_total, a_completed = _parse_attempts(away_val)
                team_stats[home_team]['passes_total'] = h_total or 0
                team_stats[home_team]['passes_completed'] = h_completed or 0
                team_stats[away_team]['passes_total'] = a_total or 0
                team_stats[away_team]['passes_completed'] = a_completed or 0
            
            elif stat_name == 'Pass Completion':
                team_stats[home_team]['pass_accuracy'] = _parse_pct(home_val)
                team_stats[away_team]['pass_accuracy'] = _parse_pct(away_val)
            
            elif stat_name == 'Crosses':
                try:
                    team_stats[home_team]['crosses_total'] = int(home_val)
                except (ValueError, TypeError):
                    team_stats[home_team]['crosses_total'] = 0
                try:
                    team_stats[away_team]['crosses_total'] = int(away_val)
                except (ValueError, TypeError):
                    team_stats[away_team]['crosses_total'] = 0
            
            elif stat_name == 'Ball Progressions':
                try:
                    team_stats[home_team]['ball_progressions'] = int(home_val)
                except (ValueError, TypeError):
                    team_stats[home_team]['ball_progressions'] = 0
                try:
                    team_stats[away_team]['ball_progressions'] = int(away_val)
                except (ValueError, TypeError):
                    team_stats[away_team]['ball_progressions'] = 0
            
            elif stat_name == 'Forced Turnovers':
                try:
                    team_stats[home_team]['forced_turnovers'] = int(home_val)
                except (ValueError, TypeError):
                    team_stats[home_team]['forced_turnovers'] = 0
                try:
                    team_stats[away_team]['forced_turnovers'] = int(away_val)
                except (ValueError, TypeError):
                    team_stats[away_team]['forced_turnovers'] = 0
    
    # 兜底：用比分验证进球数
    team_stats[home_team]['goals'] = home_score
    team_stats[away_team]['goals'] = away_score
    
    # ---- 步骤4：构建射门事件DataFrame ----
    attempts_df = data['attempts']
    shot_events = []
    
    if not attempts_df.empty:
        for idx, row in attempts_df.iterrows():
            fifa_outcome = row.get('outcome', '')
            shot_outcome = _map_shot_outcome(fifa_outcome)
            
            shot_events.append({
                # 事件基础字段
                'type': 'Shot',
                'team': row.get('team', ''),
                'player': row.get('player_name', ''),
                'minute': int(row['time_min']) if pd.notna(row.get('time_min')) else None,
                'period': 1 if (pd.notna(row.get('time_min')) and int(row['time_min']) <= 45) else 2,
                # 位置坐标（FIFA数据无坐标，留空）
                'x': np.nan,
                'y': np.nan,
                # 射门相关字段
                'shot_outcome': shot_outcome,
                'shot_body_part': _map_body_part(row.get('body_part')),
                'shot_technique': row.get('delivery_type', ''),  # 传球来源/技术类型
                'shot_statsbomb_xg': np.nan,  # 稍后按球队分配
                # 传球相关字段（非射门事件，留空）
                'pass_outcome': np.nan,
                'pass_recipient': np.nan,
                'pass_end_x': np.nan,
                'pass_end_y': np.nan,
                # 控球队伍
                'possession_team': row.get('team', ''),
            })
    
    df = pd.DataFrame(shot_events)
    
    # 估算每脚射门的xG（按球队分配总xG）
    if not df.empty:
        for team in teams:
            team_shots = df[df['team'] == team].index
            total_xg = team_stats[team].get('xg', 0)
            if len(team_shots) > 0 and total_xg > 0:
                xg_vals = _estimate_xg_per_shot(df.loc[team_shots], total_xg)
                df.loc[team_shots, 'shot_statsbomb_xg'] = xg_vals
    
    # 按时间排序
    if not df.empty and 'minute' in df.columns:
        df = df.sort_values('minute').reset_index(drop=True)
    
    # ---- 步骤5：从球员级数据推导排行 ----
    pos_dist_df = data['possession_dist']
    defense_df = data['defense']
    
    # 传球排行榜（按成功传球数）
    pass_leaders = {team: pd.Series(dtype=int) for team in teams}
    if not pos_dist_df.empty:
        for team in teams:
            team_data = pos_dist_df[pos_dist_df['team'] == team]
            if not team_data.empty:
                leaders = team_data.set_index('player_name')['passes_completed'].sort_values(ascending=False).head(5)
                pass_leaders[team] = leaders
    
    # 射门排行榜
    shot_leaders = {team: pd.Series(dtype=int) for team in teams}
    if not attempts_df.empty:
        for team in teams:
            team_data = attempts_df[attempts_df['team'] == team]
            if not team_data.empty:
                leaders = team_data.groupby('player_name').size().sort_values(ascending=False).head(3)
                shot_leaders[team] = leaders
    
    # xG排行榜（按射门次数比例估算，由于FIFA无单射xG）
    xg_leaders = {team: pd.Series(dtype=float) for team in teams}
    if not df.empty:
        for team in teams:
            team_shots = df[df['team'] == team]
            if not team_shots.empty:
                leaders = team_shots.groupby('player')['shot_statsbomb_xg'].sum().sort_values(ascending=False).head(3)
                xg_leaders[team] = leaders
    
    # ---- 步骤6：增强版阵型推导 ----
    lineups_df = data['lineups']
    formations = {}
    for team in teams:
        formations[team] = _derive_formation_enhanced(
            lineups_df, pos_dist_df, defense_df, attempts_df, team
        )
    
    # ---- 步骤7：角球数统计（来自射门中Corner类型）----
    corners_count = {team: 0 for team in teams}
    if not attempts_df.empty:
        for team in teams:
            team_corners = attempts_df[
                (attempts_df['team'] == team) & 
                (attempts_df['delivery_type'] == 'Corner')
            ]
            corners_count[team] = len(team_corners)
    
    # ---- 步骤8：从防守数据提取犯规 ----
    fouls_count = {team: 0 for team in teams}
    fouls_won_count = {team: 0 for team in teams}
    if not defense_df.empty:
        for team in teams:
            fouls_count[team] = _extract_fouls_from_defense(defense_df, team)
        # 对方的犯规约等于本方被犯规（fouls_won）
        fouls_won_count[teams[0]] = fouls_count[teams[1]]
        fouls_won_count[teams[1]] = fouls_count[teams[0]]
    
    # ---- 步骤9：从控球分布提取关键传球 ----
    key_passes_count = {team: 0 for team in teams}
    if not pos_dist_df.empty:
        for team in teams:
            key_passes_count[team] = _extract_key_passes(pos_dist_df, team)
    
    # ---- 步骤10：构建球员级防守数据（用于热力图）----
    player_defense = {}
    for team in teams:
        player_defense[team] = _build_player_defense_stats(
            defense_df, pos_dist_df, team
        )
    
    # ---- 步骤11：构建stats字典（与stats_engine格式一致）----
    stats = {}
    for team in teams:
        ts = team_stats[team]
        
        # 射偏/封堵数 = 总射门 - 射正
        shots_off_target = ts.get('shots_total', 0) - ts.get('shots_on_target', 0)
        
        # 控球事件数（按控球率比例估算总事件数，用传球总数作为代理）
        possession_events = ts.get('passes_total', 0) + ts.get('shots_total', 0)
        
        # 总事件数（粗略估算）
        total_events = possession_events + ts.get('forced_turnovers', 0)
        
        stats[team] = {
            # 基础事件
            'total_events': total_events,
            'possession_events': possession_events,
            
            # 传球
            'passes_total': ts.get('passes_total', 0),
            'passes_completed': ts.get('passes_completed', 0),
            'pass_accuracy': ts.get('pass_accuracy', 0),
            
            # 射门
            'shots_total': ts.get('shots_total', 0),
            'shots_on_target': ts.get('shots_on_target', 0),
            'shots_off_target': shots_off_target,
            'goals': ts.get('goals', 0),
            'xg': ts.get('xg', 0),
            
            # 犯规/角球/越位（从防守数据估算犯规）
            'fouls': fouls_count[team],
            'fouls_won': fouls_won_count[team],
            'corners': corners_count[team],
            'offsides': 0,
            
            # 关键传球/助攻（从line_breaks提取关键传球）
            'key_passes': key_passes_count[team],
            'assists': 0,
            
            # 球员排行
            'pass_leaders': pass_leaders[team],
            'shot_leaders': shot_leaders[team],
            'xg_leaders': xg_leaders[team],
            
            # 阵型
            'formation': formations[team],
            
            # 逼抢位置（无坐标数据，置None）
            'pressure_avg_x': None,
            'high_turnovers': 0,
            
            # 推进相关指标（FIFA有部分数据，其余置0/None）
            'progressive_passes': 0,
            'passes_into_final_third': 0,
            'passes_into_box': 0,
            'deep_progressions': ts.get('ball_progressions', 0),
            'switches_of_play': 0,  # 可从球员数据汇总
            'progressive_carries': 0,
            'ppda': None,
            'progressive_sequences': 0,
            'defensive_weak_zones': [],
        }
    
    # 计算switches_of_play（从球员级数据汇总）
    if not pos_dist_df.empty:
        for team in teams:
            team_data = pos_dist_df[pos_dist_df['team'] == team]
            if not team_data.empty and 'switches_of_play' in team_data.columns:
                stats[team]['switches_of_play'] = int(team_data['switches_of_play'].sum())
    
    # 控球率（直接使用FIFA数据）
    for team in teams:
        stats[team]['possession_pct'] = team_stats[team].get('possession_pct', 50)
    
    # ---- 步骤11.5：提取P0新图表专用数据 ----
    # 每个图表对应其核心数据源，数据源缺失时跳过（返回空字典）
    tactical_radar_data = _extract_tactical_radar_data(data['phases'], teams) if not data['phases'].empty else {}
    line_breaks_data = _extract_line_breaks_data(pos_dist_df, teams) if not pos_dist_df.empty else {}
    cross_tactics_data = _extract_cross_tactics_data(data['crosses'], pos_dist_df, teams) if not data['crosses'].empty else {}
    physical_zones_data = _extract_physical_zones_data(data['physical'], teams) if not data['physical'].empty else {}
    
    # ---- 步骤12：构建info字典 ----
    info = {
        'name': match_name,
        'teams': teams,
        'source': 'fifa',
        'csv_dir': csv_dir,
        'home_team': home_team,
        'away_team': away_team,
        'home_score': home_score,
        'away_score': away_score,
        'match_date': info_dict.get('match_date', ''),
        'stadium': info_dict.get('stadium', ''),
        'match_round': info_dict.get('match_round', ''),
        'kickoff_time': info_dict.get('kickoff_time', ''),
        # FIFA数据特有的附加信息
        'fifa_extra': {
            'phases_of_play': data['phases'].to_dict('records') if not data['phases'].empty else [],
            'defensive_stats': not data['defense'].empty,  # 有防守数据
            'physical_stats': not data['physical'].empty,  # 有体能数据
            'passing_network': not data['passing_network'].empty,  # 有传球网络
            'passing_network_data': data['passing_network'] if not data['passing_network'].empty else pd.DataFrame(),  # 传球网络原始数据
            'player_positions': lineups_df if not lineups_df.empty else pd.DataFrame(),  # 球员位置数据（用于传球网络布局）
            'player_defense_stats': player_defense,  # 球员级防守数据（用于热力图）
            'key_passes_source': 'line_breaks_completed',  # 关键传球数据来源说明
            'fouls_estimated': True,  # 犯规为估算值
            'missing_files': missing_optional,  # 缺失的非核心文件列表
            # P0新图表数据
            'tactical_radar': tactical_radar_data,    # 战术风格雷达图数据
            'line_breaks': line_breaks_data,          # 防线穿透分析数据
            'cross_tactics': cross_tactics_data,      # 传中战术分析数据
            'physical_zones': physical_zones_data,    # 体能五分区数据
        },
        # 受限功能列表（FIFA数据无法支持的功能）
        'limited_features': [
            'shot_coordinates',       # 射门无坐标，射门位置图无法精确定位
            'pass_coordinates',       # 传球无坐标，传球网络仅能显示节点大小
            'possession_timeline',    # 无逐事件控球数据，时间线图精度有限
            'pressure_heatmap',       # 无防守事件坐标，热力图使用近似位置
            'fouls_data',             # 犯规为估算值，非精确统计
            'offsides_data',          # 无越位数据
            'assists_data',           # 无助攻数据
            'key_passes_data',        # 关键传球为近似值（源自line_breaks）
            'ppda_calculation',       # 无法计算PPDA（缺少防守事件数）
            'progressive_pass_detail',  # 推进传球细节不足
            'defensive_weak_zones',   # 无法计算防守薄弱区域
        ],
    }
    
    print(f"[FIFA适配器] 加载完成：{match_name}")
    print(f"  比赛：{home_team} {home_score} - {away_score} {away_team}")
    print(f"  事件数：{len(df)}（全部为射门事件）")
    print(f"  球队：{teams}")
    print(f"  阵型：{formations[home_team]} vs {formations[away_team]}")
    print(f"  犯规：{fouls_count[home_team]} - {fouls_count[away_team]}（估算值）")
    print(f"  关键传球：{key_passes_count[home_team]} - {key_passes_count[away_team]}")
    print(f"  受限功能：{len(info['limited_features'])}项")
    
    return df, info, stats


# ========== 战术洞察生成 ==========

def generate_tactical_insights(stats, info=None):
    """从FIFA数据生成丰富的战术洞察，分进攻端和防守端
    
    覆盖维度：控球风格、进攻威胁、防守强度、防线漏洞、关键球员、
              体能对比、传中策略、防线穿透、定位球威胁、比赛节奏
    
    参数:
        stats: 球队统计字典 {team_name: {stat_name: value}}
        info: 比赛信息字典（可选，含fifa_extra高级数据）
    
    返回:
        dict: {'attack': [...], 'defense': [...]}
              每条洞察格式: {'category': str, 'text': str, 'priority': 1-3, 'suggestion': str}
    """
    teams = list(stats.keys())
    if len(teams) < 2:
        return {
            'attack': [{'category': '通用', 'text': '数据不足，无法生成对比洞察', 'priority': 3, 'suggestion': ''}],
            'defense': []
        }
    
    t1, t2 = teams[0], teams[1]
    s1, s2 = stats[t1], stats[t2]
    
    # 获取FIFA扩展数据（如果有）
    fifa_extra = info.get('fifa_extra', {}) if info else {}
    radar_data = fifa_extra.get('tactical_radar', {})
    lb_data = fifa_extra.get('line_breaks', {})
    cross_data = fifa_extra.get('cross_tactics', {})
    phys_data = fifa_extra.get('physical_zones', {})
    
    attack_insights = []
    defense_insights = []
    
    # ===== 1. 控球风格判断 =====
    p1 = s1.get('possession_pct', 50)
    p2 = s2.get('possession_pct', 50)
    pass_acc1 = s1.get('pass_accuracy', 0)
    pass_acc2 = s2.get('pass_accuracy', 0)
    
    if abs(p1 - p2) > 10:
        dominant = t1 if p1 > p2 else t2
        reactive = t2 if p1 > p2 else t1
        dom_pct = max(p1, p2)
        react_pct = min(p1, p2)
        dom_acc = pass_acc1 if p1 > p2 else pass_acc2
        
        if dom_acc > 85:
            style = "传控主导型"
        elif dom_acc > 75:
            style = "控球推进型"
        else:
            style = "控球但效率一般型"
            
        attack_insights.append({
            'category': '控球风格',
            'text': f"{dominant}以{dom_pct:.0f}%控球率占据场上主动，传球成功率{dom_acc:.0f}%，呈现{style}的进攻打法；{reactive}控球率仅{react_pct:.0f}%，更偏向防守反击战术。",
            'priority': 1 if abs(p1 - p2) > 20 else 2,
            'suggestion': f"{reactive}应注重反击时的出球速度与精准度，利用对手压上后的身后空间"
        })
    else:
        attack_insights.append({
            'category': '控球风格',
            'text': f"双方控球率接近（{p1:.0f}% vs {p2:.0f}%），比赛呈现均势对抗，中场争夺激烈。",
            'priority': 3,
            'suggestion': '控球相当的情况下，定位球和反击质量可能成为胜负关键'
        })
    
    # ===== 2. 进攻威胁来源 =====
    for team in teams:
        s = stats[team]
        xg = s.get('xg', 0)
        shots = s.get('shots_total', 0)
        sot = s.get('shots_on_target', 0)
        key_passes = s.get('key_passes', 0)
        
        if shots == 0:
            continue
        
        sot_rate = sot / shots * 100
        xg_per_shot = xg / max(shots, 1)
        
        # 判断进攻威胁类型
        if xg_per_shot > 0.15 and sot_rate > 40:
            threat_type = "高质量机会型"
            desc = f"场均每脚射门xG达{xg_per_shot:.2f}，射正率{sot_rate:.0f}%，进攻效率高，创造的机会质量好"
        elif shots > 15 and sot_rate < 30:
            threat_type = "数量压迫型"
            desc = f"全场{shots}脚射门但射正率仅{sot_rate:.0f}%，靠进攻次数压制，但射门选择有待优化"
        elif key_passes > 10:
            threat_type = "传切配合型"
            desc = f"关键传球{key_passes}次，善于通过配合创造机会，中场创造力较强"
        else:
            threat_type = "均衡型"
            desc = f"{shots}次射门、{key_passes}次关键传球，进攻手段相对均衡"
        
        attack_insights.append({
            'category': '进攻威胁',
            'text': f"{team}的进攻呈{threat_type}特征：{desc}，总xG为{xg:.2f}。",
            'priority': 2,
            'suggestion': ''
        })
    
    # ===== 3. 防线穿透能力 =====
    if lb_data and t1 in lb_data and t2 in lb_data:
        lb1 = lb_data[t1]
        lb2 = lb_data[t2]
        
        better = t1 if lb1['success_rate'] > lb2['success_rate'] else t2
        worse = t2 if lb1['success_rate'] > lb2['success_rate'] else t1
        better_lb = lb1 if lb1['success_rate'] > lb2['success_rate'] else lb2
        worse_lb = lb2 if lb1['success_rate'] > lb2['success_rate'] else lb1
        
        attack_insights.append({
            'category': '防线穿透',
            'text': f"{better}防线穿透力更强：{better_lb['attempts']}次尝试突破防线，成功{better_lb['completed']}次，成功率{better_lb['success_rate']:.1f}%，转化{better_lb['goals']}粒进球；{worse}仅{worse_lb['completed']}次成功穿透（成功率{worse_lb['success_rate']:.1f}%）。",
            'priority': 2 if abs(lb1['success_rate'] - lb2['success_rate']) > 10 else 3,
            'suggestion': f"{worse}中场需加强拦截，切断对手穿透传球的路线"
        })
        
        # 突破关键球员
        better_top = better_lb.get('top_players', [])
        if better_top:
            player_names = '、'.join([p['name'].split()[-1] if ' ' in str(p['name']) else str(p['name']) 
                                     for p in better_top[:2]])
            attack_insights.append({
                'category': '关键球员',
                'text': f"{better}的{player_names}是防线突破的核心人物，多次成功穿透对方防线。",
                'priority': 2,
                'suggestion': f"对手应对这些球员进行重点盯防和战术限制"
            })
    
    # ===== 4. 传中策略 =====
    if cross_data and t1 in cross_data and t2 in cross_data:
        c1 = cross_data[t1]
        c2 = cross_data[t2]
        
        # 分析传中偏好
        for team, cd in [(t1, c1), (t2, c2)]:
            type_dist = cd.get('type_distribution', {})
            total = cd.get('total_attempted', 0)
            if total == 0:
                continue
            
            # 找出最主要的传中类型
            main_type = max(type_dist.items(), key=lambda x: x[1]) if type_dist else ('unknown', 0)
            type_names_cn = cd.get('type_names_cn', {})
            main_type_cn = type_names_cn.get(main_type[0], main_type[0])
            main_pct = main_type[1] / total * 100 if total > 0 else 0
            
            attack_insights.append({
                'category': '传中策略',
                'text': f"{team}全场{total}次传中，成功{cd['total_completed']}次（成功率{cd['success_rate']:.1f}%），以{main_type_cn}传中为主（占比{main_pct:.0f}%）。",
                'priority': 3,
                'suggestion': ''
            })
        
        # 对比
        if c1['success_rate'] != c2['success_rate']:
            better_team = t1 if c1['success_rate'] > c2['success_rate'] else t2
            better_rate = max(c1['success_rate'], c2['success_rate'])
            worse_team = t2 if c1['success_rate'] > c2['success_rate'] else t1
            worse_rate = min(c1['success_rate'], c2['success_rate'])
            
            if abs(better_rate - worse_rate) > 10:
                attack_insights.append({
                    'category': '传中效率',
                    'text': f"{better_team}传中效率明显更高（成功率{better_rate:.1f}% vs {worse_rate:.1f}%），边路进攻质量优于{worse_team}。",
                    'priority': 2,
                    'suggestion': f"{worse_team}应提升传中质量或增加中路配合比重"
                })
    
    # ===== 5. 定位球威胁 =====
    for team in teams:
        s = stats[team]
        corners = s.get('corners', 0)
        fouls_won = s.get('fouls_won', 0)
        xg = s.get('xg', 0)
        goals = s.get('goals', 0)
        
        if corners > 5:
            attack_insights.append({
                'category': '定位球',
                'text': f"{team}获得{corners}个角球，定位球进攻资源丰富，是重要的得分手段。",
                'priority': 2 if corners > 8 else 3,
                'suggestion': '角球数多说明对手防线承受持续压力，可进一步丰富角球战术'
            })
    
    # ===== 6. 比赛节奏 =====
    prog1 = s1.get('deep_progressions', 0)
    prog2 = s2.get('deep_progressions', 0)
    total_events1 = s1.get('total_events', 0)
    total_events2 = s2.get('total_events', 0)
    
    # 用推进次数估算节奏
    avg_prog = (prog1 + prog2) / 2
    if avg_prog > 80:
        tempo_desc = "快节奏对攻战"
    elif avg_prog > 50:
        tempo_desc = "中等节奏"
    else:
        tempo_desc = "慢节奏控球战"
    
    attack_insights.append({
        'category': '比赛节奏',
        'text': f"全场比赛呈{tempo_desc}特征：{t1}推进{prog1}次，{t2}推进{prog2}次，双方合计{prog1+prog2}次向前推进。",
        'priority': 2,
        'suggestion': ''
    })
    
    # ===== 7. 进攻效率（xG vs 实际进球） =====
    for team in teams:
        s = stats[team]
        xg = s.get('xg', 0)
        goals = s.get('goals', 0)
        diff = goals - xg
        
        if abs(diff) >= 0.5:
            if diff > 0:
                attack_insights.append({
                    'category': '进攻效率',
                    'text': f"{team}把握机会能力出色：预期进球{xg:.2f}，实际打进{goals}球，超额完成{diff:.2f}球，射手效率高于预期。",
                    'priority': 1 if diff > 1 else 2,
                    'suggestion': '高效终结是宝贵优势，但需注意机会创造的可持续性'
                })
            else:
                attack_insights.append({
                    'category': '进攻效率',
                    'text': f"{team}进攻效率偏低：预期进球{xg:.2f}但仅打进{goals}球，浪费了{abs(diff):.2f}球的机会，临门一脚有待提升。",
                    'priority': 1 if abs(diff) > 1 else 2,
                    'suggestion': '建议分析射门选择和得分手状态，提升终结质量'
                })
    
    # ===== 8. 防守强度 =====
    for team in teams:
        s = stats[team]
        fouls = s.get('fouls', 0)
        forced = s.get('forced_turnovers', 0)
        
        # 从雷达数据获取防守风格
        radar_team = radar_data.get(team, {})
        def_dims = radar_team.get('defense', {})
        
        high_press = def_dims.get('高位压迫', 0) + def_dims.get('高位防线', 0)
        low_block = def_dims.get('低位防线', 0)
        
        if def_dims:
            if high_press > low_block:
                def_style = "高位逼抢型"
                desc = f"高位压迫+高位防线占比约{high_press:.0f}%，防线前提，主动出击夺回球权"
            else:
                def_style = "低位防守型"
                desc = f"低位防线占比约{low_block:.0f}%，收缩防守，注重禁区保护"
            
            defense_insights.append({
                'category': '防守风格',
                'text': f"{team}呈{def_style}防守特征：{desc}，全场犯规{fouls}次。",
                'priority': 2,
                'suggestion': ''
            })
        else:
            if fouls > 15:
                def_style = "高强度对抗型"
            elif fouls > 10:
                def_style = "中等强度型"
            else:
                def_style = "技术防守型"
            
            defense_insights.append({
                'category': '防守强度',
                'text': f"{team}防守呈{def_style}特征：全场犯规{fouls}次，防守对抗强度{'较高' if fouls > 12 else '适中'}。",
                'priority': 3,
                'suggestion': ''
            })
    
    # ===== 9. 防线漏洞 =====
    for team in teams:
        s = stats[team]
        xg_conceded = stats[t2 if team == t1 else t1].get('xg', 0)  # 对手的xG即本方被射门质量
        shots_against = stats[t2 if team == t1 else t1].get('shots_total', 0)
        sot_against = stats[t2 if team == t1 else t1].get('shots_on_target', 0)
        
        opponent = t2 if team == t1 else t1
        
        # 从防线穿透数据看漏洞
        opp_lb = lb_data.get(opponent, {})
        if opp_lb and opp_lb.get('completed', 0) > 5:
            defense_insights.append({
                'category': '防线漏洞',
                'text': f"{team}防线中路存在被穿透风险：对手成功突破防线{opp_lb['completed']}次，其中{opp_lb.get('goals', 0)}次转化为进球，穿透成功率{opp_lb.get('success_rate', 0):.1f}%。",
                'priority': 2 if opp_lb.get('success_rate', 0) > 30 else 3,
                'suggestion': '建议加强中场中路拦截，或调整后腰位置保护防线身前空间'
            })
        
        # 从传中数据看边路漏洞
        opp_cross = cross_data.get(opponent, {})
        if opp_cross and opp_cross.get('success_rate', 0) > 25:
            defense_insights.append({
                'category': '防线漏洞',
                'text': f"{team}边路防守存在隐患：对手传中成功率达{opp_cross['success_rate']:.1f}%（{opp_cross['total_completed']}/{opp_cross['total_attempted']}），边路防守压力较大。",
                'priority': 2 if opp_cross['success_rate'] > 35 else 3,
                'suggestion': '边后卫与边前卫需加强协同防守，减少对手高质量传中'
            })
    
    # ===== 10. 体能对比 =====
    if phys_data and t1 in phys_data and t2 in phys_data:
        ph1 = phys_data[t1]
        ph2 = phys_data[t2]
        
        dist1 = ph1.get('total_distance', 0) / 1000
        dist2 = ph2.get('total_distance', 0) / 1000
        sprint1 = ph1.get('sprints_count', 0)
        sprint2 = ph2.get('sprints_count', 0)
        hsr1 = ph1.get('high_speed_runs', 0)
        hsr2 = ph2.get('high_speed_runs', 0)
        
        avg_dist = (dist1 + dist2) / 2
        
        if abs(dist1 - dist2) > 5:
            fitter = t1 if dist1 > dist2 else t2
            less_fit = t2 if dist1 > dist2 else t1
            more_dist = max(dist1, dist2)
            less_dist = min(dist1, dist2)
            
            defense_insights.append({
                'category': '体能对比',
                'text': f"两队体能差距明显：{fitter}全队跑动{more_dist:.1f}km，比{less_fit}的{less_dist:.1f}km多出{more_dist-less_dist:.1f}km，体能储备更充足。",
                'priority': 2,
                'suggestion': f"{less_fit}在比赛后半段需注意体能分配，避免因体能下降导致防守失误"
            })
        else:
            defense_insights.append({
                'category': '体能对比',
                'text': f"两队体能相当：{t1}跑动{dist1:.1f}km，{t2}跑动{dist2:.1f}km，均处于{avg_dist:.0f}km左右的正常水平。",
                'priority': 3,
                'suggestion': ''
            })
        
        # 冲刺次数对比（反映爆发力和防守覆盖）
        if abs(sprint1 - sprint2) > 20:
            more_sprint = t1 if sprint1 > sprint2 else t2
            more_s = max(sprint1, sprint2)
            less_s = min(sprint1, sprint2)
            
            attack_insights.append({
                'category': '体能对比',
                'text': f"{more_sprint}冲刺次数更多（{more_s}次 vs {less_s}次），速度优势明显，反击和边路突破更具威胁。",
                'priority': 2,
                'suggestion': ''
            })
        
        # 最高速度球员
        top1 = ph1.get('top_speed_players', [])
        top2 = ph2.get('top_speed_players', [])
        if top1 and top2:
            fastest1 = top1[0]
            fastest2 = top2[0]
            n1 = fastest1['name'].split()[-1] if ' ' in str(fastest1['name']) else str(fastest1['name'])
            n2 = fastest2['name'].split()[-1] if ' ' in str(fastest2['name']) else str(fastest2['name'])
            
            defense_insights.append({
                'category': '关键球员',
                'text': f"速度尖兵：{t1}的{n1}最高速度{fastest1['top_speed']:.1f}km/h，{t2}的{n2}最高速度{fastest2['top_speed']:.1f}km/h，是各自球队反击中的重要武器。",
                'priority': 3,
                'suggestion': ''
            })
    
    # ===== 11. 射门关键球员 =====
    for team in teams:
        s = stats[team]
        shot_leaders = s.get('shot_leaders', pd.Series(dtype=int))
        xg_leaders = s.get('xg_leaders', pd.Series(dtype=float))
        
        if not shot_leaders.empty:
            top_scorer = shot_leaders.index[0]
            top_shots = shot_leaders.iloc[0]
            short_name = top_scorer.split()[-1] if ' ' in str(top_scorer) else str(top_scorer)
            
            attack_insights.append({
                'category': '关键球员',
                'text': f"{team}进攻核心：{short_name}完成{top_shots}次射门，是球队最主要的进攻终结点。",
                'priority': 2,
                'suggestion': '对手应对其进行重点防守和针对性布防'
            })
    
    # ===== 12. 传球组织核心 =====
    for team in teams:
        s = stats[team]
        pass_leaders = s.get('pass_leaders', pd.Series(dtype=int))
        
        if not pass_leaders.empty:
            top_passer = pass_leaders.index[0]
            top_passes = pass_leaders.iloc[0]
            short_name = top_passer.split()[-1] if ' ' in str(top_passer) else str(top_passer)
            
            defense_insights.append({
                'category': '关键球员',
                'text': f"{team}组织核心：{short_name}完成{top_passes}次成功传球，是球队中场节拍器和进攻发起点。",
                'priority': 2,
                'suggestion': f"限制{short_name}的传球空间可有效干扰{team}的进攻组织"
            })
    
    # 按优先级排序
    attack_insights.sort(key=lambda x: x['priority'])
    defense_insights.sort(key=lambda x: x['priority'])
    
    # 控制数量：各保留5-7条
    if len(attack_insights) > 7:
        attack_insights = attack_insights[:7]
    if len(defense_insights) > 7:
        defense_insights = defense_insights[:7]
    
    return {
        'attack': attack_insights,
        'defense': defense_insights
    }


# ========== 便捷函数 ==========

# FIFA比赛报告特征文件名关键词（用于智能识别FIFA多文件格式）
FIFA_FILE_KEYWORDS = [
    'match_info',
    'lineups',
    'key_stats',
    'phases_of_play',
    'attempts_at_goal',
    'crosses',
    'offers_to_receive',
    'in_possession_distributions',
    'in_possession_offers',
    'out_of_possession',
    'physical_data',
    'passing_network',
]

# 核心标识文件关键词（至少命中几个才认为是FIFA格式）
_FIFA_CORE_KEYWORDS = {'match_info', 'attempts_at_goal', 'key_stats'}
_FIFA_MIN_MATCH = 3  # 至少匹配3个核心关键词


def detect_fifa_from_filenames(filenames):
    """根据文件名列表判断是否为FIFA比赛报告格式（关键词匹配，更鲁棒）
    
    参数：
        filenames: list[str] — 文件名列表（不含路径）
    
    返回：
        bool — True表示识别为FIFA多文件格式
    
    识别逻辑：
        检查文件名中是否包含FIFA特征关键词，至少命中3个核心关键词即判定为FIFA格式。
        不依赖文件编号前缀（如01_、02_），不依赖大小写，支持各种命名变体。
    """
    if not filenames or len(filenames) < 2:
        return False
    
    # 统一转为小写，去掉扩展名，方便匹配
    names_lower = [os.path.splitext(f.lower())[0] for f in filenames]
    
    # 统计命中的核心关键词数量
    core_hits = 0
    for kw in _FIFA_CORE_KEYWORDS:
        if any(kw in name for name in names_lower):
            core_hits += 1
    
    if core_hits >= _FIFA_MIN_MATCH:
        return True
    
    # 退而求其次：统计所有关键词命中数
    all_hits = 0
    for kw in FIFA_FILE_KEYWORDS:
        if any(kw in name for name in names_lower):
            all_hits += 1
    
    # 命中5个以上普通关键词也认为是FIFA格式
    return all_hits >= 5


def is_fifa_csv_dir(csv_dir):
    """判断一个目录是否为FIFA比赛报告CSV输出目录
    
    使用关键词匹配，比精确文件名匹配更鲁棒，支持：
    - 带编号前缀（01_match_info.csv）
    - 不带前缀（match_info.csv）
    - 大小写不敏感
    - 不同导出工具的命名变体
    
    检测依据：目录中CSV文件的文件名是否包含足够多的FIFA特征关键词。
    """
    if not os.path.isdir(csv_dir):
        return False
    
    try:
        csv_files = [f for f in os.listdir(csv_dir) if f.lower().endswith('.csv')]
    except OSError:
        return False
    
    return detect_fifa_from_filenames(csv_files)


def fifa_chart_support(info):
    """返回各图表对FIFA数据的支持情况
    
    返回：{图表ID: (支持等级, 说明)}
    支持等级：full（完整支持）、partial（部分支持）、none（不支持）
    """
    support = {
        'shot_comparison': ('full', '射门对比数据完整'),
        'stats_bar': ('full', '核心数据对比完整（控球、传球、射门、角球、犯规、关键传球）'),
        'xg_flow': ('partial', 'xG累积曲线可用，xG为按结果类型估算值'),
        'shot_map': ('partial', '射门位置图无坐标，只能显示射门数量统计'),
        'pass_network': ('partial', '传球网络仅有传球次数，无位置坐标'),
        'possession_timeline': ('partial', '仅射门事件有时间，控球时间线不完整'),
        'pressure_heatmap': ('partial', '防守热力图使用球员位置近似值，非精确坐标'),
        # FIFA专属P0图表
        'tactical_radar': ('full', '战术风格雷达图数据完整（14个攻防维度）'),
        'line_breaks': ('full', '防线穿透分析数据完整（尝试、成功、进球、球员排行）'),
        'cross_tactics': ('full', '传中战术分析数据完整（6种类型分布+成功率）'),
        'physical_zones': ('full', '体能五分区图数据完整（5分区+冲刺+最高速度）'),
    }
    return support


# ========== 位置基准对标适配器 ==========

def _classify_detailed_position(player_name: str, fifa_pos: str,
                                 stats: Dict) -> str:
    """
    将FIFA粗分类位置(GK/DF/MF/FW)细化为基准位置(GK/CB/FB/CDM/CM/W/ST)。

    基于球员数据特征判断具体位置：
    - DF: 高解围+低进攻 → CB, 高推进+低解围 → FB
    - MF: 高防守+高触球 → CDM, 高进攻 → CM, 高过人+低防守 → W
    - FW: 高进球 → ST, 高过人+助攻 → W
    """
    if fifa_pos == 'GK':
        return 'GK'

    tackles = stats.get('tackles', 0)
    clearances = stats.get('clearances', 0)
    interceptions = stats.get('interceptions', 0)
    passes = stats.get('passes_attempted', 0)
    goals = stats.get('goals', 0)
    assists = stats.get('assists', 0)
    ball_prog = stats.get('ball_progressions', 0)
    take_ons = stats.get('take_ons', 0)
    line_breaks = stats.get('line_breaks_completed', 0)

    # 攻防评分
    attack_score = goals * 10 + assists * 8 + take_ons * 2 + ball_prog * 1.5
    defense_score = tackles * 3 + clearances * 2 + interceptions * 3

    if fifa_pos == 'DF':
        # 边后卫 vs 中卫
        if attack_score > defense_score * 0.6 and ball_prog > 3:
            return 'FB'
        else:
            return 'CB'

    elif fifa_pos == 'MF':
        # 后腰 vs 中场 vs 边锋
        if defense_score > attack_score * 1.5 and passes > 50:
            return 'CDM'
        elif take_ons > 5 and (attack_score > defense_score * 2):
            return 'W'
        else:
            return 'CM'

    elif fifa_pos == 'FW':
        # 前锋 vs 边锋
        if take_ons > 3 and assists > goals * 0.5:
            return 'W'
        else:
            return 'ST'

    return 'CM'  # 默认


class FIFAMatchBenchmarkAdapter:
    """
    FIFA比赛数据 → 位置基准对标适配器。

    用法：
        adapter = FIFAMatchBenchmarkAdapter(csv_dir)
        result = adapter.analyze_team("Canada")
        # 或
        result = adapter.analyze_match()  # 分析双方
    """

    def __init__(self, csv_dir: str):
        self.csv_dir = csv_dir
        self._load_data()

    def _load_data(self):
        """加载所有12类CSV文件"""
        d = self.csv_dir
        self.match_info = _read_csv_safe(os.path.join(d, '01_match_info.csv'))
        self.lineups = _read_csv_safe(os.path.join(d, '02_lineups.csv'))
        self.key_stats = _read_csv_safe(os.path.join(d, '03_key_stats.csv'))
        self.phases = _read_csv_safe(os.path.join(d, '04_phases_of_play.csv'))
        self.attempts = _read_csv_safe(os.path.join(d, '05_attempts_at_goal.csv'))
        self.crosses = _read_csv_safe(os.path.join(d, '06_crosses.csv'))
        self.offers = _read_csv_safe(os.path.join(d, '07_offers_to_receive.csv'))
        self.in_poss = _read_csv_safe(os.path.join(d, '08_in_possession_distributions.csv'))
        self.in_poss_offers = _read_csv_safe(os.path.join(d, '09_in_possession_offers.csv'))
        self.out_poss = _read_csv_safe(os.path.join(d, '10_out_of_possession.csv'))
        self.physical = _read_csv_safe(os.path.join(d, '11_physical_data.csv'))
        self.passing_net = _read_csv_safe(os.path.join(d, '12_passing_network.csv'))

    def _get_teams(self) -> List[str]:
        """获取两队名称"""
        if not self.lineups.empty:
            return self.lineups['team'].unique().tolist()[:2]
        if not self.in_poss.empty:
            return self.in_poss['team'].unique().tolist()[:2]
        return []

    def _get_player_positions(self, team: str) -> Dict[str, str]:
        """从lineups获取球员FIFA位置"""
        if self.lineups.empty:
            return {}
        starters = self.lineups[
            (self.lineups['team'] == team) &
            (self.lineups['role'] == 'starting')
        ]
        return {
            row['player_name']: row.get('position', 'MF')
            for _, row in starters.iterrows()
            if row.get('player_name')
        }

    def _extract_player_stats(self, team: str) -> Dict[str, Dict]:
        """
        从FIFA CSV提取每个球员的关键数据。
        返回: {player_name: {stat_key: value, ...}}
        """
        players = {}

        # 从控球分布数据获取传球/进攻指标
        if not self.in_poss.empty:
            team_data = self.in_poss[self.in_poss['team'] == team]
            for _, row in team_data.iterrows():
                name = row.get('player_name', '')
                if not name:
                    continue
                if name not in players:
                    players[name] = {}

                p = players[name]
                p['passes_attempted'] = int(row.get('passes_attempted', 0) or 0)
                p['passes_completed'] = int(row.get('passes_completed', 0) or 0)
                p['pass_accuracy'] = _parse_pct(row.get('pass_completion_pct')) or 0
                p['take_ons'] = int(row.get('take_ons', 0) or 0)
                p['crosses_completed'] = int(row.get('crosses_completed', 0) or 0)
                p['line_breaks_completed'] = int(row.get('line_breaks_completed', 0) or 0)
                p['ball_progressions'] = int(row.get('ball_progressions', 0) or 0)
                p['attempts_at_goal'] = int(row.get('attempts_at_goal', 0) or 0)
                p['switches_of_play'] = int(row.get('switches_of_play', 0) or 0)

        # 从防守数据获取防守指标
        if not self.out_poss.empty:
            team_data = self.out_poss[self.out_poss['team'] == team]
            for _, row in team_data.iterrows():
                name = row.get('player_name', '')
                if not name:
                    continue
                if name not in players:
                    players[name] = {}

                p = players[name]
                tackles_str = row.get('tackles_made_won', '0/0')
                tackles_total, tackles_won = _parse_fraction(tackles_str)
                p['tackles'] = tackles_total or 0
                p['tackles_won'] = tackles_won or 0
                p['blocks'] = int(row.get('blocks', 0) or 0)
                p['interceptions'] = int(row.get('interceptions', 0) or 0)
                p['clearances'] = int(row.get('clearances', 0) or 0)
                p['possession_regains'] = int(row.get('possession_regains', 0) or 0)
                p['pressing_direct'] = int(row.get('pressing_direct', 0) or 0)

                # 触球 ≈ 传球尝试 + 防守动作
                touches = p.get('passes_attempted', 0) + p['tackles'] + p['clearances']
                p['touches'] = touches

        # 从射门数据获取进球/助攻
        if not self.attempts.empty:
            team_shots = self.attempts[self.attempts['team'] == team]
            for _, row in team_shots.iterrows():
                name = row.get('player_name', '')
                if not name:
                    continue
                if name not in players:
                    players[name] = {'goals': 0, 'shots': 0, 'shots_on_target': 0}
                p = players[name]
                p['shots'] = p.get('shots', 0) + 1
                outcome = str(row.get('outcome', '')).lower()
                if 'goal' in outcome:
                    p['goals'] = p.get('goals', 0) + 1
                elif 'saved' in outcome or ('on target' in outcome and 'goal' not in outcome):
                    p['shots_on_target'] = p.get('shots_on_target', 0) + 1

        # 计算衍生指标
        for name, p in players.items():
            # 射正率
            shots = p.get('shots', 0)
            sot = p.get('shots_on_target', 0)
            p['shots_on_target_pct'] = (sot / shots * 100) if shots > 0 else 0

            # 进球（从射门数据补充）
            if 'goals' not in p:
                p['goals'] = 0

            # 防守贡献总数
            p['defensive_actions'] = (
                p.get('tackles', 0) + p.get('interceptions', 0) +
                p.get('blocks', 0) + p.get('clearances', 0)
            )

        return players

    def _map_to_benchmark_metrics(
        self, player_stats: Dict[str, Dict], fifa_positions: Dict[str, str]
    ) -> Tuple[Dict[str, Dict], Dict[str, str]]:
        """
        将FIFA数据映射到基准引擎所需的指标格式。
        同时将FIFA粗分类位置细化为基准位置。

        返回:
            (benchmark_stats, benchmark_positions)
        """
        benchmark_stats = {}
        benchmark_positions = {}

        for name, raw in player_stats.items():
            fifa_pos = fifa_positions.get(name, 'MF')
            detailed_pos = _classify_detailed_position(name, fifa_pos, raw)
            benchmark_positions[name] = detailed_pos

            bm = {}

            if detailed_pos == 'GK':
                bm['saves'] = raw.get('clearances', 0)
                bm['save_pct'] = raw.get('pass_accuracy', 75)
                bm['clean_sheets'] = 0
                bm['goals_conceded'] = 0

            elif detailed_pos == 'CB':
                bm['touches'] = raw.get('touches', 0)
                bm['tackles'] = raw.get('tackles', 0)
                bm['clearances'] = raw.get('clearances', 0)
                bm['interceptions'] = raw.get('interceptions', 0)
                bm['pass_accuracy'] = raw.get('pass_accuracy', 0)

            elif detailed_pos == 'FB':
                bm['goals'] = raw.get('goals', 0)
                bm['assists'] = raw.get('assists', 0)
                bm['progressive_carries'] = raw.get('ball_progressions', 0)
                bm['defensive_actions'] = raw.get('defensive_actions', 0)
                bm['pass_accuracy'] = raw.get('pass_accuracy', 0)
                tackles_won = raw.get('tackles_won', 0)
                tackles_total = raw.get('tackles', 0)
                bm['duel_win_pct'] = (tackles_won / tackles_total * 100) if tackles_total > 0 else 50

            elif detailed_pos == 'CDM':
                bm['touches'] = raw.get('touches', 0)
                bm['passes_attempted'] = raw.get('passes_attempted', 0)
                bm['pass_accuracy'] = raw.get('pass_accuracy', 0)
                bm['passes_final_third'] = raw.get('line_breaks_completed', 0) + raw.get('ball_progressions', 0)
                bm['tackles'] = raw.get('tackles', 0)
                bm['recoveries'] = raw.get('possession_regains', 0)

            elif detailed_pos == 'CM':
                bm['goals'] = raw.get('goals', 0)
                bm['assists'] = 0
                bm['xg'] = 0
                bm['goals_minus_xg'] = 0
                bm['key_passes'] = raw.get('line_breaks_completed', 0)
                bm['pass_accuracy'] = raw.get('pass_accuracy', 0)

            elif detailed_pos == 'W':
                bm['goals'] = raw.get('goals', 0)
                bm['assists'] = 0
                bm['successful_dribbles'] = raw.get('take_ons', 0)
                bm['progressive_carries_box'] = raw.get('ball_progressions', 0)
                bm['npxg'] = 0
                bm['goal_involvements'] = raw.get('goals', 0)

            elif detailed_pos == 'ST':
                bm['goals'] = raw.get('goals', 0)
                bm['assists'] = 0
                bm['xg'] = 0
                bm['goals_minus_xg'] = 0
                bm['shots_on_target_pct'] = raw.get('shots_on_target_pct', 0)

            benchmark_stats[name] = bm

        return benchmark_stats, benchmark_positions

    def analyze_team(self, team: str) -> Tuple[Dict[str, Dict], Dict[str, str]]:
        """
        分析单支球队，返回可直接输入到BenchmarkEngine的数据。

        Returns:
            (player_stats, player_positions) - 可直接传给 engine.compare_team()
        """
        fifa_positions = self._get_player_positions(team)
        raw_stats = self._extract_player_stats(team)
        return self._map_to_benchmark_metrics(raw_stats, fifa_positions)

    def analyze_match(self) -> Dict[str, Tuple[Dict[str, Dict], Dict[str, str]]]:
        """
        分析比赛双方。

        Returns:
            {team_name: (player_stats, player_positions)}
        """
        teams = self._get_teams()
        result = {}
        for team in teams:
            result[team] = self.analyze_team(team)
        return result


# ============================================================
# FIFA 单文件适配（v2）
# 支持：上传任意一个FIFA CSV即可生成分析报告+训练建议
# ============================================================

# FIFA文件类型 → 识别列名特征
_FIFA_FILE_SIGNATURES = {
    'attempts_at_goal': ['outcome', 'body_part', 'shirt_number', 'player_name', 'time_min'],
    'key_stats': ['stat_name'],
    'crosses': ['cross_type', 'outcome', 'shirt_number'],
    'out_of_possession': ['tackles_made_won', 'interceptions', 'clearances', 'blocks'],
    'in_possession': ['passes_completed', 'passes_attempted', 'take_ons', 'ball_progressions'],
    'phases_of_play': ['phase_category', 'phase_name', 'home_pct', 'away_pct'],
    'physical_data': ['total_distance', 'sprints_count', 'high_speed_runs'],
    'passing_network': ['player1_name', 'player2_name', 'pass_count'],
    'offers_to_receive': ['offers_count', 'received_count'],
    'match_info': ['home_team', 'away_team'],
    'lineups': ['role', 'position', 'player_name', 'shirt_number'],
}


def detect_fifa_single_file_type(filepath):
    """根据列名识别单个FIFA CSV文件类型
    
    返回：字符串标识（'attempts_at_goal', 'key_stats', ...）或 'unknown'
    """
    if not os.path.exists(filepath):
        return 'unknown'
    try:
        df = pd.read_csv(filepath, encoding='utf-8-sig', nrows=3)
        df.columns = [c.strip().lstrip('\ufeff') for c in df.columns]
        cols_lower = set(c.lower() for c in df.columns)
        cols_joined = ' '.join(cols_lower)
        
        # 按特征列数量匹配，取最匹配的
        best_type = 'unknown'
        best_score = 0
        
        for ftype, sig_cols in _FIFA_FILE_SIGNATURES.items():
            score = sum(1 for sc in sig_cols if any(sc in col for col in cols_joined.split()))
            if score > best_score and score >= 2:
                best_score = score
                best_type = ftype
        
        # 特殊判断：射门文件的delivery_type
        if best_type == 'unknown' and 'team' in cols_lower and 'outcome' in cols_lower:
            if 'body_part' in cols_lower:
                best_type = 'attempts_at_goal'
        
        return best_type
    except Exception:
        return 'unknown'


def _estimate_xg_from_outcomes(shots_df):
    """根据射门结果估算xG（FIFA数据没有xG字段）
    
    权重：Goal=0.35, Saved=0.15, Blocked=0.05, OffT=0.05
    """
    if shots_df.empty:
        return 0.0
    weights = {'goal': 0.35, 'saved': 0.15, 'on target': 0.15, 'blocked': 0.05, 'off t': 0.05, 'off target': 0.05, 'error': 0.05}
    total_xg = 0.0
    for outcome in shots_df['outcome'].str.lower():
        o = str(outcome).strip()
        matched = False
        for key, w in weights.items():
            if key in o:
                total_xg += w
                matched = True
                break
        if not matched:
            total_xg += 0.05
    return round(total_xg, 2)


def _map_outcome_to_sb(outcome_str):
    """FIFA射门结果 → StatsBomb风格"""
    o = str(outcome_str).strip().lower()
    if 'goal' in o:
        return 'Goal'
    elif 'saved' in o:
        return 'Saved'
    elif 'blocked' in o:
        return 'Blocked'
    elif 'off target' in o or 'error' in o:
        return 'Off T'
    return 'Unknown'


def convert_fifa_single_file(filepath, match_name=None):
    """转换单个FIFA CSV文件为统一格式
    
    返回：(df, info, stats)
      df: 转换后的DataFrame（射门文件会转为事件流格式）
      info: 比赛信息字典
      stats: 与compute_match_stats输出兼容的stats字典
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到文件：{filepath}")
    
    raw = pd.read_csv(filepath, encoding='utf-8-sig')
    raw.columns = [c.strip().lstrip('\ufeff') for c in raw.columns]
    
    file_type = detect_fifa_single_file_type(filepath)
    if match_name is None:
        match_name = os.path.basename(filepath).replace('.csv', '').replace('_', ' ')
    
    teams = raw['team'].dropna().unique().tolist() if 'team' in raw.columns else []
    if len(teams) < 2 and 'team' in raw.columns:
        # 某些文件可能只有一队数据
        teams = raw['team'].dropna().unique().tolist()[:2]
    
    info = {
        'name': match_name,
        'teams': teams,
        'source': f'fifa_single ({file_type})',
        'file': filepath,
        'fifa_file_type': file_type,
        'fifa_single_data': True,
    }
    
    # 按文件类型分发处理
    if file_type == 'attempts_at_goal':
        df, stats = _convert_attempts(raw, teams, match_name)
    elif file_type == 'key_stats':
        df, stats = _convert_key_stats(raw, teams, match_name)
    elif file_type == 'crosses':
        df, stats = _convert_crosses(raw, teams, match_name)
    elif file_type == 'out_of_possession':
        df, stats = _convert_defense(raw, teams, match_name)
    elif file_type == 'in_possession':
        df, stats = _convert_possession(raw, teams, match_name)
    elif file_type == 'phases_of_play':
        df, stats = _convert_phases(raw, teams, match_name)
    elif file_type == 'physical_data':
        df, stats = _convert_physical(raw, teams, match_name)
    else:
        df, stats = _convert_generic(raw, teams, match_name)
    
    info['fifa_stats'] = stats
    return df, info


def _init_stats(teams):
    """初始化空stats字典（兼容stats_engine输出格式）"""
    stats = {}
    for team in teams:
        stats[team] = {
            'total_events': 0, 'possession_events': 0, 'possession_pct': 50.0,
            'passes_total': 0, 'passes_completed': 0, 'pass_accuracy': 0,
            'shots_total': 0, 'shots_on_target': 0, 'shots_off_target': 0,
            'goals': 0, 'xg': 0.0, 'fouls': 0, 'fouls_won': 0,
            'corners': 0, 'offsides': 0, 'key_passes': 0, 'assists': 0,
            'pass_leaders': pd.Series(dtype=int), 'shot_leaders': pd.Series(dtype=int),
            'xg_leaders': pd.Series(dtype=float), 'formation': 'N/A',
            'pressure_avg_x': None, 'high_turnovers': 0,
            'progressive_passes': 0, 'passes_into_final_third': 0,
            'passes_into_box': 0, 'deep_progressions': 0,
            'switches_of_play': 0, 'progressive_carries': 0, 'ppda': None,
            'progressive_sequences': 0, 'defensive_weak_zones': [], 'through_balls': 0,
            'crosses_total': 0, 'crosses_completed': 0, 'cross_accuracy': 0,
            'duels_total': 0, 'duels_won': 0, 'duel_success_rate': 0,
            'offensive_duel_success': 0, 'defensive_duel_success': 0,
            'aerial_duels_total': 0, 'aerial_success': 0,
            'counter_press_actions': 0, 'pressures_total': 0, 'pressures_high': 0,
            'turnover_x_mean': 60, 'turnover_own_third': 0, 'turnover_mid_third': 0,
            'turnover_final_third': 0, 'recovery_own_third': 0, 'recovery_mid_third': 0,
            'recovery_final_third': 0, 'high_recoveries': 0,
            'big_chances_taken': 0, 'big_chances_goals': 0,
            'shot_techniques': {}, 'shot_body_parts': {},
        }
    return stats


def _convert_attempts(raw, teams, match_name):
    """转换05_attempts_at_goal.csv → 事件流 + stats"""
    stats = _init_stats(teams)
    events = []
    
    for _, row in raw.iterrows():
        team = str(row.get('team', '')).strip()
        if team not in stats:
            continue
        
        outcome_raw = str(row.get('outcome', 'Unknown'))
        outcome_sb = _map_outcome_to_sb(outcome_raw)
        body_part = str(row.get('body_part', ''))
        time_min = row.get('time_min', 0)
        player = str(row.get('player_name', ''))
        
        # 构建类StatsBomb事件行
        events.append({
            'team': team, 'type': 'Shot',
            'player': player, 'time_min': time_min,
            'shot_outcome': outcome_sb,
            'shot_body_part': body_part,
            'possession_team': team,
            'x': None, 'y': None,
        })
        
        s = stats[team]
        s['shots_total'] += 1
        s['total_events'] += 1
        
        if outcome_sb == 'Goal':
            s['goals'] += 1
            s['shots_on_target'] += 1
        elif outcome_sb == 'Saved':
            s['shots_on_target'] += 1
        else:
            s['shots_off_target'] += 1
    
    # 估算xG
    for team in teams:
        team_shots = raw[raw['team'] == team]
        if not team_shots.empty:
            stats[team]['xg'] = _estimate_xg_from_outcomes(team_shots)
    
    # 大机会估算（进球视为大机会转化）
    for team in teams:
        s = stats[team]
        goals = s['goals']
        # 估算：每个进球约对应2次大机会
        s['big_chances_taken'] = max(goals * 2, 1) if goals > 0 else 0
        s['big_chances_goals'] = goals
    
    # 射门身体部位分布
    for team in teams:
        team_shots = raw[raw['team'] == team]
        if 'body_part' in team_shots.columns:
            bp_counts = team_shots['body_part'].value_counts().to_dict()
            stats[team]['shot_body_parts'] = bp_counts
    
    # 射门球员排行
    for team in teams:
        team_shots = raw[raw['team'] == team]
        if not team_shots.empty and 'player_name' in team_shots.columns:
            stats[team]['shot_leaders'] = team_shots['player_name'].value_counts().head(5)
    
    df = pd.DataFrame(events) if events else pd.DataFrame()
    return df, stats


def _convert_key_stats(raw, teams, match_name):
    """转换03_key_stats.csv → stats"""
    stats = _init_stats(teams)
    
    # key_stats通常是宽表格式：每行一个统计指标，列为home/away值
    # 或者：team, stat_name, value 格式
    # 尝试解析常见格式
    
    cols = set(c.lower() for c in raw.columns)
    
    if 'home_team' in cols and 'away_team' in cols:
        # 宽表格式
        home_name = str(raw.iloc[0].get('home_team', teams[0] if teams else 'Home')).strip()
        away_name = str(raw.iloc[0].get('away_team', teams[1] if len(teams) > 1 else 'Away')).strip()
        if not teams:
            teams = [home_name, away_name]
            stats = _init_stats(teams)
        
        for _, row in raw.iterrows():
            _parse_key_stat_row(row, stats, teams[0], teams[1] if len(teams) > 1 else None, 'home', 'away')
    elif 'stat_name' in cols or 'statistic' in cols:
        stat_col = 'stat_name' if 'stat_name' in cols else 'statistic'
        for _, row in raw.iterrows():
            stat_name = str(row.get(stat_col, '')).strip().lower()
            # 尝试从home/away列或value列获取值
            for i, team in enumerate(teams):
                val_col = f'home_{team.lower()}' if f'home_{team.lower()}' in cols else None
                if val_col:
                    val = row.get(val_col)
                    _apply_key_stat(stats, team, stat_name, val)
    else:
        # 逐行解析所有数值列
        for _, row in raw.iterrows():
            for team in teams:
                for col in raw.columns:
                    if team.lower() in col.lower():
                        val = row.get(col)
                        _apply_key_stat(stats, team, col, val)
    
    df = pd.DataFrame()
    return df, stats


def _parse_key_stat_row(row, stats, home, away, home_col_prefix, away_col_prefix):
    """解析一行key_stats数据"""
    cols = {c.lower(): c for c in row.index}
    for col_lower, col_actual in cols.items():
        val = row[col_actual]
        if home.lower() in col_lower or 'home' in col_lower:
            _apply_key_stat(stats, home, col_lower, val)
        elif away.lower() in col_lower or 'away' in col_lower:
            if away:
                _apply_key_stat(stats, away, col_lower, val)


def _apply_key_stat(stats, team, stat_name, value):
    """将单个统计值应用到stats字典"""
    if team not in stats:
        return
    s = stats[team]
    sn = str(stat_name).lower().strip()
    
    try:
        val = float(value) if pd.notna(value) else 0
    except (ValueError, TypeError):
        return
    
    if 'possession' in sn and 'pct' in sn or '控球' in sn:
        s['possession_pct'] = val
    elif 'pass' in sn and ('accuracy' in sn or 'completion' in sn or '成功率' in sn):
        s['pass_accuracy'] = val
    elif 'pass' in sn and ('attempted' in sn or 'total' in sn or '尝试' in sn):
        s['passes_total'] = max(s['passes_total'], int(val))
    elif 'pass' in sn and ('completed' in sn or '完成' in sn):
        s['passes_completed'] = max(s['passes_completed'], int(val))
    elif 'shot' in sn and ('total' in sn or 'attempt' in sn or '射门' in sn and '正' not in sn):
        s['shots_total'] = max(s['shots_total'], int(val))
    elif 'shot' in sn and ('on target' in sn or '射正' in sn):
        s['shots_on_target'] = max(s['shots_on_target'], int(val))
    elif 'goal' in sn and 'xg' not in sn:
        s['goals'] = max(s['goals'], int(val))
    elif 'xg' in sn or 'expected goal' in sn:
        s['xg'] = max(s['xg'], val)
    elif 'foul' in sn:
        s['fouls'] = max(s['fouls'], int(val))
    elif 'corner' in sn or '角球' in sn:
        s['corners'] = max(s['corners'], int(val))
    elif 'yellow' in sn:
        s['yellow_cards'] = int(val)
    elif 'red' in sn:
        s['red_cards'] = int(val)


def _convert_crosses(raw, teams, match_name):
    """转换06_crosses.csv → stats"""
    stats = _init_stats(teams)
    
    for _, row in raw.iterrows():
        team = str(row.get('team', '')).strip()
        if team not in stats:
            continue
        s = stats[team]
        s['crosses_total'] += 1
        
        outcome = str(row.get('outcome', '')).lower()
        if 'success' in outcome or 'complete' in outcome:
            s['crosses_completed'] += 1
    
    for team in teams:
        s = stats[team]
        if s['crosses_total'] > 0:
            s['cross_accuracy'] = s['crosses_completed'] / s['crosses_total'] * 100
    
    return pd.DataFrame(), stats


def _convert_defense(raw, teams, match_name):
    """转换10_out_of_possession.csv → stats"""
    stats = _init_stats(teams)
    
    for _, row in raw.iterrows():
        team = str(row.get('team', '')).strip()
        if team not in stats:
            continue
        s = stats[team]
        
        # 解析 "made/won" 格式
        tackles_str = str(row.get('tackles_made_won', '0/0'))
        made, won = _parse_fraction(tackles_str)
        tackles_total = made or 0
        tackles_won = won or 0
        
        s['duels_total'] += tackles_total
        s['duels_won'] += tackles_won
        
        interceptions = int(row.get('interceptions', 0) or 0)
        blocks = int(row.get('blocks', 0) or 0)
        clearances = int(row.get('clearances', 0) or 0)
        presses = int(row.get('pressing_direct', 0) or 0)
        regains = int(row.get('possession_regains', 0) or 0)
        
        s['pressures_total'] += presses
        s['high_recoveries'] += regains // 3  # 估算前场夺回
        s['total_events'] += tackles_total + interceptions + blocks + presses
    
    for team in teams:
        s = stats[team]
        if s['duels_total'] > 0:
            s['duel_success_rate'] = s['duels_won'] / s['duels_total'] * 100
    
    return pd.DataFrame(), stats


def _convert_possession(raw, teams, match_name):
    """转换08_in_possession_distributions.csv → stats"""
    stats = _init_stats(teams)
    
    for _, row in raw.iterrows():
        team = str(row.get('team', '')).strip()
        if team not in stats:
            continue
        s = stats[team]
        
        passes_att = int(row.get('passes_attempted', 0) or 0)
        passes_comp = int(row.get('passes_completed', 0) or 0)
        take_ons = int(row.get('take_ons', 0) or 0)
        line_breaks = int(row.get('line_breaks_completed', 0) or 0)
        ball_prog = int(row.get('ball_progressions', 0) or 0)
        crosses_comp = int(row.get('crosses_completed', 0) or 0)
        crosses_att = int(row.get('crosses_attempted', 0) or 0)
        switches = int(row.get('switches_of_play', 0) or 0)
        
        s['passes_total'] += passes_att
        s['passes_completed'] += passes_comp
        s['progressive_passes'] += line_breaks
        s['passes_into_final_third'] += ball_prog
        s['switches_of_play'] += switches
        s['crosses_total'] += crosses_att
        s['crosses_completed'] += crosses_comp
        s['progressive_carries'] += take_ons
        s['total_events'] += passes_att
    
    for team in teams:
        s = stats[team]
        if s['passes_total'] > 0:
            s['pass_accuracy'] = s['passes_completed'] / s['passes_total'] * 100
        if s['crosses_total'] > 0:
            s['cross_accuracy'] = s['crosses_completed'] / s['crosses_total'] * 100
    
    return pd.DataFrame(), stats


def _convert_phases(raw, teams, match_name):
    """转换04_phases_of_play.csv → stats"""
    stats = _init_stats(teams)
    # 比赛阶段数据主要影响战术洞察，基础指标无法直接提取
    return pd.DataFrame(), stats


def _convert_physical(raw, teams, match_name):
    """转换11_physical_data.csv → stats"""
    stats = _init_stats(teams)
    # 体能数据不直接影响战术stats，但可以在报告中展示
    return pd.DataFrame(), stats


def _convert_generic(raw, teams, match_name):
    """通用转换：尝试从任意CSV中提取有用信息"""
    stats = _init_stats(teams)
    
    # 尝试找team列
    team_col = None
    for col in raw.columns:
        if col.lower() == 'team':
            team_col = col
            break
    
    if team_col is None:
        return pd.DataFrame(), stats
    
    # 遍历所有数值列，尝试推断含义
    for team in teams:
        team_data = raw[raw[team_col] == team]
        s = stats[team]
        s['total_events'] = len(team_data)
        
        for col in team_data.select_dtypes(include=[np.number]).columns:
            col_lower = col.lower()
            if 'shot' in col_lower and 'total' in col_lower:
                s['shots_total'] = max(s['shots_total'], int(team_data[col].sum()))
            elif 'goal' in col_lower and 'xg' not in col_lower:
                s['goals'] = max(s['goals'], int(team_data[col].sum()))
    
    return pd.DataFrame(), stats


def generate_fifa_single_insights(stats, file_type):
    """根据FIFA单文件数据生成战术洞察
    
    返回与generate_insights兼容的insights列表（含training_key）
    """
    teams = list(stats.keys())
    if len(teams) < 2:
        return [{"category": "数据概览", "text": "数据不足，无法生成对比洞察", "priority": 3}]
    
    insights = []
    t1, t2 = teams[0], teams[1]
    s1, s2 = stats[t1], stats[t2]
    
    # 射门对比
    if s1['shots_total'] > 0 or s2['shots_total'] > 0:
        diff = s1['shots_total'] - s2['shots_total']
        if abs(diff) >= 3:
            more = t1 if diff > 0 else t2
            insights.append({
                "category": "进攻", "priority": 2,
                "text": f"{more}射门次数明显更多（{max(s1['shots_total'],s2['shots_total'])} vs {min(s1['shots_total'],s2['shots_total'])}）",
                "suggestion": "射门少的一方需提升进攻组织效率"
            })
        
        # 射正率
        for team in teams:
            s = stats[team]
            if s['shots_total'] > 3:
                sot_pct = s['shots_on_target'] / s['shots_total'] * 100
                if sot_pct < 30:
                    insights.append({
                        "category": "射门选择", "priority": 2,
                        "text": f"{team}射正率仅{sot_pct:.0f}%，射门质量待提升",
                        "suggestion": "分析射门位置分布，减少低质量射门",
                        "training_key": "射门选择差",
                    })
                elif sot_pct > 55:
                    insights.append({
                        "category": "射门选择", "priority": 2,
                        "text": f"{team}射正率{sot_pct:.0f}%，射门选择质量高",
                        "suggestion": "把握机会能力强"
                    })
        
        # 进球效率
        for team in teams:
            s = stats[team]
            if s['xg'] > 0 and abs(s['goals'] - s['xg']) >= 0.8:
                diff = s['goals'] - s['xg']
                if diff > 0:
                    insights.append({
                        "category": "进攻效率", "priority": 1,
                        "text": f"{team}进攻效率极高：估算xG {s['xg']:.1f} 却打进 {s['goals']} 球，把握机会能力突出",
                        "suggestion": "对手需限制该队射门机会"
                    })
                else:
                    insights.append({
                        "category": "进攻效率", "priority": 1,
                        "text": f"{team}浪费机会：估算xG {s['xg']:.1f} 但只进 {s['goals']} 球",
                        "suggestion": "临门一脚需专项训练",
                        "training_key": "终结效率低",
                    })
    
    # 传中质量
    for team in teams:
        s = stats[team]
        if s.get('crosses_total', 0) >= 3:
            ca = s.get('cross_accuracy', 0)
            if ca < 25 and ca > 0:
                insights.append({
                    "category": "传中质量", "priority": 2,
                    "text": f"{team}传中{s['crosses_total']}次，成功率仅{ca:.0f}%",
                    "suggestion": "训练传中精度和落点控制",
                    "training_key": "传中质量低",
                })
    
    # 对抗能力
    for team in teams:
        s = stats[team]
        if s.get('duels_total', 0) > 10:
            dsr = s.get('duel_success_rate', 50)
            if dsr < 40:
                insights.append({
                    "category": "对抗能力", "priority": 2,
                    "text": f"{team}对抗成功率{dsr:.0f}%，处于劣势",
                    "suggestion": "加强身体对抗和1v1防守能力",
                    "training_key": "1v1防守差",
                })
    
    # 控球率
    p1 = s1.get('possession_pct', 50)
    p2 = s2.get('possession_pct', 50)
    if abs(p1 - p2) > 15:
        dominant = t1 if p1 > p2 else t2
        less = t2 if p1 > p2 else t1
        insights.append({
            "category": "比赛节奏", "priority": 2,
            "text": f"{dominant}控球占优（{max(p1,p2):.0f}% vs {min(p1,p2):.0f}%）",
            "suggestion": f"{less}应关注反击效率而非追求控球"
        })
    
    # 传球成功率
    if abs(s1['pass_accuracy'] - s2['pass_accuracy']) > 8:
        better = t1 if s1['pass_accuracy'] > s2['pass_accuracy'] else t2
        worse = t2 if s1['pass_accuracy'] > s2['pass_accuracy'] else t1
        insights.append({
            "category": "传球质量", "priority": 2,
            "text": f"{better}传球成功率({max(s1['pass_accuracy'],s2['pass_accuracy']):.0f}%)明显高于{worse}({min(s1['pass_accuracy'],s2['pass_accuracy']):.0f}%)",
            "suggestion": f"{worse}可能受对手压迫影响"
        })
    
    # 为每条insight附加训练映射
    try:
        from stats_engine import TRAINING_MAPPING
        for ins in insights:
            tk = ins.get('training_key', '')
            if tk and tk in TRAINING_MAPPING:
                mapping = TRAINING_MAPPING[tk]
                ins['training_recommendations'] = mapping.get('overall', {}).get('trainings', [])
                ins['training_description'] = mapping.get('overall', {}).get('description', '')
    except ImportError:
        pass
    
    insights.sort(key=lambda x: x['priority'])
    
    if not insights:
        insights.append({
            "category": "通用", "text": "双方数据较为均衡", "priority": 3,
            "suggestion": "可结合更多数据维度进行深入分析"
        })
    
    return insights
