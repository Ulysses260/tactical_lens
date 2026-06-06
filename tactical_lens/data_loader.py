"""
data_loader.py — 数据加载模块
支持：StatsBomb CSV、Catapult CSV、自定义CSV
"""
import json
import os
import pandas as pd


def parse_location(loc_str):
    """解析StatsBomb的位置字符串 [x, y] → (x, y)"""
    if pd.isna(loc_str):
        return None, None
    try:
        coords = json.loads(str(loc_str))
        return coords[0], coords[1]
    except:
        return None, None


def load_statsbomb_csv(filepath, match_name="自定义比赛"):
    """加载StatsBomb格式CSV，返回(df, info)"""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到文件：{filepath}")
    
    df = pd.read_csv(filepath)
    
    coord_mappings = {
        'location': ('x', 'y'),
        'pass_end_location': ('pass_end_x', 'pass_end_y'),
        'carry_end_location': ('carry_end_x', 'carry_end_y'),
    }
    for col, (x_name, y_name) in coord_mappings.items():
        if col in df.columns:
            locs = df[col].apply(parse_location)
            df[x_name] = [l[0] for l in locs]
            df[y_name] = [l[1] for l in locs]
    
    teams = df['team'].dropna().unique().tolist()
    info = {"name": match_name, "teams": teams, "source": "statsbomb", "file": filepath}
    print(f"[数据加载] {match_name}：{len(df)}条事件，{len(teams)}支队伍")
    return df, info


def load_catapult_csv(filepath, match_name="Catapult比赛"):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到文件：{filepath}")
    
    raw = pd.read_csv(filepath)
    df = raw.copy()
    
    info = {"name": match_name, "source": "catapult", "file": filepath, "raw_columns": list(raw.columns)}
    print(f"[数据加载] {match_name}（Catapult）：{len(df)}行，字段：{list(raw.columns)[:10]}...")
    return df, info


def load_custom_csv(filepath, match_name="自定义比赛", team_col="team", event_col="type"):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到文件：{filepath}")
    
    df = pd.read_csv(filepath)
    
    if 'location' in df.columns:
        locs = df['location'].apply(parse_location)
        df['x'] = [l[0] for l in locs]
        df['y'] = [l[1] for l in locs]
    
    teams = df[team_col].dropna().unique().tolist() if team_col in df.columns else []
    info = {"name": match_name, "teams": teams, "source": "custom", "file": filepath}
    print(f"[数据加载] {match_name}（自定义）：{len(df)}行")
    return df, info


def auto_load(filepath, match_name=None):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到文件：{filepath}")
    
    df = pd.read_csv(filepath, nrows=5)
    columns = set(df.columns)
    
    statsbomb_cols = {'type', 'team', 'location', 'possession_team'}
    if statsbomb_cols.issubset(columns):
        if match_name is None:
            match_name = os.path.basename(filepath).replace('.csv', '')
        return load_statsbomb_csv(filepath, match_name)
    
    catapult_keywords = {'距离', '高强度', 'RHIE', '跑动', '冲刺'}
    if any(kw in ''.join(columns) for kw in catapult_keywords):
        if match_name is None:
            match_name = os.path.basename(filepath).replace('.csv', '')
        return load_catapult_csv(filepath, match_name)
    
    if match_name is None:
        match_name = os.path.basename(filepath).replace('.csv', '')
    return load_custom_csv(filepath, match_name)
