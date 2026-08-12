"""
data_loader.py — 数据加载模块（v3）
支持：StatsBomb CSV、Catapult CSV、FIFA单文件、自定义CSV
v3新增：FIFA单文件自动识别 + 目录批量加载
"""
import json
import os
import glob
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
    
    # 解析坐标字段
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
    """加载Catapult导出的CSV"""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到文件：{filepath}")
    
    raw = pd.read_csv(filepath)
    df = raw.copy()
    
    info = {"name": match_name, "source": "catapult", "file": filepath, "raw_columns": list(raw.columns)}
    print(f"[数据加载] {match_name}（Catapult）：{len(df)}行，字段：{list(raw.columns)[:10]}...")
    return df, info


def load_custom_csv(filepath, match_name="自定义比赛", team_col="team", event_col="type"):
    """加载自定义格式CSV"""
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


def _is_statsbomb_file(filepath):
    """判断文件是否为StatsBomb格式"""
    try:
        df = pd.read_csv(filepath, nrows=5)
        cols = set(df.columns)
        return {'type', 'team', 'location', 'possession_team'}.issubset(cols)
    except Exception:
        return False


def _is_catapult_file(filepath):
    """判断文件是否为Catapult格式"""
    try:
        df = pd.read_csv(filepath, nrows=5)
        cols = set(df.columns)
        keywords = {'距离', '高强度', 'RHIE', '跑动', '冲刺'}
        return any(kw in ''.join(cols) for kw in keywords)
    except Exception:
        return False


def _is_fifa_single_file(filepath):
    """判断文件是否为FIFA单文件格式（通过列名特征识别）"""
    try:
        from fifa_adapter import detect_fifa_single_file_type
        ftype = detect_fifa_single_file_type(filepath)
        return ftype != 'unknown'
    except Exception:
        return False


# ========== 自动识别格式（v3：增加FIFA单文件识别）==========
def auto_load(filepath, match_name=None):
    """自动识别CSV格式并加载
    
    识别优先级：StatsBomb → FIFA单文件 → Catapult → 自定义CSV兜底
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到文件：{filepath}")
    
    if match_name is None:
        match_name = os.path.basename(filepath).replace('.csv', '')
    
    # 1. StatsBomb
    if _is_statsbomb_file(filepath):
        print(f"  → 识别为 StatsBomb 格式")
        return load_statsbomb_csv(filepath, match_name)
    
    # 2. FIFA 单文件
    if _is_fifa_single_file(filepath):
        from fifa_adapter import convert_fifa_single_file, detect_fifa_single_file_type
        ftype = detect_fifa_single_file_type(filepath)
        print(f"  → 识别为 FIFA 单文件（{ftype}）")
        return convert_fifa_single_file(filepath, match_name)
    
    # 3. Catapult
    if _is_catapult_file(filepath):
        print(f"  → 识别为 Catapult 格式")
        return load_catapult_csv(filepath, match_name)
    
    # 4. 自定义CSV兜底
    print(f"  → 识别为自定义格式")
    return load_custom_csv(filepath, match_name)


# ========== 目录批量加载 ==========
def load_fifa_directory(dirpath):
    """加载一个目录下所有FIFA CSV文件，合并为统一格式
    
    适用于用户上传了多个FIFA文件（如03_key_stats + 05_attempts_at_goal + ...）
    会自动识别每个文件类型并合并stats
    """
    if not os.path.isdir(dirpath):
        raise NotADirectoryError(f"不是目录：{dirpath}")
    
    csv_files = sorted(glob.glob(os.path.join(dirpath, '*.csv')))
    if not csv_files:
        raise FileNotFoundError(f"目录中没有CSV文件：{dirpath}")
    
    print(f"[FIFA目录加载] 发现 {len(csv_files)} 个CSV文件")
    
    all_stats = {}
    all_dfs = []
    combined_info = {
        'name': os.path.basename(dirpath),
        'teams': [],
        'source': 'fifa_directory',
        'files_loaded': [],
        'fifa_single_data': True,
    }
    
    for csv_file in csv_files:
        fname = os.path.basename(csv_file)
        try:
            from fifa_adapter import detect_fifa_single_file_type, convert_fifa_single_file
            ftype = detect_fifa_single_file_type(csv_file)
            if ftype == 'unknown':
                print(f"  ⚠ 跳过未识别文件：{fname}")
                continue
            
            df, info = convert_fifa_single_file(csv_file)
            combined_info['files_loaded'].append({
                'file': fname,
                'type': ftype,
            })
            
            # 合并teams
            for t in info.get('teams', []):
                if t not in combined_info['teams']:
                    combined_info['teams'].append(t)
            
            # 合并stats
            if 'fifa_stats' in info:
                for team, team_stats in info['fifa_stats'].items():
                    if team not in all_stats:
                        from fifa_adapter import _init_stats
                        all_stats[team] = _init_stats([team])[team]
                    
                    # 合并数值字段
                    s = all_stats[team]
                    ts = team_stats
                    merge_keys = [
                        'shots_total', 'shots_on_target', 'shots_off_target',
                        'goals', 'fouls', 'corners', 'key_passes', 'assists',
                        'passes_total', 'passes_completed',
                        'crosses_total', 'crosses_completed',
                        'duels_total', 'duels_won',
                        'pressures_total', 'total_events',
                        'progressive_passes', 'passes_into_final_third',
                        'switches_of_play', 'progressive_carries',
                    ]
                    for key in merge_keys:
                        if key in ts:
                            s[key] = s.get(key, 0) + ts.get(key, 0)
                    
                    # xG取最大值
                    if 'xg' in ts:
                        s['xg'] = max(s.get('xg', 0), ts['xg'])
                    
                    # 控球率取最新文件的值
                    if ts.get('possession_pct', 50) != 50:
                        s['possession_pct'] = ts['possession_pct']
                    
                    # 重新计算百分比指标
                    if s['passes_total'] > 0:
                        s['pass_accuracy'] = s['passes_completed'] / s['passes_total'] * 100
                    if s['crosses_total'] > 0:
                        s['cross_accuracy'] = s['crosses_completed'] / s['crosses_total'] * 100
                    if s['duels_total'] > 0:
                        s['duel_success_rate'] = s['duels_won'] / s['duels_total'] * 100
            
            if not df.empty:
                all_dfs.append(df)
            
            print(f"  ✓ {ftype}: {fname}")
        except Exception as e:
            print(f"  ✗ 加载失败 {fname}: {e}")
    
    combined_info['fifa_stats'] = all_stats
    
    # 合并DataFrame
    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
    else:
        combined_df = pd.DataFrame()
    
    loaded_types = [f['type'] for f in combined_info['files_loaded']]
    print(f"\n[FIFA目录加载] 完成：{len(combined_info['files_loaded'])}/{len(csv_files)} 文件成功")
    print(f"  已加载类型：{', '.join(loaded_types)}")
    
    return combined_df, combined_info


def is_fifa_csv_dir(dirpath):
    """检查目录是否包含FIFA CSV文件"""
    if not os.path.isdir(dirpath):
        return False
    csv_files = glob.glob(os.path.join(dirpath, '*.csv'))
    for f in csv_files:
        if _is_fifa_single_file(f):
            return True
    return False
