"""
stats_engine.py — 统计引擎
输入：df + info → 输出：stats字典（两队核心数据）
"""
import ast
import pandas as pd
import numpy as np


def compute_match_stats(df, info):
    """计算双方比赛核心数据，返回stats字典"""
    teams = [t for t in info.get('teams', []) if t in df['team'].values]
    if len(teams) < 2:
        teams = df['team'].dropna().unique().tolist()[:2]
    
    stats = {}
    for team in teams:
        t_df = df[df['team'] == team]
        
        # 基础
        total_events = len(t_df)
        possession_events = len(df[df['possession_team'] == team]) if 'possession_team' in df.columns else 0
        
        # 传球
        passes = t_df[t_df['type'] == 'Pass']
        pass_completed = passes[passes['pass_outcome'].isna()]
        pass_accuracy = len(pass_completed) / len(passes) * 100 if len(passes) > 0 else 0
        
        # 射门
        shots = t_df[t_df['type'] == 'Shot']
        goals = shots[shots['shot_outcome'] == 'Goal']
        saved = shots[shots['shot_outcome'] == 'Saved']
        blocked = shots[shots['shot_outcome'] == 'Blocked']
        off_target = shots[shots['shot_outcome'].isin(['Off T', 'Wayward', 'Post'])]
        on_target = len(goals) + len(saved)
        
        # xG
        xg_total = shots['shot_statsbomb_xg'].sum() if 'shot_statsbomb_xg' in shots.columns else 0
        
        # 犯规/角球/越位
        fouls = len(t_df[t_df['type'] == 'Foul Committed'])
        fouls_won = len(t_df[t_df['type'] == 'Foul Won'])
        corners = len(t_df[t_df['pass_type'] == 'Corner']) if 'pass_type' in t_df.columns else 0
        offsides = len(t_df[t_df['type'] == 'Offside'])
        
        # 关键传球/助攻
        key_passes = len(passes[passes['pass_shot_assist'] == True]) if 'pass_shot_assist' in passes.columns else 0
        assists = len(passes[passes['pass_goal_assist'] == True]) if 'pass_goal_assist' in passes.columns else 0
        
        # 球员排行
        pass_leaders = pass_completed.groupby('player').size().sort_values(ascending=False).head(5)
        shot_leaders = shots.groupby('player').size().sort_values(ascending=False).head(3)
        xg_leaders = shots.groupby('player')['shot_statsbomb_xg'].sum().sort_values(ascending=False).head(3) if 'shot_statsbomb_xg' in shots.columns else pd.Series(dtype=float)
        
        # 阵型
        formation = "N/A"
        if 'tactics' in t_df.columns:
            tactics_rows = t_df[t_df['tactics'].notna()]
            if not tactics_rows.empty:
                try:
                    first_tactic = ast.literal_eval(str(tactics_rows.iloc[0]['tactics']))
                    formation = first_tactic.get('formation', 'N/A')
                except:
                    pass
        
        # 逼抢位置（平均X坐标，仅防守事件）
        defensive_types = ['Pressure', 'Foul Committed', 'Block', 'Interception']
        def_events = t_df[t_df['type'].isin(defensive_types)]
        pressure_avg_x = def_events['x'].mean() if not def_events.empty and def_events['x'].notna().any() else None
        
        # 前场抢回球权
        if def_events['x'].notna().any():
            high_turnovers = len(def_events[def_events['x'] > 60])
        else:
            high_turnovers = 0
        
        stats[team] = {
            'total_events': total_events,
            'possession_events': possession_events,
            'passes_total': len(passes),
            'passes_completed': len(pass_completed),
            'pass_accuracy': pass_accuracy,
            'shots_total': len(shots),
            'shots_on_target': on_target,
            'shots_off_target': len(off_target) + len(blocked),
            'goals': len(goals),
            'xg': xg_total,
            'fouls': fouls,
            'fouls_won': fouls_won,
            'corners': corners,
            'offsides': offsides,
            'key_passes': key_passes,
            'assists': assists,
            'pass_leaders': pass_leaders,
            'shot_leaders': shot_leaders,
            'xg_leaders': xg_leaders,
            'formation': formation,
            'pressure_avg_x': pressure_avg_x,
            'high_turnovers': high_turnovers,
        }
    
    # 控球率
    total_poss = sum(s['possession_events'] for s in stats.values())
    if total_poss > 0:
        for team in stats:
            stats[team]['possession_pct'] = stats[team]['possession_events'] / total_poss * 100
    
    return stats


def generate_insights(stats, df=None, info=None):
    """根据统计数据自动生成战术洞察，返回insights列表
    
    每条洞察格式：{"category": "进攻/防守/节奏/体能", "text": "xxx", "priority": 1-3}
    priority: 1=重要发现, 2=值得注意, 3=补充信息
    """
    teams = list(stats.keys())
    if len(teams) < 2:
        return [{"category": "通用", "text": "数据不足，无法生成对比洞察", "priority": 3}]
    
    insights = []
    t1, t2 = teams[0], teams[1]
    s1, s2 = stats[t1], stats[t2]
    
    # === 进攻效率 ===
    for team in teams:
        s = stats[team]
        diff = s['goals'] - s['xg']
        if abs(diff) >= 0.8:
            priority = 1 if abs(diff) >= 1.5 else 2
            if diff > 0:
                insights.append({
                    "category": "进攻效率",
                    "text": f"{team}进攻效率极高：xG仅{s['xg']:.2f}却打进{s['goals']}球（超额+{diff:.2f}），把握机会能力突出",
                    "priority": priority,
                    "suggestion": "对手需限制该队射门机会，因为他们的转化率极高"
                })
            else:
                insights.append({
                    "category": "进攻效率",
                    "text": f"{team}浪费机会：xG达{s['xg']:.2f}但只进{s['goals']}球（亏欠{abs(diff):.2f}），临门一脚需提升",
                    "priority": priority,
                    "suggestion": "可分析射门位置分布，判断是选择问题还是技术问题"
                })
    
    # === 控球与节奏 ===
    p1 = s1.get('possession_pct', 50)
    p2 = s2.get('possession_pct', 50)
    if abs(p1 - p2) > 15:
        dominant = t1 if p1 > p2 else t2
        less = t2 if p1 > p2 else t1
        insights.append({
            "category": "比赛节奏",
            "text": f"{dominant}控球占优（{max(p1,p2):.0f}% vs {min(p1,p2):.0f}%），{less}偏向防守反击",
            "priority": 1,
            "suggestion": f"{less}应关注反击出球速度，而非追求控球率"
        })
    
    # === 传球质量 ===
    if abs(s1['pass_accuracy'] - s2['pass_accuracy']) > 8:
        better = t1 if s1['pass_accuracy'] > s2['pass_accuracy'] else t2
        worse = t2 if s1['pass_accuracy'] > s2['pass_accuracy'] else t1
        insights.append({
            "category": "传球质量",
            "text": f"{better}传球成功率({max(s1['pass_accuracy'],s2['pass_accuracy']):.0f}%)明显高于{worse}({min(s1['pass_accuracy'],s2['pass_accuracy']):.0f}%)，节奏控制更好",
            "priority": 2,
            "suggestion": f"{worse}可能受对手压迫影响，建议分析传球失败的位置分布"
        })
    
    # === 射正率 ===
    for team in teams:
        s = stats[team]
        if s['shots_total'] > 0:
            sot_pct = s['shots_on_target'] / s['shots_total'] * 100
            if sot_pct > 55:
                insights.append({
                    "category": "射门选择",
                    "text": f"{team}射正率{sot_pct:.0f}%，射门选择质量高",
                    "priority": 2,
                    "suggestion": "说明该队耐心组织，不轻易起脚"
                })
            elif sot_pct < 30 and s['shots_total'] > 5:
                insights.append({
                    "category": "射门选择",
                    "text": f"{team}射正率仅{sot_pct:.0f}%，射门位置/时机需要优化",
                    "priority": 2,
                    "suggestion": "建议分析射门分布，是否过多远射或被封堵位置射门"
                })
    
    # === 逼抢强度 ===
    if s1['fouls'] > s2['fouls'] + 5:
        insights.append({
            "category": "逼抢策略",
            "text": f"{t1}犯规{s1['fouls']}次远多于{t2}的{s2['fouls']}次，可能采用高强度逼抢/战术犯规打断节奏",
            "priority": 2,
            "suggestion": f"关注{t1}犯规集中区域，判断是高位逼抢还是低位犯规拖延"
        })
    elif s2['fouls'] > s1['fouls'] + 5:
        insights.append({
            "category": "逼抢策略",
            "text": f"{t2}犯规{s2['fouls']}次远多于{t1}的{s1['fouls']}次，可能采用高强度逼抢/战术犯规打断节奏",
            "priority": 2,
            "suggestion": f"关注{t2}犯规集中区域，判断是高位逼抢还是低位犯规拖延"
        })
    
    # === 逼抢位置（如果有坐标数据）===
    for team in teams:
        s = stats[team]
        if s.get('pressure_avg_x') is not None:
            avg_x = s['pressure_avg_x']
            if avg_x > 55:
                insights.append({
                    "category": "逼抢位置",
                    "text": f"{team}逼抢平均位置X={avg_x:.0f}，高位压迫激进",
                    "priority": 2,
                    "suggestion": "对手可通过长传绕过压迫区域"
                })
            elif avg_x < 45:
                insights.append({
                    "category": "逼抢位置",
                    "text": f"{team}逼抢平均位置X={avg_x:.0f}，中低位防守为主",
                    "priority": 3,
                    "suggestion": "对手可在中场耐心组织寻找破绽"
                })
    
    # 按优先级排序
    insights.sort(key=lambda x: x['priority'])
    
    if not insights:
        insights.append({
            "category": "通用",
            "text": "双方数据较为均衡，比赛竞争激烈",
            "priority": 3,
            "suggestion": "可进一步分析上下半场差异"
        })
    
    return insights
