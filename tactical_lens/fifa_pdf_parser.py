"""
fifa_pdf_parser.py — FIFA比赛报告PDF解析器（纯函数版）

将FIFA Training Centre比赛报告PDF解析为12个CSV文件，供战术透镜平台使用。
无Streamlit依赖，无CodeAct SDK依赖，仅依赖pdfplumber。

用法:
    from fifa_pdf_parser import parse_fifa_pdf
    result = parse_fifa_pdf(pdf_path, output_dir)
    if result['success']:
        print(result['files'])

输出CSV文件列表:
  - 01_match_info.csv          比赛基本信息
  - 02_lineups.csv             阵容（首发+替补）
  - 03_key_stats.csv           关键统计
  - 04_phases_of_play.csv      比赛阶段占比
  - 05_attempts_at_goal.csv    射门明细
  - 06_crosses.csv             传中数据
  - 07_offers_to_receive.csv   要球/跑动接应数据
  - 08_in_possession_distributions.csv  个人持球数据（传球/过人/传中）
  - 09_in_possession_offers.csv         个人持球数据（接应跑动类型）
  - 10_out_of_possession.csv   个人防守数据
  - 11_physical_data.csv       跑动数据
  - 12_passing_network.csv     传球网络矩阵
"""

import csv
import os
import re
from typing import List, Dict, Tuple, Optional

# ============================================================
# 常量定义
# ============================================================

# 跑动数据PUA字体编码映射: U+E071=0, U+E072=1, ..., U+E07A=9
PHYSICAL_FONT_MAP = {
    '\ue071': '0', '\ue072': '1', '\ue073': '2', '\ue074': '3',
    '\ue075': '4', '\ue076': '5', '\ue077': '6', '\ue078': '7',
    '\ue079': '8', '\ue07a': '9', '\ue094': '.',
}

# 其他特殊字符映射
SPECIAL_CHAR_MAP = {
    '\x00': 'ff',  # ligature
    '\ue088': '-',  # en dash in zone labels
    '\ue092': ':',  # colon-like
    '\ue09d': '+',  # plus sign
    '\ue081': '(',  # left paren
    '\ue082': ')',  # right paren
}


# ============================================================
# 辅助函数
# ============================================================

def clean_text(text: str) -> str:
    """清理PDF提取的文本，替换特殊字符"""
    if not text:
        return ''
    result = text
    for char, replacement in SPECIAL_CHAR_MAP.items():
        result = result.replace(char, replacement)
    return result.strip()


def decode_physical_number(text: str) -> Optional[float]:
    """解码跑动数据中的PUA编码数字"""
    if not text:
        return None
    decoded = ''
    for ch in text:
        if ch in PHYSICAL_FONT_MAP:
            decoded += PHYSICAL_FONT_MAP[ch]
        elif ch.isdigit() or ch == '.':
            decoded += ch
    if not decoded:
        return None
    try:
        return float(decoded)
    except ValueError:
        return None


def write_csv(filepath: str, headers: List[str], rows: List[List], encoding: str = 'utf-8-sig') -> int:
    """写入CSV文件，返回写入的行数"""
    dir_path = os.path.dirname(filepath)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    with open(filepath, 'w', newline='', encoding=encoding) as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
    return len(rows)


def extract_page_lines(pdf, page_num: int) -> List[str]:
    """提取指定页的文本行（1-indexed）"""
    page = pdf.pages[page_num - 1]
    text = page.extract_text() or ''
    return [clean_text(line) for line in text.split('\n') if clean_text(line)]


def get_page_text(pdf, page_num: int) -> str:
    """获取指定页的完整文本"""
    page = pdf.pages[page_num - 1]
    return clean_text(page.extract_text() or '')


# ============================================================
# 1. 比赛基本信息
# ============================================================

def parse_match_info(pdf) -> Tuple[List[str], List]:
    """解析比赛基本信息（第1-2页）"""
    headers = ['field', 'value']
    rows = []

    # 第1页
    lines = extract_page_lines(pdf, 1)

    # 比分和对阵
    score_line = ''
    for line in lines:
        if re.match(r'^.+\s+\d+\s*-\s*\d+\s+.+$', line):
            score_line = line
            break

    if score_line:
        match = re.match(r'^(.+?)\s+(\d+)\s*-\s*(\d+)\s+(.+)$', score_line)
        if match:
            home_team = match.group(1).strip()
            away_team = match.group(4).strip()
            home_score = int(match.group(2))
            away_score = int(match.group(3))
            rows.append(['home_team', home_team])
            rows.append(['away_team', away_team])
            rows.append(['home_score', home_score])
            rows.append(['away_score', away_score])

    # 轮次
    for line in lines:
        if 'Round of' in line or 'Match' in line:
            rows.append(['match_round', line.strip()])
            break

    # 日期
    for line in lines:
        if re.match(r'^\d{1,2}\s+\w+\s+\d{4}', line):
            rows.append(['match_date', line.strip()])
            break

    # 开球时间
    for line in lines:
        if 'Kick' in line:
            rows.append(['kickoff_time', line.strip()])
            break

    # 球场
    for line in lines:
        if 'Stadium' in line and 'Kick' not in line:
            rows.append(['stadium', line.strip()])
            break

    # 报告类型
    for line in lines:
        if 'REPORT' in line.upper():
            rows.append(['report_type', line.strip()])
            break

    return headers, rows


# ============================================================
# 2. 阵容解析
# ============================================================

def parse_lineups(pdf) -> Tuple[List[str], List]:
    """解析阵容（第2页）"""
    headers = ['team', 'role', 'shirt_number', 'position', 'player_name', 'substitution_time', 'notes']
    rows = []

    lines = extract_page_lines(pdf, 2)

    # 获取队名
    home_team = ''
    away_team = ''
    for i, line in enumerate(lines):
        if 'STARTING STARTING' in line:
            for j in range(max(0, i-5), i):
                l = lines[j]
                words = l.split()
                if len(words) == 2 and words[0][0].isupper() and words[1][0].isupper():
                    home_team = words[0]
                    away_team = words[1]
                    break
            break

    if not home_team or not away_team:
        # 从关键统计页获取队名
        key_stats_lines = extract_page_lines(pdf, 3)
        for line in key_stats_lines:
            if 'Goals' in line and len(line.split()) >= 3:
                idx = key_stats_lines.index(line)
                if idx > 0:
                    team_line = key_stats_lines[idx - 1]
                    teams = team_line.split()
                    if len(teams) >= 2:
                        home_team = teams[0]
                        away_team = teams[-1]
                break

    # 找到STARTING行和SUBSTITUTES行
    starting_idx = -1
    substitutes_idx = -1
    for i, line in enumerate(lines):
        if 'STARTING' in line:
            starting_idx = i
        if 'SUBSTITUTES' in line.upper() or 'SUBSTITUTE' in line.upper():
            if substitutes_idx == -1:
                substitutes_idx = i

    in_starting = False
    in_substitutes = False

    for i, line in enumerate(lines):
        if i == starting_idx:
            in_starting = True
            in_substitutes = False
            continue
        if i == substitutes_idx:
            in_starting = False
            in_substitutes = True
            continue

        if not in_starting and not in_substitutes:
            continue

        stripped = line.strip()
        
        # 跳过非球员行
        if not re.match(r'^\d+', stripped):
            continue
        if stripped.startswith('Total') or stripped.startswith('Attempt') or stripped.startswith('Distribution'):
            continue

        # 尝试解析左边球员（主队）
        left_match = re.match(r'^(\d+)\s+(GK|DF|MF|FW)\s+([A-Z][a-z]+\s+[A-Z]+)', stripped)
        if left_match:
            num = left_match.group(1)
            pos = left_match.group(2)
            name = left_match.group(3).strip()

            # 检查是否有替换时间
            sub_time = ''
            rest = stripped[left_match.end():]
            sub_match = re.search(r'(F|M|O)\s*(\d+\'?)', rest[:20])
            if sub_match:
                sub_time = f"{sub_match.group(1)} {sub_match.group(2)}"

            role = 'starting' if in_starting else 'substitute'
            rows.append([home_team, role, num, pos, name, sub_time, ''])

        # 尝试解析右边球员（客队）
        right_match = re.search(r'([A-Z][a-z]+\s+[A-Z]+)\s+(GK|DF|MF|FW)\s+(\d+)\s*$', stripped)
        if right_match:
            name = right_match.group(1).strip()
            pos = right_match.group(2)
            num = right_match.group(3)

            # 检查替换时间
            sub_time = ''
            before_name = stripped[:right_match.start(1)]
            sub_match = re.search(r'(\d+\'?)\s*$', before_name[-20:])
            if sub_match:
                sub_time = sub_match.group(1)

            role = 'starting' if in_starting else 'substitute'
            rows.append([away_team, role, num, pos, name, sub_time, ''])

    return headers, rows


# ============================================================
# 3. 关键统计
# ============================================================

def parse_key_stats(pdf) -> Tuple[List[str], List]:
    """解析关键统计（第3页）"""
    headers = ['stat_category', 'stat_name', 'home_value', 'away_value']
    rows = []

    lines = extract_page_lines(pdf, 3)

    home_team = ''
    away_team = ''

    # 获取队名
    for i, line in enumerate(lines):
        if 'Goals' in line:
            if i > 0:
                teams = lines[i-1].split()
                if len(teams) >= 2:
                    home_team = teams[0]
                    away_team = teams[-1]
            break

    # 从行中提取统计数据
    in_possession_section = False
    for i, line in enumerate(lines):
        if 'Possession' in line and not line[0].isdigit():
            in_possession_section = True
            continue
        
        if in_possession_section and line.startswith('Total ') and '%' in line:
            percents = re.findall(r'([\d.]+%)', line)
            if len(percents) >= 2:
                rows.append(['Possession', 'Total Possession', percents[0], percents[-1]])
            in_possession_section = False
            continue
        
        if in_possession_section:
            continue

        # 跳过非数据行
        if not line or not line[0].isdigit():
            continue

        # 格式1: "0 Goals 3"
        match = re.match(r'^(\d+)\s+(.+?)\s+(\d+)\s*$', line)
        if match and '(' not in line:
            left_val = match.group(1)
            stat_name = match.group(2).strip()
            right_val = match.group(3)
            rows.append(['Key Stats', stat_name, left_val, right_val])
            continue

        # 格式2: "0.68 xG (Expected Goals) 0.85"
        match = re.match(r'^([\d.]+)\s+(.+?)\s+([\d.]+)\s*$', line)
        if match and 'km' not in line and '%' not in line:
            left_val = match.group(1)
            stat_name = match.group(2).strip()
            right_val = match.group(3)
            rows.append(['Key Stats', stat_name, left_val, right_val])
            continue

        # 格式3: "10 (3) Attempts at Goal (On Target) 5 (4)"
        match = re.match(r'^(\d+\s*\(\d+\))\s+(.+?)\s+(\d+\s*\(\d+\))\s*$', line)
        if match:
            left_val = match.group(1).replace(' ', '')
            stat_name = match.group(2).strip()
            right_val = match.group(3).replace(' ', '')
            rows.append(['Key Stats', stat_name, left_val, right_val])
            continue

        # 格式5: "77 % Pass Completion % 84 %"
        match = re.match(r'^(\d+)\s*%\s+(.+?)\s+(\d+)\s*%$', line)
        if match:
            left_val = f"{match.group(1)}%"
            stat_name = match.group(2).strip()
            stat_name = re.sub(r'%$', '', stat_name).strip()
            right_val = f"{match.group(3)}%"
            rows.append(['Key Stats', stat_name, left_val, right_val])
            continue

        # 格式6: "116.2 km Total Distance Covered 108.8 km"
        match = re.match(r'^([\d.]+)\s+km\s+(.+?)\s+([\d.]+)\s+km$', line)
        if match:
            left_val = f"{match.group(1)} km"
            stat_name = match.group(2).strip()
            right_val = f"{match.group(3)} km"
            rows.append(['Physical', stat_name, left_val, right_val])
            continue

    return headers, rows


# ============================================================
# 4. 比赛阶段占比
# ============================================================

def parse_phases_of_play(pdf) -> Tuple[List[str], List]:
    """解析比赛阶段占比（第4页）"""
    headers = ['phase_category', 'phase_name', 'home_pct', 'away_pct']
    rows = []

    lines = extract_page_lines(pdf, 4)

    home_team = ''
    away_team = ''

    # 第一行获取队名
    if lines:
        title_match = re.match(r'(.+?)\s+Phases of Play\s+(.+)', lines[0])
        if title_match:
            home_team = title_match.group(1).strip()
            away_team = title_match.group(2).strip()

    current_category = ''

    for line in lines[1:]:
        if 'IN POSSESSION' in line.upper():
            current_category = 'In Possession'
            continue
        if 'OUT OF POSSESSION' in line.upper():
            current_category = 'Out of Possession'
            continue

        # 格式: "24% Build Up Unopposed 41%"
        match = re.match(r'^(\d+%)\s+(.+?)\s+(\d+%)$', line)
        if match:
            home_pct = match.group(1)
            phase_name = match.group(2).strip()
            away_pct = match.group(3)
            rows.append([current_category, phase_name, home_pct, away_pct])

    return headers, rows


# ============================================================
# 5. 射门明细
# ============================================================

def parse_attempts_at_goal(pdf, team_a_page: int = 15, team_b_page: int = 17) -> Tuple[List[str], List]:
    """解析射门明细"""
    headers = ['team', 'time_min', 'shirt_number', 'player_name', 'outcome', 'body_part', 'delivery_type']
    rows = []

    for page_num in [team_a_page, team_b_page]:
        lines = extract_page_lines(pdf, page_num)

        # 从标题获取队名
        team_name = ''
        for line in lines:
            if 'Attempts at Goal' in line:
                parts = line.replace('Attempts at Goal', '').strip()
                if parts:
                    team_name = parts
                break

        # 找到表头行
        header_idx = -1
        for i, line in enumerate(lines):
            if 'Time' in line and 'Player' in line and 'Outcome' in line:
                header_idx = i
                break

        if header_idx == -1:
            continue

        # 解析数据行
        for line in lines[header_idx + 1:]:
            body_part_match = re.search(r'\s+(Left Foot|Right Foot|Head|Body)\s+(.+)$', line)
            if not body_part_match:
                continue

            body_part = body_part_match.group(1)
            delivery = body_part_match.group(2).strip()
            prefix = line[:body_part_match.start()].strip()

            time_match = re.match(r'^(\d+)\s+(\d+)\s*(.+)$', prefix)
            if not time_match:
                continue

            time_min = time_match.group(1)
            shirt_num = time_match.group(2)
            rest = time_match.group(3).strip()

            # 从后往前找结果关键词
            outcome_patterns = [
                r'(Deflected On Target - Saved)$',
                r'(On Target - Goal)$',
                r'(On Target - Saved)$',
                r'(Incomplete - Player On Ball Error)$',
                r'(Incomplete - Blocked)$',
                r'(Off Target)$',
                r'(Blocked)$',
            ]
            outcome = ''
            player_name = rest
            for pat in outcome_patterns:
                m = re.search(pat, rest)
                if m:
                    outcome = m.group(1)
                    player_name = rest[:m.start()].strip()
                    break

            if not outcome:
                words = rest.split()
                name_end = 0
                for j, w in enumerate(words):
                    if w[0].isupper() and j < len(words) - 1:
                        name_end = j + 1
                    else:
                        break
                player_name = ' '.join(words[:name_end])
                outcome = ' '.join(words[name_end:])

            rows.append([team_name, time_min, shirt_num, player_name, outcome, body_part, delivery])

    return headers, rows


# ============================================================
# 6. 传中数据
# ============================================================

def parse_crosses(pdf, team_a_page: int = 18, team_b_page: int = 19) -> Tuple[List[str], List]:
    """解析传中数据"""
    headers = ['team', 'shirt_number', 'player_name', 'inswing', 'outswing', 'driven', 'lofted', 'cutback', 'push_cross', 'total_attempted']
    rows = []

    for page_num in [team_a_page, team_b_page]:
        lines = extract_page_lines(pdf, page_num)

        team_name = ''
        for line in lines:
            if 'Crosses' in line:
                if 'Canada' in line:
                    team_name = 'Canada'
                elif 'Morocco' in line:
                    team_name = 'Morocco'
                break

        # 找到表头行
        header_idx = -1
        for i, line in enumerate(lines):
            if '# Player' in line and 'Inswing' in line:
                header_idx = i
                break

        if header_idx == -1:
            continue

        # 解析数据行
        for line in lines[header_idx + 1:]:
            match = re.match(r'^(\d+)\s+([A-Z][a-z]+\s+[A-Z]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$', line)
            if match:
                num = match.group(1)
                name = match.group(2).strip()
                vals = [match.group(i) for i in range(3, 10)]
                rows.append([team_name, num, name] + vals)

    return headers, rows


# ============================================================
# 7. Offers to Receive
# ============================================================

def parse_offers_to_receive(pdf, team_a_page: int = 20, team_b_page: int = 21) -> Tuple[List[str], List]:
    """解析Offering to Receive数据"""
    headers = ['team', 'shirt_number', 'player_name', 'offers_made', 'offers_received', 'offer_reception_pct']
    rows = []

    for page_num in [team_a_page, team_b_page]:
        lines = extract_page_lines(pdf, page_num)

        team_name = ''
        second_line = lines[1] if len(lines) > 1 else ''
        if 'Canada' in second_line:
            team_name = 'Canada'
        elif 'Morocco' in second_line:
            team_name = 'Morocco'

        # 找到表头行
        header_idx = -1
        for i, line in enumerate(lines):
            if '# Player' in line and 'Offers' in line and '%' in line:
                header_idx = i
                break

        if header_idx == -1:
            continue

        # 解析数据行
        for line in lines[header_idx + 1:]:
            match = re.match(r'^(\d+)\s+([A-Z][a-z]+\s+[A-Z]+)\s+(\d+)\s+(\d+)\s+([\d.]+%)$', line)
            if match:
                num = match.group(1)
                name = match.group(2).strip()
                made = match.group(3)
                received = match.group(4)
                pct = match.group(5)
                rows.append([team_name, num, name, made, received, pct])

    return headers, rows


# ============================================================
# 8. 个人持球数据 - Distributions
# ============================================================

def parse_in_possession_distributions(pdf, team_a_page: int = 42, team_b_page: int = 44) -> Tuple[List[str], List]:
    """解析个人持球数据-传球分布"""
    headers = [
        'team', 'shirt_number', 'player_name',
        'passes_attempted', 'passes_completed', 'pass_completion_pct',
        'switches_of_play', 'take_ons', 'step_ins',
        'crosses_attempted', 'crosses_completed', 'cross_completion_pct',
        'line_breaks_attempted', 'line_breaks_completed', 'line_break_goals',
        'ball_progressions', 'attempts_at_goal',
    ]
    rows = []

    for page_num in [team_a_page, team_b_page]:
        lines = extract_page_lines(pdf, page_num)

        team_name = ''
        for line in lines:
            if 'Canada' in line:
                team_name = 'Canada'
                break
            if 'Morocco' in line:
                team_name = 'Morocco'
                break

        # 找到数据起始行
        data_start = -1
        for i, line in enumerate(lines):
            if re.match(r'^\d+\s+[A-Z][a-z]+\s+[A-Z]+\s+\d+\s+\d+\s+\d+%', line):
                data_start = i
                break

        if data_start == -1:
            continue

        for line in lines[data_start:]:
            match = re.match(
                r'^(\d+)\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+%)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+%)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$',
                line
            )
            if match:
                num = match.group(1)
                name = match.group(2).strip()
                vals = [match.group(i) for i in range(3, 17)]
                rows.append([team_name, num, name] + vals)

    return headers, rows


# ============================================================
# 9. 个人持球数据 - Offers & Receptions
# ============================================================

def parse_in_possession_offers(pdf, team_a_page: int = 43, team_b_page: int = 45) -> Tuple[List[str], List]:
    """解析个人持球数据-接应跑动类型"""
    headers = [
        'team', 'shirt_number', 'player_name',
        'total_offers', 'in_front', 'in_between',
        'out_to_in', 'in_to_out', 'in_behind',
        'no_movement', 'offers_received',
    ]
    rows = []

    for page_num in [team_a_page, team_b_page]:
        lines = extract_page_lines(pdf, page_num)

        team_name = ''
        for line in lines:
            if 'Canada' in line:
                team_name = 'Canada'
                break
            if 'Morocco' in line:
                team_name = 'Morocco'
                break

        # 找到数据起始行
        data_start = -1
        for i, line in enumerate(lines):
            if re.match(r'^\d+\s+[A-Z][a-z]+\s+[A-Z]+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+', line):
                data_start = i
                break

        if data_start == -1:
            continue

        for line in lines[data_start:]:
            match = re.match(
                r'^(\d+)\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$',
                line
            )
            if match:
                num = match.group(1)
                name = match.group(2).strip()
                vals = [match.group(i) for i in range(3, 11)]
                rows.append([team_name, num, name] + vals)

    return headers, rows


# ============================================================
# 10. 个人防守数据
# ============================================================

def parse_out_of_possession(pdf, team_a_page: int = 47, team_b_page: int = 48) -> Tuple[List[str], List]:
    """解析个人防守数据"""
    headers = [
        'team', 'shirt_number', 'player_name',
        'tackles_made_won', 'blocks', 'interceptions',
        'pressing_direct', 'pressing_indirect',
        'duels_aerial_won', 'duels_physical_won',
        'loose_ball_receptions', 'pushing_on',
        'possession_contests', 'clearances',
        'pushing_into_pressing',
        'possession_regains', 'possession_interrupted',
    ]
    rows = []

    for page_num in [team_a_page, team_b_page]:
        lines = extract_page_lines(pdf, page_num)

        team_name = ''
        for line in lines:
            if 'Canada' in line:
                team_name = 'Canada'
                break
            if 'Morocco' in line:
                team_name = 'Morocco'
                break

        # 找到数据起始行
        data_start = -1
        for i, line in enumerate(lines):
            if re.match(r'^\d+\s+[A-Z][a-z]+', line) and ' / ' in line:
                if not any(h in line for h in ['Player', 'Blocks', 'Tackles']):
                    data_start = i
                    break

        if data_start == -1:
            continue

        for line in lines[data_start:]:
            # 按空格分割
            parts = line.split()
            if len(parts) < 10:
                continue

            # 第一个是号码
            if not parts[0].isdigit():
                continue

            shirt_num = parts[0]

            # 找到 "/" 的位置
            slash_idx = -1
            for j, p in enumerate(parts):
                if p == '/':
                    slash_idx = j
                    break

            if slash_idx < 3:
                continue

            player_name = ' '.join(parts[1:slash_idx - 1])
            tackle_val = f"{parts[slash_idx - 1]}/{parts[slash_idx + 1]}"
            num_vals = parts[slash_idx + 2:]

            if len(num_vals) < 13:
                continue
            num_vals = num_vals[:13]

            rows.append([team_name, shirt_num, player_name, tackle_val] + num_vals)

    return headers, rows


# ============================================================
# 11. 跑动数据（含PUA字体解码）
# ============================================================

def parse_physical_data(pdf, team_a_page: int = 50, team_b_page: int = 51) -> Tuple[List[str], List]:
    """解析跑动数据（含PUA字体解码）"""
    headers = [
        'team', 'shirt_number', 'player_name',
        'total_distance_m',
        'zone1_walk_m', 'zone2_jog_m', 'zone3_run_m',
        'zone4_low_sprint_m', 'zone5_high_sprint_m',
        'high_speed_runs_zone3', 'sprints_zone4_5',
        'top_speed_kmh',
    ]
    rows = []

    for page_num in [team_a_page, team_b_page]:
        page = pdf.pages[page_num - 1]
        chars = page.chars

        team_name = ''
        page_text = clean_text(page.extract_text() or '')
        if 'Canada' in page_text:
            team_name = 'Canada'
        elif 'Morocco' in page_text:
            team_name = 'Morocco'

        # 按y坐标分组字符
        chars_by_y = {}
        for c in chars:
            y = round(c['top'], 0)
            if y not in chars_by_y:
                chars_by_y[y] = []
            chars_by_y[y].append(c)

        sorted_ys = sorted(chars_by_y.keys())

        # 找到数据行（包含PUA数字的行）
        for y in sorted_ys:
            line_chars = sorted(chars_by_y[y], key=lambda x: x['x0'])
            line_text = ''.join(c['text'] for c in line_chars)

            # 检测是否为球员数据行（包含PUA数字）
            has_pua = any(ord(c) > 0xE000 for c in line_text)
            if not has_pua:
                continue

            # 解析号码和名字（正常ASCII字符）
            first_pua_idx = None
            for i, ch in enumerate(line_text):
                if ord(ch) > 0xE000:
                    first_pua_idx = i
                    break

            if first_pua_idx is None or first_pua_idx < 5:
                continue

            prefix = line_text[:first_pua_idx].strip()
            match = re.match(r'^(\d+)\s*(.+)$', prefix)
            if not match:
                continue

            shirt_num = match.group(1)
            player_name = match.group(2).strip()

            # 按x坐标聚类分列
            if len(line_chars) > first_pua_idx:
                data_chars = line_chars[first_pua_idx:]
            else:
                data_chars = []

            columns = []
            current_col = []
            last_x = None

            for c in data_chars:
                x1_val = c.get('x1', c['x0'] + c.get('width', 5))
                if last_x is not None and c['x0'] - last_x > 8:
                    if current_col:
                        columns.append(current_col)
                    current_col = [c]
                else:
                    current_col.append(c)
                last_x = x1_val

            if current_col:
                columns.append(current_col)

            # 解码每列
            values = []
            for col in columns:
                col_text = ''.join(c['text'] for c in col)
                decoded = decode_physical_number(col_text)
                values.append(decoded)

            # 期望9个数据列
            if len(values) != 9:
                # 尝试按小数点分割PUA文本
                pua_part = line_text[first_pua_idx:]
                decoded_str = ''
                for ch in pua_part:
                    if ch in PHYSICAL_FONT_MAP:
                        decoded_str += PHYSICAL_FONT_MAP[ch]
                    else:
                        decoded_str += ' '

                numbers = [s for s in decoded_str.split() if s]
                values = []
                for n in numbers[:9]:
                    try:
                        values.append(float(n))
                    except ValueError:
                        values.append(None)

            # 确保9个值
            while len(values) < 9:
                values.append(None)
            values = values[:9]

            row = [team_name, shirt_num, player_name] + values
            rows.append(row)

    return headers, rows


# ============================================================
# 12. 传球网络
# ============================================================

def parse_passing_network(pdf, team_a_page: int = 12, team_b_page: int = 13) -> Tuple[List[str], List]:
    """解析传球网络数据"""
    headers = ['team', 'from_number', 'from_player', 'to_number', 'to_player', 'passes']
    rows = []

    for page_num in [team_a_page, team_b_page]:
        lines = extract_page_lines(pdf, page_num)

        team_name = ''
        for line in lines:
            if 'Passing Networks' in line:
                if 'Canada' in line:
                    team_name = 'Canada'
                elif 'Morocco' in line:
                    team_name = 'Morocco'
                break

        # 找到矩阵表头行
        header_idx = -1
        target_players = []
        for i, line in enumerate(lines):
            if line.startswith('# Passes From') or line.startswith('# Passes'):
                header_idx = i
                rest = re.sub(r'^#\s*Passes\s*(From)?\s*(to)?\s*', '', line)
                surnames = re.findall(r'\b([A-Z]{2,})\b', rest)
                if surnames:
                    target_players = surnames
                break

        if header_idx == -1 or not target_players:
            continue

        # 解析数据行
        for line in lines[header_idx:]:
            match = re.match(r'^(\d+)\s+(.+?)\s+(\d[\d\s]*\d)$', line)
            if not match:
                continue

            from_num = match.group(1)
            from_name = match.group(2).strip()
            numbers_str = match.group(3).strip()
            numbers = numbers_str.split()

            if not re.search(r'[A-Z]{2,}', from_name):
                continue

            if len(numbers) != len(target_players):
                n = min(len(numbers), len(target_players))
                numbers = numbers[:n]
                targets = target_players[:n]
            else:
                targets = target_players

            # 输出非零传球对
            for j, count_str in enumerate(numbers):
                try:
                    count = int(count_str)
                except ValueError:
                    continue
                if count > 0:
                    to_player = targets[j]
                    rows.append([team_name, from_num, from_name, '', to_player, count])

    return headers, rows


# ============================================================
# 自动检测页码
# ============================================================

def _detect_team_pages(pdf) -> Dict[str, Dict[str, int]]:
    """自动检测各球队数据所在的页码（适用于不同报告格式）
    
    通过匹配每页第2行的标题格式来精确定位数据页。
    """
    total_pages = len(pdf.pages)
    
    # 先找两队队名
    lines_p1 = extract_page_lines(pdf, 1)
    home_team = ''
    away_team = ''
    for line in lines_p1:
        match = re.match(r'^(.+?)\s+(\d+)\s*-\s*(\d+)\s+(.+)$', line)
        if match:
            home_team = match.group(1).strip()
            away_team = match.group(4).strip()
            break
    
    # 数据类型 -> 标题关键词（匹配第2行）
    # 格式: (keyword_prefix, data_type, special_check)
    # special_check: 用于区分同一标题的多个页面（如射门有可视化页和明细表）
    keyword_map = [
        ('Attempts at Goal', 'attempts', 'detailed'),  # 需要明细表（含Time Player Outcome）
        ('Crosses (Open Play)', 'crosses', None),
        ('Crosses', 'crosses', None),  # 备用
        ('Offering to Receive', 'offers', None),
        ('In Possession - Distributions', 'possession_dist', None),
        ('In Possession - Offers', 'possession_offers', None),
        ('Out of Possession', 'defense', None),
        ('Physical Data', 'physical', None),
        ('Passing Networks', 'passing_network', None),
    ]
    
    found = {}
    for _, data_type, _ in keyword_map:
        if data_type not in found:
            found[data_type] = {'team_a': 0, 'team_b': 0}
    
    for page_num in range(1, min(total_pages + 1, 60)):
        try:
            lines = extract_page_lines(pdf, page_num)
        except Exception:
            continue
        
        if len(lines) < 2:
            continue
        
        title_line = lines[1]  # 第2行是标题
        
        for keyword, data_type, special_check in keyword_map:
            if keyword not in title_line:
                continue
            
            # 判断是哪支球队（标题行中应包含队名）
            is_home = home_team and home_team in title_line
            is_away = away_team and away_team in title_line
            
            team_key = 'team_a' if is_home else ('team_b' if is_away else '')
            if not team_key:
                continue
            
            # 如果已经找到过，跳过（保留第一个匹配）
            if found[data_type][team_key] != 0:
                # 但对于attempts，我们需要明细表（第二个页面）
                if data_type == 'attempts' and special_check == 'detailed':
                    # 检查是否为明细表（含Time Player Outcome表头）
                    full_text = get_page_text(pdf, page_num)
                    if 'Time Player Outcome' in full_text:
                        found[data_type][team_key] = page_num
                continue
            
            if data_type == 'attempts' and special_check == 'detailed':
                # 对于attempts，先检查是否为明细表
                full_text = get_page_text(pdf, page_num)
                if 'Time Player Outcome' in full_text:
                    found[data_type][team_key] = page_num
                # 否则先记录第一个，后面如果找到明细表会覆盖
                elif found[data_type][team_key] == 0:
                    found[data_type][team_key] = page_num
            else:
                found[data_type][team_key] = page_num
    
    # 如果没找到，使用默认值
    defaults = {
        'team_a': {
            'attempts': 15, 'crosses': 18, 'offers': 20,
            'possession_dist': 42, 'possession_offers': 43,
            'defense': 47, 'physical': 50, 'passing_network': 12,
        },
        'team_b': {
            'attempts': 17, 'crosses': 19, 'offers': 21,
            'possession_dist': 44, 'possession_offers': 45,
            'defense': 48, 'physical': 51, 'passing_network': 13,
        },
    }
    
    result = {}
    for team_key in ['team_a', 'team_b']:
        result[team_key] = {}
        for data_type in found.keys():
            page_val = found[data_type].get(team_key, 0)
            result[team_key][data_type] = page_val if page_val else defaults[team_key][data_type]
    
    return result


# ============================================================
# 主入口函数
# ============================================================

def parse_fifa_pdf(pdf_path: str, output_dir: str) -> Dict:
    """解析FIFA比赛报告PDF，生成12个CSV文件
    
    参数:
        pdf_path: PDF文件路径
        output_dir: 输出目录路径
    
    返回:
        dict: {
            'success': bool,
            'error': str (仅失败时有),
            'files': {key: {'path': str, 'rows': int}},
            'total_files': int,
            'total_rows': int,
            'output_dir': str,
        }
    """
    # 检查pdfplumber是否可用
    try:
        import os
        os.environ['PDFPLUMBER_VERBOSE'] = '0'
        import warnings
        warnings.filterwarnings('ignore')
        import gc
        import logging
        for logger_name in ['pdfplumber', 'pdfminer', 'pdfminer.cmapdb', 'pdfminer.pdfpage',
                            'pdfminer.pdfinterp', 'pdfminer.pdfdevice', 'pdfminer.converter',
                            'pdfminer.layout', 'pdfminer.utils']:
            try:
                logging.getLogger(logger_name).setLevel(logging.CRITICAL + 10)
            except Exception:
                pass
        import pdfplumber
    except ImportError:
        return {
            'success': False,
            'error': '缺少pdfplumber依赖，请先安装: pip install pdfplumber',
            'files': {},
            'total_files': 0,
            'total_rows': 0,
            'output_dir': output_dir,
        }
    
    try:
        # 验证PDF文件存在
        if not os.path.exists(pdf_path):
            return {
                'success': False,
                'error': f'PDF文件不存在: {pdf_path}',
                'files': {},
                'total_files': 0,
                'total_rows': 0,
                'output_dir': output_dir,
            }

        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)

        # 使用默认参数加载，laparams不传避免兼容性问题
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            if total_pages < 5:
                return {
                    'success': False,
                    'error': 'PDF页数过少，可能不是有效的FIFA比赛报告',
                    'files': {},
                    'total_files': 0,
                    'total_rows': 0,
                    'output_dir': output_dir,
                }

            # 自动检测页码
            pages = _detect_team_pages(pdf)

            output_files = {}

            # 1. 比赛基本信息
            headers, rows = parse_match_info(pdf)
            path = os.path.join(output_dir, "01_match_info.csv")
            count = write_csv(path, headers, rows)
            output_files['match_info'] = {'path': path, 'rows': count}

            # 2. 阵容
            headers, rows = parse_lineups(pdf)
            path = os.path.join(output_dir, "02_lineups.csv")
            count = write_csv(path, headers, rows)
            output_files['lineups'] = {'path': path, 'rows': count}

            # 3. 关键统计
            headers, rows = parse_key_stats(pdf)
            path = os.path.join(output_dir, "03_key_stats.csv")
            count = write_csv(path, headers, rows)
            output_files['key_stats'] = {'path': path, 'rows': count}

            # 4. 比赛阶段占比
            headers, rows = parse_phases_of_play(pdf)
            path = os.path.join(output_dir, "04_phases_of_play.csv")
            count = write_csv(path, headers, rows)
            output_files['phases_of_play'] = {'path': path, 'rows': count}

            # 5. 射门明细
            headers, rows = parse_attempts_at_goal(
                pdf,
                team_a_page=pages['team_a']['attempts'],
                team_b_page=pages['team_b']['attempts'],
            )
            path = os.path.join(output_dir, "05_attempts_at_goal.csv")
            count = write_csv(path, headers, rows)
            output_files['attempts_at_goal'] = {'path': path, 'rows': count}

            # 6. 传中数据
            headers, rows = parse_crosses(
                pdf,
                team_a_page=pages['team_a']['crosses'],
                team_b_page=pages['team_b']['crosses'],
            )
            path = os.path.join(output_dir, "06_crosses.csv")
            count = write_csv(path, headers, rows)
            output_files['crosses'] = {'path': path, 'rows': count}

            # 7. Offers to Receive
            headers, rows = parse_offers_to_receive(
                pdf,
                team_a_page=pages['team_a']['offers'],
                team_b_page=pages['team_b']['offers'],
            )
            path = os.path.join(output_dir, "07_offers_to_receive.csv")
            count = write_csv(path, headers, rows)
            output_files['offers_to_receive'] = {'path': path, 'rows': count}

            # 8. 个人持球 - Distributions
            headers, rows = parse_in_possession_distributions(
                pdf,
                team_a_page=pages['team_a']['possession_dist'],
                team_b_page=pages['team_b']['possession_dist'],
            )
            path = os.path.join(output_dir, "08_in_possession_distributions.csv")
            count = write_csv(path, headers, rows)
            output_files['in_possession_distributions'] = {'path': path, 'rows': count}

            # 9. 个人持球 - Offers
            headers, rows = parse_in_possession_offers(
                pdf,
                team_a_page=pages['team_a']['possession_offers'],
                team_b_page=pages['team_b']['possession_offers'],
            )
            path = os.path.join(output_dir, "09_in_possession_offers.csv")
            count = write_csv(path, headers, rows)
            output_files['in_possession_offers'] = {'path': path, 'rows': count}

            # 10. 个人防守数据
            headers, rows = parse_out_of_possession(
                pdf,
                team_a_page=pages['team_a']['defense'],
                team_b_page=pages['team_b']['defense'],
            )
            path = os.path.join(output_dir, "10_out_of_possession.csv")
            count = write_csv(path, headers, rows)
            output_files['out_of_possession'] = {'path': path, 'rows': count}

            # 11. 跑动数据
            headers, rows = parse_physical_data(
                pdf,
                team_a_page=pages['team_a']['physical'],
                team_b_page=pages['team_b']['physical'],
            )
            path = os.path.join(output_dir, "11_physical_data.csv")
            count = write_csv(path, headers, rows)
            output_files['physical_data'] = {'path': path, 'rows': count}

            # 12. 传球网络
            headers, rows = parse_passing_network(
                pdf,
                team_a_page=pages['team_a']['passing_network'],
                team_b_page=pages['team_b']['passing_network'],
            )
            path = os.path.join(output_dir, "12_passing_network.csv")
            count = write_csv(path, headers, rows)
            output_files['passing_network'] = {'path': path, 'rows': count}

        # 统计
        total_rows = sum(v['rows'] for v in output_files.values())
        total_files = len(output_files)

        # 验证关键文件是否有数据
        if output_files['match_info']['rows'] == 0:
            return {
                'success': False,
                'error': '未能解析出比赛基本信息，PDF格式可能不支持',
                'files': output_files,
                'total_files': total_files,
                'total_rows': total_rows,
                'output_dir': output_dir,
            }

        return {
            'success': True,
            'files': output_files,
            'total_files': total_files,
            'total_rows': total_rows,
            'output_dir': output_dir,
        }

    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': f'解析失败: {str(e)}',
            'error_detail': traceback.format_exc(),
            'files': {},
            'total_files': 0,
            'total_rows': 0,
            'output_dir': output_dir,
        }


# ============================================================
# 命令行直接运行
# ============================================================

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("用法: python fifa_pdf_parser.py <pdf_path> [output_dir]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './csv_output'
    
    result = parse_fifa_pdf(pdf_path, output_dir)
    
    if result['success']:
        print(f"解析成功: {result['total_files']} 个文件, {result['total_rows']} 行数据")
        for key, info in result['files'].items():
            print(f"  - {key}: {info['rows']} 行 -> {os.path.basename(info['path'])}")
    else:
        print(f"解析失败: {result['error']}")
        if 'error_detail' in result:
            print(result['error_detail'])
        sys.exit(1)
