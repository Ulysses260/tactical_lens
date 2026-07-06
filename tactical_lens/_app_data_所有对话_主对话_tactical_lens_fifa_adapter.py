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


def _derive_formation(lineups_df, team):
    """从首发阵容位置推导阵型
    
    统计首发中DF/MF/FW数量，输出如 "4-3-3" 格式
    """
    starters = lineups_df[
        (lineups_df['team'] == team) & 
        (lineups_df['role'] == 'starting')
    ]
    if starters.empty:
        return 'N/A'
    
    df_count = len(starters[starters['position'] == 'DF'])
    mf_count = len(starters[starters['position'] == 'MF'])
    fw_count = len(starters[starters['position'] == 'FW'])
    
    formation_parts = []
    if df_count > 0:
        formation_parts.append(str(df_count))
    if mf_count > 0:
        formation_parts.append(str(mf_count))
    if fw_count > 0:
        formation_parts.append(str(fw_count))
    
    return '-'.join(formation_parts) if formation_parts else 'N/A'


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
    """
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
    
    # ---- 步骤6：推导阵型 ----
    lineups_df = data['lineups']
    formations = {}
    for team in teams:
        formations[team] = _derive_formation(lineups_df, team)
    
    # ---- 步骤7：角球数统计（来自射门中Corner类型）----
    corners_count = {team: 0 for team in teams}
    if not attempts_df.empty:
        for team in teams:
            team_corners = attempts_df[
                (attempts_df['team'] == team) & 
                (attempts_df['delivery_type'] == 'Corner')
            ]
            corners_count[team] = len(team_corners)
    
    # ---- 步骤8：构建stats字典（与stats_engine格式一致）----
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
            
            # 犯规/角球/越位（FIFA数据无，置0）
            'fouls': 0,
            'fouls_won': 0,
            'corners': corners_count[team],
            'offsides': 0,
            
            # 关键传球/助攻（FIFA数据无，置0）
            'key_passes': 0,
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
        stats[team]['possession_pct'] = ts.get('possession_pct', 50)
    
    # 重新赋值（上面循环中最后一个team的ts会覆盖，需单独设置）
    for team in teams:
        stats[team]['possession_pct'] = team_stats[team].get('possession_pct', 50)
    
    # ---- 步骤9：构建info字典 ----
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
            'defensive_stats': True,  # 有防守数据
            'physical_stats': True,   # 有体能数据
            'passing_network': True,  # 有传球网络
        },
        # 受限功能列表（FIFA数据无法支持的功能）
        'limited_features': [
            'shot_coordinates',       # 射门无坐标，射门位置图无法精确定位
            'pass_coordinates',       # 传球无坐标，传球网络仅能显示节点大小
            'possession_timeline',    # 无逐事件控球数据，时间线图精度有限
            'pressure_heatmap',       # 无防守事件坐标，热力图无法生成
            'fouls_data',             # 无犯规数据
            'offsides_data',          # 无越位数据
            'assists_data',           # 无助攻数据
            'key_passes_data',        # 无关键传球数据
            'ppda_calculation',       # 无法计算PPDA（缺少防守事件数）
            'progressive_pass_detail',  # 推进传球细节不足
            'defensive_weak_zones',   # 无法计算防守薄弱区域
        ],
    }
    
    print(f"[FIFA适配器] 加载完成：{match_name}")
    print(f"  比赛：{home_team} {home_score} - {away_score} {away_team}")
    print(f"  事件数：{len(df)}（全部为射门事件）")
    print(f"  球队：{teams}")
    print(f"  受限功能：{len(info['limited_features'])}项")
    
    return df, info, stats


# ========== 便捷函数 ==========

def is_fifa_csv_dir(csv_dir):
    """判断一个目录是否为FIFA比赛报告CSV输出目录
    
    检测依据：是否同时存在01_match_info.csv和05_attempts_at_goal.csv
    """
    required = ['01_match_info.csv', '05_attempts_at_goal.csv', '03_key_stats.csv']
    return all(os.path.exists(os.path.join(csv_dir, f)) for f in required)


def fifa_chart_support(info):
    """返回各图表对FIFA数据的支持情况
    
    返回：{图表ID: (支持等级, 说明)}
    支持等级：full（完整支持）、partial（部分支持）、none（不支持）
    """
    support = {
        'shot_comparison': ('full', '射门对比数据完整'),
        'stats_bar': ('full', '核心数据对比完整（控球、传球、射门、角球）'),
        'xg_flow': ('partial', 'xG累积曲线可用，xG为按结果类型估算值'),
        'shot_map': ('partial', '射门位置图无坐标，只能显示射门数量统计'),
        'pass_network': ('partial', '传球网络仅有传球次数，无位置坐标'),
        'possession_timeline': ('partial', '仅射门事件有时间，控球时间线不完整'),
        'pressure_heatmap': ('none', '无防守事件坐标数据，无法生成热力图'),
    }
    return support
