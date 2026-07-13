"""
team_tracker.py — 球队多场比赛追踪模块
功能：加载多场FIFA比赛数据，计算球队汇总指标与趋势数据，支持跨场对比分析

设计原则：
- 仅依赖 fifa_adapter.load_fifa_from_csv，不修改核心分析逻辑
- 缺数据的场次优雅降级（跳过缺失字段，不崩溃）
- 日期排序优先用 info.match_date，没有则用目录名
- 输出格式与现有 stats_engine / visualizer 风格兼容
"""
import os
import re
from datetime import datetime

# 延迟导入fifa_adapter（避免循环引用，实际使用时再导入）
_fifa_adapter = None


def _get_fifa_adapter():
    """延迟导入FIFA适配器"""
    global _fifa_adapter
    if _fifa_adapter is None:
        from fifa_adapter import load_fifa_from_csv
        _fifa_adapter = load_fifa_from_csv
    return _fifa_adapter


# ========== 核心函数1：加载多场比赛数据 ==========

def load_multiple_matches(csv_dirs):
    """
    加载多场FIFA比赛数据
    
    参数：
        csv_dirs: list — 多个CSV目录路径列表（每个目录是一场FIFA比赛的CSV输出）
    
    返回：
        match_data_list: list[dict] — 每场的字典列表，按比赛日期排序
            每个字典包含：
                - df: DataFrame（射门事件）
                - info: dict（比赛元信息）
                - stats: dict（球队统计）
                - csv_dir: str（原始目录路径）
                - dir_name: str（目录名，用于兜底排序）
    """
    match_data_list = []
    load_fifa = _get_fifa_adapter()
    
    for csv_dir in csv_dirs:
        if not os.path.isdir(csv_dir):
            print(f"[球队追踪] 警告：目录不存在，跳过 → {csv_dir}")
            continue
        
        try:
            df, info, stats = load_fifa(csv_dir)
            match_data_list.append({
                'df': df,
                'info': info,
                'stats': stats,
                'csv_dir': csv_dir,
                'dir_name': os.path.basename(csv_dir.rstrip('/')),
            })
            print(f"[球队追踪] 加载成功：{info.get('name', '未知比赛')}")
        except Exception as e:
            print(f"[球队追踪] 警告：加载失败，跳过 → {csv_dir}（{str(e)[:60]}）")
            continue
    
    # 按比赛日期排序（优先用info.match_date，没有就按目录名）
    def _sort_key(m):
        info = m['info']
        match_date = info.get('match_date', '')
        if match_date:
            # 尝试解析常见日期格式
            for fmt in ['%d %B %Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                try:
                    return (0, datetime.strptime(match_date.strip(), fmt))
                except ValueError:
                    continue
        # 兜底：用目录名排序
        return (1, m['dir_name'].lower())
    
    match_data_list.sort(key=_sort_key)
    
    print(f"[球队追踪] 共加载 {len(match_data_list)} 场比赛（已按日期排序）")
    return match_data_list


# ========== 辅助：获取对手球队名 ==========

def _get_opponent(info, target_team):
    """从info中获取目标球队的对手名称"""
    teams = info.get('teams', [])
    for t in teams:
        if t != target_team:
            return t
    return '未知对手'


# ========== 辅助：安全获取数值 ==========

def _safe_get(d, key, default=0):
    """安全从字典获取数值，处理None和缺失情况"""
    val = d.get(key, default)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ========== 核心函数2：计算汇总指标 ==========

def compute_team_overview(match_data_list, target_team):
    """
    计算目标球队的多场汇总指标
    
    参数：
        match_data_list: list[dict] — 多场比赛数据
        target_team: str — 目标球队名
    
    返回：
        overview: dict — 汇总指标
            - matches: int — 场次
            - wins / draws / losses: int — 胜/平/负
            - win_rate: float — 胜率（0-100）
            - goals_for: int — 总进球
            - goals_against: int — 总失球
            - goal_diff: int — 净胜球
            - xg_total: float — 总xG
            - xga_total: float — 总xGA（对手xG）
            - xg_diff: float — xG差
            - avg_possession: float — 场均控球率（%）
            - avg_shots: float — 场均射门
            - avg_shots_on_target: float — 场均射正
            - avg_pass_accuracy: float — 场均传球成功率（%）
            - results: list[dict] — 每场结果明细
    """
    if not match_data_list:
        return {}
    
    matches = 0
    wins = 0
    draws = 0
    losses = 0
    goals_for = 0
    goals_against = 0
    xg_total = 0.0
    xga_total = 0.0
    possession_sum = 0.0
    possession_count = 0
    shots_sum = 0
    shots_on_target_sum = 0
    pass_accuracy_sum = 0.0
    pass_accuracy_count = 0
    results = []
    
    for m in match_data_list:
        stats = m['stats']
        info = m['info']
        
        # 检查目标球队是否在本场比赛中
        if target_team not in stats:
            continue
        
        team_stats = stats[target_team]
        opponent = _get_opponent(info, target_team)
        opponent_stats = stats.get(opponent, {})
        
        matches += 1
        
        # 进球与失球
        gf = int(_safe_get(team_stats, 'goals', 0))
        ga = int(_safe_get(opponent_stats, 'goals', 0))
        goals_for += gf
        goals_against += ga
        
        # 胜负判断
        if gf > ga:
            wins += 1
            result = '胜'
        elif gf == ga:
            draws += 1
            result = '平'
        else:
            losses += 1
            result = '负'
        
        # xG
        xg = _safe_get(team_stats, 'xg', 0)
        xga = _safe_get(opponent_stats, 'xg', 0)
        xg_total += xg
        xga_total += xga
        
        # 控球率
        poss = _safe_get(team_stats, 'possession_pct', None)
        if poss is not None and poss > 0:
            possession_sum += poss
            possession_count += 1
        
        # 射门
        shots_sum += int(_safe_get(team_stats, 'shots_total', 0))
        shots_on_target_sum += int(_safe_get(team_stats, 'shots_on_target', 0))
        
        # 传球成功率
        pass_acc = _safe_get(team_stats, 'pass_accuracy', None)
        if pass_acc is not None and pass_acc > 0:
            pass_accuracy_sum += pass_acc
            pass_accuracy_count += 1
        
        # 本场结果明细
        results.append({
            'match_name': info.get('name', ''),
            'opponent': opponent,
            'match_date': info.get('match_date', ''),
            'goals_for': gf,
            'goals_against': ga,
            'result': result,
            'xg': round(xg, 2),
            'xga': round(xga, 2),
            'possession': round(poss, 1) if poss else None,
            'shots': int(_safe_get(team_stats, 'shots_total', 0)),
            'shots_on_target': int(_safe_get(team_stats, 'shots_on_target', 0)),
            'pass_accuracy': round(pass_acc, 1) if pass_acc else None,
        })
    
    if matches == 0:
        return {}
    
    overview = {
        'matches': matches,
        'wins': wins,
        'draws': draws,
        'losses': losses,
        'win_rate': round(wins / matches * 100, 1),
        'goals_for': goals_for,
        'goals_against': goals_against,
        'goal_diff': goals_for - goals_against,
        'xg_total': round(xg_total, 2),
        'xga_total': round(xga_total, 2),
        'xg_diff': round(xg_total - xga_total, 2),
        'avg_possession': round(possession_sum / possession_count, 1) if possession_count > 0 else None,
        'avg_shots': round(shots_sum / matches, 1),
        'avg_shots_on_target': round(shots_on_target_sum / matches, 1),
        'avg_pass_accuracy': round(pass_accuracy_sum / pass_accuracy_count, 1) if pass_accuracy_count > 0 else None,
        'results': results,
    }
    
    return overview


# ========== 核心函数3：提取趋势数据 ==========

def compute_trends(match_data_list, target_team):
    """
    提取目标球队的趋势数据（按场次排序的数值列表）
    
    参数：
        match_data_list: list[dict] — 多场比赛数据（已排序）
        target_team: str — 目标球队名
    
    返回：
        trends: dict — 每个指标是按场次排序的数值列表
            指标：possession, shots, shots_on_target, goals, xg, pass_accuracy,
                  goals_against, xga（对手xG）
        match_labels: list[str] — 每场的对手名（用于x轴标签）
    """
    if not match_data_list:
        return {}, []
    
    trends = {
        'possession': [],
        'shots': [],
        'shots_on_target': [],
        'goals': [],
        'xg': [],
        'pass_accuracy': [],
        'goals_against': [],
        'xga': [],
    }
    
    match_labels = []
    
    for m in match_data_list:
        stats = m['stats']
        info = m['info']
        
        # 跳过目标球队不在本场的情况
        if target_team not in stats:
            continue
        
        team_stats = stats[target_team]
        opponent = _get_opponent(info, target_team)
        opponent_stats = stats.get(opponent, {})
        
        match_labels.append(opponent)
        
        # 控球率
        trends['possession'].append(_safe_get(team_stats, 'possession_pct', None))
        
        # 射门
        trends['shots'].append(int(_safe_get(team_stats, 'shots_total', 0)))
        trends['shots_on_target'].append(int(_safe_get(team_stats, 'shots_on_target', 0)))
        
        # 进球
        trends['goals'].append(int(_safe_get(team_stats, 'goals', 0)))
        
        # xG
        trends['xg'].append(_safe_get(team_stats, 'xg', 0))
        
        # 传球成功率
        trends['pass_accuracy'].append(_safe_get(team_stats, 'pass_accuracy', None))
        
        # 失球（对手进球）
        trends['goals_against'].append(int(_safe_get(opponent_stats, 'goals', 0)))
        
        # 对手xG
        trends['xga'].append(_safe_get(opponent_stats, 'xg', 0))
    
    return trends, match_labels


# ========== 辅助：检测共同球队 ==========

def find_common_teams(match_data_list):
    """
    找出所有比赛中共同出现的球队
    
    参数：
        match_data_list: list[dict] — 多场比赛数据
    
    返回：
        common_teams: list[str] — 出现在所有比赛中的球队名（按出现次数降序）
    """
    if not match_data_list:
        return []
    
    # 统计每支球队出现的场次
    team_counts = {}
    for m in match_data_list:
        teams = m['info'].get('teams', [])
        for t in teams:
            team_counts[t] = team_counts.get(t, 0) + 1
    
    # 按出现次数降序排序
    sorted_teams = sorted(team_counts.items(), key=lambda x: x[1], reverse=True)
    
    # 返回至少出现2场的球队
    common_teams = [t for t, cnt in sorted_teams if cnt >= 2]
    
    return common_teams