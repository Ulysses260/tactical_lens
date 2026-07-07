"""
fifa_adapter.py — FIFA比赛报告数据适配器
功能：将FIFA PDF转出的CSV数据（12个文件）转换为战术透镜平台统一格式
"""
import os
import re
import pandas as pd
import numpy as np


def _read_csv_safe(filepath):
    """安全读取CSV，文件不存在返回空DataFrame"""
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
    return str(fifa_body_part).strip()


def _estimate_xg_per_shot(shots_df, total_xg):
    if total_xg <= 0 or shots_df.empty:
        return np.zeros(len(shots_df))
    outcome_weights = {
        'Goal': 0.50, 'Saved': 0.25, 'Blocked': 0.08,
        'Off T': 0.08, 'Unknown': 0.10,
    }
    weights = np.array([outcome_weights.get(o, 0.1) for o in shots_df['shot_outcome']])
    weight_sum = weights.sum()
    if weight_sum == 0:
        return np.full(len(shots_df), total_xg / len(shots_df))
    return weights / weight_sum * total_xg


def _derive_formation(lineups_df, team):
    if lineups_df.empty:
        return 'N/A'
    starters = lineups_df[
        (lineups_df['team'] == team) & 
        (lineups_df['role'] == 'starting')
    ]
    if starters.empty:
        return 'N/A'
    df_count = len(starters[starters['position'] == 'DF'])
    mf_count = len(starters[starters['position'] == 'MF'])
    fw_count = len(starters[starters['position'] == 'FW'])
    parts = []
    if df_count > 0:
        parts.append(str(df_count))
    if mf_count > 0:
        parts.append(str(mf_count))
    if fw_count > 0:
        parts.append(str(fw_count))
    return '-'.join(parts) if parts else 'N/A'


def load_fifa_from_csv(csv_dir, match_name=None):
    """加载FIFA比赛报告CSV目录，返回 (df, info, stats)"""
    # ---- 1. 读取所有CSV（缺文件返回空，不报错）----
    csv_files = {
        'match_info': '01_match_info.csv',
        'lineups': '02_lineups.csv',
        'key_stats': '03_key_stats.csv',
        'phases': '04_phases_of_play.csv',
        'attempts': '05_attempts_at_goal.csv',
        'crosses': '06_crosses.csv',
        'offers': '07_offers_to_receive.csv',
        'possession_dist': '08_in_possession_distributions.csv',
        'possession_offers': '09_in_possession_offers.csv',
        'defense': '10_out_of_possession.csv',
        'physical': '11_physical_data.csv',
        'passing_network': '12_passing_network.csv',
    }
    data = {}
    for key, filename in csv_files.items():
        data[key] = _read_csv_safe(os.path.join(csv_dir, filename))

    # ---- 2. 比赛基本信息 ----
    match_info_df = data['match_info']
    if not match_info_df.empty and 'field' in match_info_df.columns:
        info_dict = dict(zip(match_info_df['field'], match_info_df['value']))
    else:
        info_dict = {}

    home_team = info_dict.get('home_team', '主队')
    away_team = info_dict.get('away_team', '客队')
    home_score = int(info_dict.get('home_score', 0) or 0)
    away_score = int(info_dict.get('away_score', 0) or 0)

    if match_name is None:
        match_name = f"{home_team} vs {away_team}"

    teams = [home_team, away_team]

    # ---- 3. 核心统计数据 ----
    key_stats_df = data['key_stats']
    team_stats = {team: {} for team in teams}

    if not key_stats_df.empty:
        for _, row in key_stats_df.iterrows():
            stat_name = row.get('stat_name', '')
            home_val = row.get('home_value', '')
            away_val = row.get('away_value', '')

            if stat_name == 'Total Possession':
                team_stats[home_team]['possession_pct'] = _parse_pct(home_val) or 50
                team_stats[away_team]['possession_pct'] = _parse_pct(away_val) or 50
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
                ht, ho = _parse_attempts(home_val)
                at, ao = _parse_attempts(away_val)
                team_stats[home_team]['shots_total'] = ht or 0
                team_stats[home_team]['shots_on_target'] = ho or 0
                team_stats[away_team]['shots_total'] = at or 0
                team_stats[away_team]['shots_on_target'] = ao or 0
            elif stat_name == 'Total Passes (Complete)':
                ht, ho = _parse_attempts(home_val)
                at, ao = _parse_attempts(away_val)
                team_stats[home_team]['passes_total'] = ht or 0
                team_stats[home_team]['passes_completed'] = ho or 0
                team_stats[away_team]['passes_total'] = at or 0
                team_stats[away_team]['passes_completed'] = ao or 0
            elif stat_name == 'Pass Completion':
                team_stats[home_team]['pass_accuracy'] = _parse_pct(home_val) or 0
                team_stats[away_team]['pass_accuracy'] = _parse_pct(away_val) or 0
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

    # 兜底：用比分覆盖进球数
    team_stats[home_team]['goals'] = home_score
    team_stats[away_team]['goals'] = away_score

    # ---- 4. 射门事件DataFrame ----
    attempts_df = data['attempts']
    shot_events = []

    if not attempts_df.empty:
        for _, row in attempts_df.iterrows():
            fifa_outcome = row.get('outcome', '')
            shot_outcome = _map_shot_outcome(fifa_outcome)
            minute_val = row.get('time_min')
            minute = int(minute_val) if pd.notna(minute_val) else None

            shot_events.append({
                'type': 'Shot',
                'team': row.get('team', ''),
                'player': row.get('player_name', ''),
                'minute': minute,
                'period': 1 if (minute and minute <= 45) else 2,
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

    # 估算每脚射门的xG
    if not df.empty:
        for team in teams:
            team_idx = df[df['team'] == team].index
            total_xg = team_stats[team].get('xg', 0)
            if len(team_idx) > 0 and total_xg > 0:
                xg_vals = _estimate_xg_per_shot(df.loc[team_idx], total_xg)
                df.loc[team_idx, 'shot_statsbomb_xg'] = xg_vals

    if not df.empty and 'minute' in df.columns:
        df = df.sort_values('minute').reset_index(drop=True)

    # ---- 5. 球员排行 ----
    pos_dist_df = data['possession_dist']

    pass_leaders = {team: pd.Series(dtype=int) for team in teams}
    if not pos_dist_df.empty and 'player_name' in pos_dist_df.columns:
        for team in teams:
            team_data = pos_dist_df[pos_dist_df['team'] == team]
            if not team_data.empty and 'passes_completed' in team_data.columns:
                leaders = team_data.set_index('player_name')['passes_completed'].sort_values(ascending=False).head(5)
                pass_leaders[team] = leaders

    shot_leaders = {team: pd.Series(dtype=int) for team in teams}
    if not attempts_df.empty:
        for team in teams:
            team_data = attempts_df[attempts_df['team'] == team]
            if not team_data.empty:
                leaders = team_data.groupby('player_name').size().sort_values(ascending=False).head(3)
                shot_leaders[team] = leaders

    xg_leaders = {team: pd.Series(dtype=float) for team in teams}
    if not df.empty:
        for team in teams:
            team_shots = df[df['team'] == team]
            if not team_shots.empty:
                leaders = team_shots.groupby('player')['shot_statsbomb_xg'].sum().sort_values(ascending=False).head(3)
                xg_leaders[team] = leaders

    # ---- 6. 阵型 ----
    lineups_df = data['lineups']
    formations = {}
    for team in teams:
        formations[team] = _derive_formation(lineups_df, team)

    # ---- 7. 角球数 ----
    corners_count = {team: 0 for team in teams}
    if not attempts_df.empty and 'delivery_type' in attempts_df.columns:
        for team in teams:
            corners_count[team] = len(attempts_df[
                (attempts_df['team'] == team) & 
                (attempts_df['delivery_type'] == 'Corner')
            ])

    # ---- 8. 构建stats字典 ----
    stats = {}
    for team in teams:
        ts = team_stats[team]
        shots_off = ts.get('shots_total', 0) - ts.get('shots_on_target', 0)
        poss_events = ts.get('passes_total', 0) + ts.get('shots_total', 0)
        total_events = poss_events + ts.get('forced_turnovers', 0)

        stats[team] = {
            'total_events': total_events,
            'possession_events': poss_events,
            'passes_total': ts.get('passes_total', 0),
            'passes_completed': ts.get('passes_completed', 0),
            'pass_accuracy': ts.get('pass_accuracy', 0),
            'shots_total': ts.get('shots_total', 0),
            'shots_on_target': ts.get('shots_on_target', 0),
            'shots_off_target': shots_off,
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
            'possession_pct': ts.get('possession_pct', 50),
        }

    # ---- 9. 构建info字典 ----
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
            'defensive_stats': not data['defense'].empty,
            'physical_stats': not data['physical'].empty,
            'passing_network': not data['passing_network'].empty,
        },
        'limited_features': [
            'shot_coordinates',
            'pass_coordinates',
            'pressure_heatmap',
            'fouls_data',
            'offsides_data',
            'assists_data',
            'key_passes_data',
            'ppda_calculation',
            'defensive_weak_zones',
        ],
    }

    return df, info, stats


def is_fifa_csv_dir(csv_dir):
    """判断目录是否包含FIFA格式CSV（有任意一个特征文件就算）"""
    markers = ['01_match_info.csv', '03_key_stats.csv',
               '05_attempts_at_goal.csv', '12_passing_network.csv']
    return any(os.path.exists(os.path.join(csv_dir, f)) for f in markers)
