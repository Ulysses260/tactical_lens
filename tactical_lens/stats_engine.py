"""
stats_engine.py — 统计引擎 v2
输入：df + info → 输出：stats字典（两队核心数据）+ 训练映射洞察
新增：反抢/对抗/传中/球权流动/大机会等StatsBomb核心指标
知识库映射：每条insight自动关联训练方案
"""
import json
import pandas as pd
import numpy as np

try:
    from progression_rules import apply_all_rules, detect_progressive_sequences, detect_defensive_vulnerabilities
    _HAS_PROGRESSION = True
except ImportError:
    _HAS_PROGRESSION = False


# ============================================================
# 训练映射知识库（来源：StatsBomb Glossary + 战术透镜知识库）
# 结构：{insight_type: {condition: {zone: {trainings: [...]}}}}
# ============================================================
TRAINING_MAPPING = {
    "终结效率低": {
        "overall": {
            "description": "xG高于实际进球，射门终结能力不足",
            "trainings": [
                {"name": "1v1射门训练", "scenario": "1v1进攻", "zone": "进攻三区", "duration": "15min",
                 "focus": "一对一面对门将的射门质量"},
                {"name": "禁区终结专项", "scenario": "射门训练", "zone": "禁区", "duration": "20min",
                 "focus": "禁区内不同角度的射门技术"},
            ]
        }
    },
    "射门选择差": {
        "overall": {
            "description": "射门数多但xG低，射门位置/时机不佳",
            "trainings": [
                {"name": "射门选择决策训练", "scenario": "进攻决策", "zone": "进攻三区", "duration": "15min",
                 "focus": "识别好的射门时机vs继续配合"},
                {"name": "进攻套路演练", "scenario": "推进配合", "zone": "进攻三区", "duration": "20min",
                 "focus": "通过配合创造高xG机会而非强射"},
            ]
        }
    },
    "压迫强度不足": {
        "overall": {
            "description": "PPDA偏高或防守动作少，前场压迫不够",
            "trainings": [
                {"name": "前场反抢训练", "scenario": "防守压迫", "zone": "前场", "duration": "20min",
                 "focus": "丢球后5秒内集体反抢的意识和协调"},
                {"name": "压迫+进攻衔接", "scenario": "压迫训练", "zone": "前场", "duration": "25min",
                 "focus": "高位抢断后快速转进攻的衔接"},
            ]
        }
    },
    "1v1防守差": {
        "overall": {
            "description": "被突破次数多，单人防守能力弱",
            "trainings": [
                {"name": "1v1防守训练", "scenario": "1v1防守", "zone": "中路", "duration": "15min",
                 "focus": "防守姿态、延缓、逼迫方向"},
                {"name": "2v2边路防守", "scenario": "2v2", "zone": "边路", "duration": "20min",
                 "focus": "边路配合防守的协调和补位"},
            ]
        }
    },
    "推进传球少": {
        "overall": {
            "description": "缺少纵向穿透传球，进攻缺少纵深",
            "trainings": [
                {"name": "破线传球训练", "scenario": "推进配合", "zone": "中场", "duration": "20min",
                 "focus": "中场球员向前的穿透传球时机和精度"},
                {"name": "中场推进配合", "scenario": "推进配合", "zone": "中场→进攻三区", "duration": "25min",
                 "focus": "连续传球推进的组织能力"},
            ]
        }
    },
    "后场出球差": {
        "overall": {
            "description": "后场传球成功率低，面对压迫出球困难",
            "trainings": [
                {"name": "后场组织训练", "scenario": "后场出球", "zone": "后场", "duration": "20min",
                 "focus": "面对压迫时的短传配合和长传转移"},
                {"name": "后场2v1出球", "scenario": "2v1", "zone": "后场", "duration": "15min",
                 "focus": "后场局部人数优势下的快速出球"},
            ]
        }
    },
    "边路进攻弱": {
        "overall": {
            "description": "边路传中成功率低或边路推进少",
            "trainings": [
                {"name": "边路套边配合", "scenario": "边路进攻", "zone": "边路", "duration": "20min",
                 "focus": "边后卫前插+边锋内切的配合套路"},
                {"name": "传中质量训练", "scenario": "边路进攻", "zone": "边路→禁区", "duration": "15min",
                 "focus": "不同位置、不同脚法的传中精度"},
            ]
        }
    },
    "反抢能力弱": {
        "overall": {
            "description": "丢球后反抢成功率低，转换防守薄弱",
            "trainings": [
                {"name": "丢球反抢训练", "scenario": "攻防转换", "zone": "全场", "duration": "20min",
                 "focus": "丢球瞬间立即反抢的反应速度和协同"},
                {"name": "转换攻防演练", "scenario": "攻防转换", "zone": "中场", "duration": "25min",
                 "focus": "攻转守5秒内的反抢/落位决策"},
            ]
        }
    },
    "反击效率低": {
        "overall": {
            "description": "抢断后反击射门少，转换进攻质量差",
            "trainings": [
                {"name": "快速转换训练", "scenario": "攻防转换", "zone": "全场", "duration": "25min",
                 "focus": "夺回球权后快速向前推进的效率"},
                {"name": "2v1反击", "scenario": "2v1", "zone": "中场→进攻三区", "duration": "15min",
                 "focus": "反击中的人数优势把握和最后一传"},
            ]
        }
    },
    "定位球防守差": {
        "overall": {
            "description": "角球/任意球失球多，定位球防守体系有问题",
            "trainings": [
                {"name": "角球防守站位", "scenario": "角球防守", "zone": "禁区", "duration": "20min",
                 "focus": "区域+盯人混合防守体系演练"},
                {"name": "定位球防守演练", "scenario": "定位球防守", "zone": "禁区", "duration": "15min",
                 "focus": "前点/后点/弧顶的防守职责分配"},
            ]
        }
    },
    "传中质量低": {
        "overall": {
            "description": "传中成功率低于25%，落点控制差",
            "trainings": [
                {"name": "传中精度训练", "scenario": "边路进攻", "zone": "边路→禁区", "duration": "15min",
                 "focus": "不同位置的传中脚法和落点控制"},
                {"name": "半空间传中", "scenario": "半空间进攻", "zone": "半空间", "duration": "15min",
                 "focus": "从半空间内切的倒三角传中"},
            ]
        }
    },
    "横向转移少": {
        "overall": {
            "description": "大范围转移球少，进攻缺少宽度利用",
            "trainings": [
                {"name": "大范围转移训练", "scenario": "推进配合", "zone": "中场", "duration": "20min",
                 "focus": "长距离横向转移球的时机和精度"},
                {"name": "弱侧切换配合", "scenario": "边路进攻", "zone": "边路→对侧边路", "duration": "15min",
                 "focus": "强侧吸引后快速转移到弱侧的套路"},
            ]
        }
    },
}


# ============================================================
# 场地区域定义（StatsBomb标准 120×80）
# ============================================================
ZONE_DEFINITIONS = {
    "后场": {"x_range": (0, 40), "desc": "防守三区，本方球门到中线前"},
    "中场": {"x_range": (40, 80), "desc": "中场三区，比赛核心区域"},
    "进攻三区": {"x_range": (80, 120), "desc": "对方防守三区，创造机会的关键区域"},
    "左路": {"y_range": (0, 27), "desc": "球场左侧通道"},
    "中路": {"y_range": (27, 53), "desc": "球场中央通道"},
    "右路": {"y_range": (53, 80), "desc": "球场右侧通道"},
    "左半空间": {"y_range": (27, 40), "desc": "左路与中路之间的半空间"},
    "右半空间": {"y_range": (40, 53), "desc": "右路与中路之间的半空间"},
    "禁区": {"x_range": (102, 120), "y_range": (18, 62), "desc": "射门最高概率区域"},
}


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
                    first_tactic = json.loads(str(tactics_rows.iloc[0]['tactics']))
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

        # === 传中 ===
        crosses = passes[passes['pass_type'] == 'Cross'] if 'pass_type' in passes.columns else pd.DataFrame()
        cross_completed = crosses[crosses['pass_outcome'].isna()] if not crosses.empty else pd.DataFrame()
        cross_accuracy = len(cross_completed) / len(crosses) * 100 if len(crosses) > 0 else 0

        # === 对抗 (Duels) ===
        duels = t_df[t_df['type'] == 'Duel']
        duels_won = duels[duels['duel_outcome'] == 'Won'] if 'duel_outcome' in duels.columns else pd.DataFrame()
        duel_success_rate = len(duels_won) / len(duels) * 100 if len(duels) > 0 else 0

        # 进攻对抗 / 防守对抗
        offensive_duels = duels[duels.get('duel_type', pd.Series(dtype=str)) == 'Offensive'] if 'duel_type' in duels.columns else pd.DataFrame()
        defensive_duels = duels[duels.get('duel_type', pd.Series(dtype=str)) == 'Defensive'] if 'duel_type' in duels.columns else pd.DataFrame()
        offensive_duel_success = len(offensive_duels[offensive_duels['duel_outcome'] == 'Won']) / len(offensive_duels) * 100 if len(offensive_duels) > 0 else 0
        defensive_duel_success = len(defensive_duels[defensive_duels['duel_outcome'] == 'Won']) / len(defensive_duels) * 100 if len(defensive_duels) > 0 else 0

        # 高空对抗
        aerial_duels = duels[duels.get('duel_type', pd.Series(dtype=str)) == 'Aerial'] if 'duel_type' in duels.columns else pd.DataFrame()
        aerial_success = len(aerial_duels[aerial_duels['duel_outcome'] == 'Won']) / len(aerial_duels) * 100 if len(aerial_duels) > 0 else 0

        # === 反抢 (Counter-press) ===
        # 定义：丢球后5秒内夺回球权
        pressures = t_df[t_df['type'] == 'Pressure']
        high_pressures = pressures[pressures['x'] > 60] if 'x' in pressures.columns else pd.DataFrame()
        counter_press_success = 0
        if 'counterpress' in t_df.columns:
            cp_events = t_df[t_df['counterpress'] == True]
            counter_press_success = len(cp_events[cp_events['type'].isin(['Ball Recovery', 'Pressure'])])

        # === 球权丢失位置分析 ===
        turnovers = t_df[t_df['type'].isin(['Pass', 'Shot', 'Duel', 'Bad Touch'])]
        if 'x' in turnovers.columns and turnovers['x'].notna().any():
            turnover_x_mean = turnovers['x'].mean()
            # 后场丢失（x < 40）
            turnover_own_third = len(turnovers[turnovers['x'] < 40])
            turnover_mid_third = len(turnovers[(turnovers['x'] >= 40) & (turnovers['x'] < 80)])
            turnover_final_third = len(turnovers[turnovers['x'] >= 80])
        else:
            turnover_x_mean = 60
            turnover_own_third = turnover_mid_third = turnover_final_third = 0

        # === 球权夺回位置分析 ===
        recoveries = t_df[t_df['type'] == 'Ball Recovery']
        if 'x' in recoveries.columns and recoveries['x'].notna().any():
            recovery_own_third = len(recoveries[recoveries['x'] < 40])
            recovery_mid_third = len(recoveries[(recoveries['x'] >= 40) & (recoveries['x'] < 80)])
            recovery_final_third = len(recoveries[recoveries['x'] >= 80])
            high_recoveries = recovery_final_third
        else:
            recovery_own_third = recovery_mid_third = recovery_final_third = 0
            high_recoveries = 0

        # === 大机会 (Big Chances) 估算 ===
        # 简化版：xG > 0.3 的射门视为大机会
        if 'shot_statsbomb_xg' in shots.columns:
            big_chances_taken = len(shots[shots['shot_statsbomb_xg'] > 0.3])
            big_chances_goals = len(shots[(shots['shot_statsbomb_xg'] > 0.3) & (shots['shot_outcome'] == 'Goal')])
        else:
            big_chances_taken = 0
            big_chances_goals = 0

        # === 射门技术分布 ===
        shot_techniques = {}
        if 'shot_technique' in shots.columns:
            for tech in shots['shot_technique'].dropna().unique():
                shot_techniques[tech] = len(shots[shots['shot_technique'] == tech])

        # === 射门身体部位 ===
        shot_body_parts = {}
        if 'shot_body_part' in shots.columns:
            for bp in shots['shot_body_part'].dropna().unique():
                shot_body_parts[bp] = len(shots[shots['shot_body_part'] == bp])

        # === 压迫事件统计 ===
        pressures_total = len(pressures)
        pressures_high = len(high_pressures)

        # === 推进规则指标 ===
        if _HAS_PROGRESSION:
            try:
                prog_result = apply_all_rules(df, team)
                prog_summary = prog_result['summary']
                progressive_passes = prog_summary['progressive_passes']
                passes_into_final_third = prog_summary['passes_into_final_third']
                passes_into_box = prog_summary['passes_into_box']
                deep_progressions = prog_summary['deep_progressions']
                switches_of_play = prog_summary['switches_of_play']
                progressive_carries = prog_summary['progressive_carries']
                ppda = prog_summary.get('ppda')
                prog_sequences_count = prog_summary['progressive_sequences']
                weak_zones = prog_summary.get('defensive_weak_zones', [])
                through_balls = prog_summary.get('through_balls', 0)
            except Exception as e:
                print(f"[推进指标] {team}计算异常：{e}")
                progressive_passes = passes_into_final_third = passes_into_box = 0
                deep_progressions = switches_of_play = progressive_carries = 0
                ppda = None
                prog_sequences_count = 0
                weak_zones = []
                through_balls = 0
        else:
            progressive_passes = passes_into_final_third = passes_into_box = 0
            deep_progressions = switches_of_play = progressive_carries = 0
            ppda = None
            prog_sequences_count = 0
            weak_zones = []
            through_balls = 0

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
            # 推进规则指标
            'progressive_passes': progressive_passes,
            'passes_into_final_third': passes_into_final_third,
            'passes_into_box': passes_into_box,
            'deep_progressions': deep_progressions,
            'switches_of_play': switches_of_play,
            'progressive_carries': progressive_carries,
            'ppda': ppda,
            'progressive_sequences': prog_sequences_count,
            'defensive_weak_zones': weak_zones,
            'through_balls': through_balls,
            # v2 新增指标
            'crosses_total': len(crosses),
            'crosses_completed': len(cross_completed),
            'cross_accuracy': cross_accuracy,
            'duels_total': len(duels),
            'duels_won': len(duels_won),
            'duel_success_rate': duel_success_rate,
            'offensive_duel_success': offensive_duel_success,
            'defensive_duel_success': defensive_duel_success,
            'aerial_duels_total': len(aerial_duels),
            'aerial_success': aerial_success,
            'counter_press_actions': counter_press_success,
            'pressures_total': pressures_total,
            'pressures_high': pressures_high,
            'turnover_x_mean': turnover_x_mean,
            'turnover_own_third': turnover_own_third,
            'turnover_mid_third': turnover_mid_third,
            'turnover_final_third': turnover_final_third,
            'recovery_own_third': recovery_own_third,
            'recovery_mid_third': recovery_mid_third,
            'recovery_final_third': recovery_final_third,
            'high_recoveries': high_recoveries,
            'big_chances_taken': big_chances_taken,
            'big_chances_goals': big_chances_goals,
            'shot_techniques': shot_techniques,
            'shot_body_parts': shot_body_parts,
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
    
    # === 推进能力对比 ===
    for team in teams:
        s = stats[team]
        if s.get('progressive_passes', 0) > 0 and len(teams) == 2:
            other = [t for t in teams if t != team][0]
            s_other = stats[other]
            diff = s['progressive_passes'] - s_other.get('progressive_passes', 0)
            if abs(diff) >= 5:
                dominant = team if diff > 0 else other
                dom_s = stats[dominant]
                ins_suggestion = f"{dominant}推进能力强，建议对手注意中场拦截"
                insights.append({
                    "category": "推进能力",
                    "text": f"{dominant}推进传球{dom_s['progressive_passes']}次，远超对手{stats[[t for t in teams if t != dominant][0]].get('progressive_passes', 0)}次，球权向前的能力突出",
                    "priority": 2,
                    "suggestion": ins_suggestion
                })
                break  # 只报一次

    # === PPDA压迫强度 ===
    for team in teams:
        s = stats[team]
        if s.get('ppda') is not None:
            if s['ppda'] < 9:
                insights.append({
                    "category": "压迫强度",
                    "text": f"{team}的PPDA={s['ppda']:.1f}，高位压迫凶狠（顶级压迫水平）",
                    "priority": 1,
                    "suggestion": "对手应利用快速出球和长传破解压迫"
                })
            elif s['ppda'] > 16:
                insights.append({
                    "category": "压迫强度",
                    "text": f"{team}的PPDA={s['ppda']:.1f}，压迫消极，偏向低位防守",
                    "priority": 2,
                    "suggestion": "对手可在中场从容组织"
                })

    # === 防守薄弱区域 ===
    for team in teams:
        s = stats[team]
        weak_zones = s.get('defensive_weak_zones', [])
        if weak_zones:
            top_zone = weak_zones[0]
            insights.append({
                "category": "防守薄弱",
                "text": f"{team}防守薄弱区域：{top_zone['description']}，对手多次在该区域完成推进",
                "priority": 1,
                "suggestion": f"建议加强区域({top_zone['center_x']:.0f},{top_zone['center_y']:.0f})附近的防守覆盖"
            })
    
    # === v2 新增洞察：传中质量 ===
    for team in teams:
        s = stats[team]
        if s.get('crosses_total', 0) >= 5:
            ca = s.get('cross_accuracy', 0)
            if ca < 25:
                insights.append({
                    "category": "传中质量",
                    "text": f"{team}传中{s['crosses_total']}次，成功率仅{ca:.0f}%，落点控制差",
                    "priority": 2,
                    "suggestion": "建议分析传中位置分布和目标区域，训练传中精度",
                    "training_key": "传中质量低",
                })

    # === v2 新增洞察：对抗能力 ===
    for team in teams:
        s = stats[team]
        if s.get('duels_total', 0) > 20:
            dsr = s.get('duel_success_rate', 50)
            if dsr < 40:
                insights.append({
                    "category": "对抗能力",
                    "text": f"{team}对抗成功率{dsr:.0f}%，整体对抗处于劣势",
                    "priority": 2,
                    "suggestion": "区分进攻/防守/高空对抗，针对性训练",
                    "training_key": "1v1防守差",
                })

    # === v2 新增洞察：反抢能力 ===
    for team in teams:
        s = stats[team]
        cp = s.get('counter_press_actions', 0)
        if cp == 0 and s.get('pressures_total', 0) > 30:
            insights.append({
                "category": "反抢能力",
                "text": f"{team}压迫次数{s['pressures_total']}次但反抢转化极少，反抢效率低",
                "priority": 2,
                "suggestion": "压迫不等于反抢，需训练压迫后的协同围抢",
                "training_key": "反抢能力弱",
            })

    # === v2 新增洞察：球权流动 ===
    for team in teams:
        s = stats[team]
        tft = s.get('turnover_final_third', 0)
        rft = s.get('recovery_final_third', 0)
        total_events = s.get('total_events', 1)
        # 前场丢球占比高 → 高位打法但效率低
        if tft / max(total_events * 0.1, 1) > 0.5:
            insights.append({
                "category": "球权流动",
                "text": f"{team}前场丢失球权{tft}次，高位进攻风险大",
                "priority": 2,
                "suggestion": "检查前场传球选择，是否过多冒险传球",
            })
        # 前场夺回多 → 高位压迫有效
        if rft > 5:
            insights.append({
                "category": "球权流动",
                "text": f"{team}前场夺回球权{rft}次，高位压迫转化好",
                "priority": 2,
                "suggestion": "前场反抢成功→快速射门，训练转换效率",
                "training_key": "反击效率低",
            })

    # === v2 新增洞察：大机会把握 ===
    for team in teams:
        s = stats[team]
        bc_taken = s.get('big_chances_taken', 0)
        bc_goals = s.get('big_chances_goals', 0)
        if bc_taken >= 3:
            bc_rate = bc_goals / bc_taken * 100
            if bc_rate < 40:
                insights.append({
                    "category": "大机会把握",
                    "text": f"{team}获得{bc_taken}次大机会仅把握{bc_goals}个（{bc_rate:.0f}%），终结效率极低",
                    "priority": 1,
                    "suggestion": "大机会不进最伤士气，需专项训练禁区终结",
                    "training_key": "终结效率低",
                })

    # === v2 新增洞察：横向转移 ===
    for team in teams:
        s = stats[team]
        sw = s.get('switches_of_play', 0)
        if sw <= 1 and s.get('passes_total', 0) > 200:
            insights.append({
                "category": "横向转移",
                "text": f"{team}仅{sw}次大范围转移，进攻宽度利用不足",
                "priority": 2,
                "suggestion": "进攻过于集中在中路，容易被对手收缩防守",
                "training_key": "横向转移少",
            })

    # === 为每条insight自动附加训练映射 ===
    for ins in insights:
        tk = ins.get('training_key', '')
        if tk and tk in TRAINING_MAPPING:
            mapping = TRAINING_MAPPING[tk]
            ins['training_recommendations'] = mapping.get('overall', {}).get('trainings', [])
            ins['training_description'] = mapping.get('overall', {}).get('description', '')

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


def get_training_plan(insights, max_exercises=4):
    """从insights中提取训练计划，按优先级排序，去重
    
    返回：
        plan: [{"name", "scenario", "zone", "duration", "focus", "triggered_by"}, ...]
    """
    seen = set()
    plan = []
    
    for ins in sorted(insights, key=lambda x: x.get('priority', 3)):
        recs = ins.get('training_recommendations', [])
        for rec in recs:
            name = rec.get('name', '')
            if name not in seen and len(plan) < max_exercises:
                seen.add(name)
                plan.append({
                    **rec,
                    'triggered_by': ins.get('text', ''),
                    'category': ins.get('category', ''),
                })
    
    return plan
