"""
fifa_adapter.py — FIFA比赛报告数据适配器
功能：将FIFA PDF转出的CSV数据（12个文件）转换为战术透镜平台统一格式
"""
import os
import re
import pandas as pd
import numpy as np


# ========== 辅助函数 ==========

def _read_csv_safe(filepath):
    if not os.path.exists(filepath):
        return pd.DataFrame()
    df = pd.read_csv(filepath, encoding='utf-8-sig')
    df.columns = [c.strip().lstrip('\ufeff') for c in df.columns]
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].str.replace('\r', '', regex=False).str.strip()
    return df


def _parse_pct(s):
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
    if pd.isna(s):
        return None, None
    s = str(s).strip()
    m = re.match(r'(\d+)\s*\((\d+)\)', s)
    if m := re.match(r'(\d+)\s*\((\d+)\)', s)
    if m:
        return int(m.group(1)), int(m.group(2))
    try:
        return int(s), None
    except ValueError:
        return None, None


def _map_shot_outcome(fifa_outcome):
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
    if pd.isna(fifa_body_part):
        return None
    b = str(fifa_body_part).strip()
    return b


def _estimate_xg_per_shot(shots_df, total_xg):
    if total_xg <= 0 or shots_df.empty:
        return np.zeros(len(shots_df))
    outcome_weights = {
        'Goal': 0.50, 'Saved': 0.25, 'Blocked': 0.08, 'Off T': 0.08, 'Unknown': 0.10,
    }
    weights = np.array([outcome_weights.get(o, 0.1) for o in shots_df['shot_outcome']])
    weight_sum = weights.sum()
    if weight_sum == 0:
        return np.full(len(shots_df), total_xg / len(shots_df))
    return weights / weight_sum * total_xg


# ===== 修复1：位置映射推导阵型 =====
_POS_TO_LINE = {
    # 后卫
    'RB': 'DF', 'LB': 'DF', 'CB': 'DF', 'RWB': 'DF', 'LWB': 'DF',
    'RCB': 'DF', 'LCB': 'DF', 'RB2': 'DF', 'LB2': 'DF',
    'SW': 'DF', 'CDM': 'MF',
    # 中场
    'CM': 'MF', 'DM': 'MF', 'AM': 'MF', 'LM': 'MF', 'RM': 'MF',
    'CAM': 'MF', 'LCM': 'MF', 'RCM': 'MF', 'LDM': 'MF', 'RDM': 'MF',
    'LAM': 'MF', 'RAM': 'MF',
    # 前锋
    'ST': 'FW', 'CF': 'FW', 'LW': 'FW', 'RW': 'FW',
    'LS': 'FW', 'RS': 'FW', 'RF': 'FW', 'LF': 'FW',
    'SS': 'FW', 'LCF': 'FW', 'RCF': 'FW',
    # 大类直接匹配
    'DF': 'DF', 'DEF': 'DF', 'DEFENDER': 'DF',
    'MF': 'MF', 'MID': 'MF', 'MIDFIELDER': 'MF',
    'FW': 'FW', 'FWD': 'FW', 'FORWARD': 'FW',
    'GK': 'GK', 'GOALKEEPER': 'GK',
}


def _position_to_line(position):
    """具体位置 → 防线位置（GK/DF/MF/FW）"""
    if pd.isna(position):
        return None
    pos = str(position).strip().upper()
    return _POS_TO_LINE.get(pos, None)


def _derive_formation(lineups_df, team):
    """从首发阵容推导阵型，支持具体位置名和大类位置名"""
    starters = lineups_df[
        (lineups_df['team'] == team) &
        (lineups_df['role'] == 'starting')
    ]
    if starters.empty:
        return 'N/A'

    df_count = mf_count = fw_count = 0
    for _, row in starters.iterrows():
        pos = str(row.get('position', '')).strip().upper()
        line = _POS_TO_LINE.get(pos, pos if pos in ('DF', 'MF', 'FW', 'GK') else None)
        if line == 'DF':
            df_count += 1
        elif line == 'MF':
            mf_count += 1
        elif line == 'FW':
            fw_count += 1
        # GK不计入阵型数字

    parts = []
    if df_count > 0:
        parts.append(str(df_count))
    if mf_count > 0:
        parts.append(str(mf_count))
    if fw_count > 0:
        parts.append(str(fw_count))
    return '-'.join(parts) if parts else 'N/A'


def _get_player_positions(lineups_df, team):
    """获取球队球员位置映射 {player_name: position_line}"""
    players = lineups_df[lineups_df['team'] == team]
    pos_map = {}
    for _, row in players.iterrows():
        line = _position_to_line(row.get('position', ''))
        if line:
            pos_map[row['player_name']] = line
    return pos_map


# ========== 主适配器函数 ==========

def load_fifa_from_csv(csv_dir, match_name=None):
    # ---- 步骤1：读取所有CSV文件 ----
    csv_files = {
        'match_info': os.path.join(csv_dir, '01_match_info.csv'),
        'lineups': os.path.join(csv_dir, '02_lineups.csv'),
        'key_stats': os.path.join(csv_dir, '03_key_stats.csv'),
        'phases': os.path.join(csv_dir, '04_phases_of_play.csv'),
        'attempts': os.path.join(csv_dir, '05_attempts_at_goal.csv'),
        'crosses': os.path.join(csv_dir, '06_crosses.csv'),
        'offers': os.path.join(csv_dir, '07_offers_to_receive.csv'),
        'possession_dist': os.path.join(csv_dir, '08_in_possession_distributions.csv'),
        'possession_offers': os.path.join(csv_dir, '09_in_possession_offers.csv'),
        'defense': os.path.join(csv_dir, '10_out_of_possession.csv'),
        'physical': os.path.join(csv_dir, '11_physical_data.csv'),
        'passing_network': os.path.join(csv_dir, '12_passing_network.csv'),
    }

    data = {}
    for key, filepath in csv_files.items():
        data[key] = _read_csv_safe(filepath)

    # ---- 步骤2：解析比赛基本信息 ----
    match_info_df = data['match_info']
    info_dict = dict(zip(match_info_df['field'], match_info_df['value'])) \
        if not match_info_df.empty else {}

    home_team = info_dict.get('home_team', '主队')
    away_team = info_dict.get('away_team', '客队')
    home_score = int(info_dict.get('home_score', 0))
    away_score = int(info_dict.get('away_score', 0))

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
                'type': 'Shot',
                'team': row.get('team', ''),
                'player': row.get('player_name', ''),
                'minute': int(row['time_min']) if pd.notna(row.get('time_min')) else None,
                'period': 1 if (pd.notna(row.get('time_min')) and int(row['time_min']) <= 45) else 2,
                'x': np.nan,
                'y': np.nan,
                'shot_outcome': shot_outcome,
                'shot_body_part': _map_body_part(row.get('body_part')),
                'shot_technique': row.get('delivery_type', ''),
                'shot_statsbomb_xg': np.nan,
                'pass_outcome': np.nan,
                'pass_recipient': np.nan,
                'pass_end_x': np.nan,
                'pass_end_y': np.nan,
                'possession_team': row.get('team', ''),
            })

    df = pd.DataFrame(shot_events)

    if not df.empty:
        for team in teams:
            team_shots = df[df['team'] == team].index
            total_xg = team_stats[team].get('xg', 0)
            if len(team_shots) > 0 and total_xg > 0:
                xg_vals = _estimate_xg_per_shot(df.loc[team_shots], total_xg)
                df.loc[team_shots, 'shot_statsbomb_xg'] = xg_vals

    if not df.empty and 'minute' in df.columns:
        df = df.sort_values('minute').reset_index(drop=True)

    # ---- 步骤5：球员排行 ----
    pos_dist_df = data['possession_dist']
    pass_leaders = {team: pd.Series(dtype=int) for team in teams}
    if not pos_dist_df.empty:
        for team in teams:
            team_data = pos_dist_df[pos_dist_df['team'] == team]
            if not team_data.empty:
                leaders = team_data.set_index('player_name')['passes_completed'].sort_values(ascending=False).head(5)
                pass_leaders[team] = leaders

    shot_leaders = {team: pd.Series(dtype=int) for team in teams}
    xg_leaders = {team: pd.Series(dtype=float) for team in teams}
    if not attempts_df.empty:
        for team in teams:
            team_data = attempts_df[attempts_df['team'] == team]
            if not team_data.empty:
                leaders = team_data.groupby('player_name').size().sort_values(ascending=False).head(3)
                shot_leaders[team] = leaders
    if not df.empty:
        for team in teams:
            team_shots = df[df['team'] == team]
            if not team_shots.empty:
                leaders = team_shots.groupby('player')['shot_statsbomb_xg'].sum().sort_values(ascending=False).head(3)
                xg_leaders[team] = leaders

    # ---- 步骤6：推导阵型 ----
    lineups_df = data['lineups']
    formations = {}
    player_positions = {}
    for team in teams:
        formations[team] = _derive_formation(lineups_df, team)
        player_positions[team] = _get_player_positions(lineups_df, team)

    # ---- 步骤7：角球数 ----
    corners_count = {team: 0 for team in teams}
    if not attempts_df.empty:
        for team in teams:
            team_corners = attempts_df[
                (attempts_df['team'] == team) &
                (attempts_df['delivery_type'] == 'Corner')
            ]
            corners_count[team] = len(team_corners)

    # ---- 步骤8：构建stats字典 ----
    stats = {}
    for team in teams:
        ts = team_stats[team]
        shots_off_target = ts.get('shots_total', 0) - ts.get('shots_on_target', 0)
        possession_events = ts.get('passes_total', 0) + ts.get('shots_total', 0)
        total_events = possession_events + ts.get('forced_turnovers', 0)

        stats[team] = {
            'total_events': total_events,
            'possession_events': possession_events,
            'passes_total': ts.get('passes_total', 0),
            'passes_completed': ts.get('passes_completed', 0),
            'pass_accuracy': ts.get('pass_accuracy', 0),
            'shots_total': ts.get('shots_total', 0),
            'shots_on_target': ts.get('shots_on_target', 0),
            'shots_off_target': shots_off_target,
            'goals': ts.get('goals', 0),
            'xg': ts.get('xg', 0),
            'fouls': 0,
            'fouls_won': 0,
            'corners': corners_count[team],
            'offsides': 0,
            'key_passes': 0,
            'assists': 0,
            'pass_leaders': pass_leaders[team],
            'shot_leaders': shot_leaders[team],
            'xg_leaders': xg_leaders[team],
            'formation': formations[team],
            'pressure_avg_x': None,
            'high_turnovers': 0,
            'progressive_passes': 0,
            'passes_into_final_third': 0,
            'passes_into_box': 0,
            'deep_progressions': ts.get('ball_progressions', 0),
            'switches_of_play': 0,
            'progressive_carries': 0,
            'ppda': None,
            'progressive_sequences': 0,
            'defensive_weak_zones': [],
            'possession_pct': team_stats[team].get('possession_pct', 50),
        }

    if not pos_dist_df.empty:
        for team in teams:
            team_data = pos_dist_df[pos_dist_df['team'] == team]
            if not team_data.empty and 'switches_of_play' in team_data.columns:
                stats[team]['switches_of_play'] = int(team_data['switches_of_play'].sum())

    # ---- 步骤9：构建info字典（含传球网络数据）----
    # ===== 修复2：把传球网络数据和球员位置注入info =====
    passing_network_records = data['passing_network'].to_dict('records') \
        if not data['passing_network'].empty else []

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
        'fifa_extra': {
            'phases_of_play': data['phases'].to_dict('records') if not data['phases'].empty else [],
            'defensive_stats': True,
            'physical_stats': True,
            'passing_network': True,
            'passing_network_records': passing_network_records,
            'player_positions': player_positions,
        },
        'limited_features': [
            'shot_coordinates',
            'pass_coordinates',
            'possession_timeline',
            'pressure_heatmap',
            'fouls_data',
            'offsides_data',
            'assists_data',
            'key_passes_data',
            'ppda_calculation',
            'progressive_pass_detail',
            'defensive_weak_zones',
        ],
    }

    print(f"[FIFA适配器] 加载完成：{match_name}")
    print(f"  比赛：{home_team} {home_score} - {away_score} {away_team}")
    print(f"  事件数：{len(df)}（全部为射门事件）")
    print(f"  球队：{teams}")
    print(f"  阵型：{formations[home_team]} vs {formations[away_team]}")

    return df, info, stats


# ========== 便捷函数 ==========

def is_fifa_csv_dir(csv_dir):
    required = ['01_match_info.csv', '05_attempts_at_goal.csv', '03_key_stats.csv']
    return all(os.path.exists(os.path.join(csv_dir, f)) for f in required)


def fifa_chart_support(info):
    return {
        'shot_comparison': ('full', '射门对比数据完整'),
        'stats_bar': ('full', '核心数据对比完整'),
        'xg_flow': ('partial', 'xG累积曲线可用，xG为估算值'),
        'shot_map': ('partial', '射门位置图无坐标'),
        'pass_network': ('full', '传球网络基于FIFA传球网络数据，按位置分层布局'),
        'possession_timeline': ('partial', '仅射门事件有时间'),
        'pressure_heatmap': ('none', '无防守事件坐标'),
    }
