"""
training_standards.py — 国际主流训练体系

数据源：
  • UEFA Training Guide (2023)
  • Liverpool FC Academy Methodology
  • Barcelona La Masia Principles
  • StatsBomb 教练培训材料

核心：每个战术问题映射到具体的训练方案
  - 训练名称（国际通用术语）
  - 时长和强度
  - 人数配置
  - 重点指标
  - 难度等级
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import json


@dataclass
class TrainingModule:
    """训练模块定义"""

    module_id: str
    name_en: str  # 英文名（国际通用术语）
    name_cn: str  # 中文名
    category: str  # "attacking" | "defending" | "possession" | "transition" | "set_piece"
    duration_min: int  # 分钟
    intensity: str  # "low" | "medium" | "high"
    setup_complexity: str  # "simple" | "medium" | "complex"
    players_required: int
    focus_stats: List[str]  # 这个训练改善的指标
    description: str
    progression_level: int  # 1-5，难度等级
    reference_source: str  # 数据来源（UEFA/Liverpool/Barcelona）
    key_coaching_points: List[str]


class TrainingStandards:
    """国际主流训练库"""

    # 攻防转换训练
    TRANSITION_MODULES = [
        TrainingModule(
            module_id="high_press_1st_pass",
            name_en="High Press - First Pass Reaction",
            name_cn="高位反抢-首传反应",
            category="transition",
            duration_min=20,
            intensity="high",
            setup_complexity="medium",
            players_required=11,
            focus_stats=["ppda", "pressure_success"],
            description="丢球后 5 秒内集体反抢，针对对手出球第一传的压迫训练",
            progression_level=3,
            reference_source="UEFA Level A",
            key_coaching_points=[
                "反抢时机识别（观察对方传中点）",
                "逼迫方向明确（切断射门/传中线路）",
                "压迫强度控制（不过度冒进）",
            ],
        ),
        TrainingModule(
            module_id="transition_counter_attack",
            name_en="Transition - Counter Attack",
            name_cn="防守反击-快速转攻",
            category="transition",
            duration_min=25,
            intensity="high",
            setup_complexity="complex",
            players_required=11,
            focus_stats=["counter_attack_goals", "transition_success"],
            description="抢断球后 3 秒内完成传导，形成 3v2 或 4v3 的快速反击",
            progression_level=4,
            reference_source="Liverpool FC",
            key_coaching_points=[
                "抢断位置判断（往哪边反击最快）",
                "传导节奏（直传 vs 横传）",
                "终结意识（何时射门 vs 继续推进）",
            ],
        ),
    ]

    # 进攻模块
    ATTACKING_MODULES = [
        TrainingModule(
            module_id="final_third_decision",
            name_en="Final Third Decision Making",
            name_cn="禁区前沿决策训练",
            category="attacking",
            duration_min=20,
            intensity="medium",
            setup_complexity="medium",
            players_required=8,
            focus_stats=["xg_to_shot_ratio", "key_passes"],
            description="禁区前 20m 区域内的决策训练：何时传中、何时盘带、何时射门",
            progression_level=3,
            reference_source="Barcelona La Masia",
            key_coaching_points=[
                "空间读数（防线漏洞识别）",
                "时机选择（门将位置、防线站位）",
                "射门位置质量（禁区内 > 禁区外）",
            ],
        ),
        TrainingModule(
            module_id="crossing_accuracy",
            name_en="Crossing Accuracy - Wide Play",
            name_cn="传中精准度-边锋训练",
            category="attacking",
            duration_min=20,
            intensity="medium",
            setup_complexity="simple",
            players_required=6,
            focus_stats=["cross_accuracy", "crosses_completed"],
            description="边锋/边后卫传中精准度提升：不同距离、角度、防守压力下的传中",
            progression_level=2,
            reference_source="UEFA Training Guide",
            key_coaching_points=[
                "传中节奏控制（快速 vs 停顿调整）",
                "传中类型多样性（地滚球 vs 高空球 vs 外旋球）",
                "禁区前锋位置感（何时插上）",
            ],
        ),
        TrainingModule(
            module_id="shot_finishing",
            name_en="Shot Finishing - 1v1 vs Keeper",
            name_cn="1v1 射门终结",
            category="attacking",
            duration_min=15,
            intensity="medium",
            setup_complexity="simple",
            players_required=4,
            focus_stats=["conversion_rate", "shots_on_target"],
            description="一对一面对门将的射门训练，重点是枪法和心理素质",
            progression_level=2,
            reference_source="Liverpool FC",
            key_coaching_points=[
                "身体控制（射门前的触球调整）",
                "枪法选择（远角 vs 近角 vs 穿档）",
                "心理建设（克服门将压力）",
            ],
        ),
    ]

    # 防守模块
    DEFENDING_MODULES = [
        TrainingModule(
            module_id="1v1_defending",
            name_en="1v1 Defending - Positioning",
            name_cn="1v1 防守-位置感",
            category="defending",
            duration_min=20,
            intensity="medium",
            setup_complexity="simple",
            players_required=4,
            focus_stats=["duel_success_rate", "tackle_success"],
            description="单人防守训练：距离管理、身体姿态、延缓对手",
            progression_level=2,
            reference_source="UEFA Level A",
            key_coaching_points=[
                "防守距离（0.5-1.5m 最佳）",
                "身体姿态（降低重心，敞开胸口）",
                "逼迫方向（往弱脚逼）",
                "避免飞铲（静态防守 > 动态铲球）",
            ],
        ),
        TrainingModule(
            module_id="defensive_line_shape",
            name_en="Defensive Line Shape - Offside Trap",
            name_cn="防线形态-越位陷阱",
            category="defending",
            duration_min=25,
            intensity="medium",
            setup_complexity="complex",
            players_required=11,
            focus_stats=["offside_trap_success", "defensive_line_coordination"],
            description="整体防线配合，通过联动前压制造越位",
            progression_level=4,
            reference_source="Barcelona",
            key_coaching_points=[
                "防线同步性（所有后卫同时前压）",
                "防线宽度（根据进攻方宽度调整）",
                "越位陷阱时机（预判 vs 反应）",
            ],
        ),
        TrainingModule(
            module_id="defensive_set_pieces",
            name_en="Set Piece Defense - Zonal Coverage",
            name_cn="定位球防守-区域防守",
            category="defending",
            duration_min=15,
            intensity="medium",
            setup_complexity="simple",
            players_required=6,
            focus_stats=["set_piece_goals_conceded", "aerials_won"],
            description="角球和任意球的定位球防守，强调站位和头球争顶",
            progression_level=2,
            reference_source="UEFA",
            key_coaching_points=[
                "区域分工（6 码区 vs 禁区 vs 禁区外）",
                "身体对抗位置（抢占身体位置，不犯规）",
                "头球争顶意识（提前启动）",
            ],
        ),
    ]

    # 传控组织模块
    POSSESSION_MODULES = [
        TrainingModule(
            module_id="build_up_play",
            name_en="Build-Up Play - Pressing Resistance",
            name_cn="防线组织-抗压传球",
            category="possession",
            duration_min=20,
            intensity="medium",
            setup_complexity="medium",
            players_required=8,
            focus_stats=["pass_accuracy", "possession_pct"],
            description="后场在对手压迫下的组织传球，增强容错能力",
            progression_level=3,
            reference_source="Barcelona",
            key_coaching_points=[
                "接球身体前倾（面向前方，准备出球）",
                "三角传导（避免直线传导容易被断）",
                "出球选项清晰（门将 + 两个后卫形成三角）",
            ],
        ),
        TrainingModule(
            module_id="progressive_passing",
            name_en="Progressive Passing - Forward Line Breaking",
            name_cn="推进传球-线性穿透",
            category="possession",
            duration_min=20,
            intensity="medium",
            setup_complexity="medium",
            players_required=8,
            focus_stats=["pass_into_final_third", "progressive_passes"],
            description="纵向穿透传球，快速推进到禁区前沿",
            progression_level=3,
            reference_source="Liverpool FC",
            key_coaching_points=[
                "传球时机（防线不完整时）",
                "传球距离（避免过长导致失球）",
                "接球跑位（插上接应，创造身后空间）",
            ],
        ),
        TrainingModule(
            module_id="possession_rondo",
            name_en="Rondo - Possession Under Pressure",
            name_cn="回传游戏-压力下传控",
            category="possession",
            duration_min=15,
            intensity="high",
            setup_complexity="simple",
            players_required=6,
            focus_stats=["pass_accuracy", "pass_completion"],
            description="多人传控对抗：5v1 或 6v2，强调一触传球和空间意识",
            progression_level=1,
            reference_source="UEFA",
            key_coaching_points=[
                "跑位节奏（提前启动，不等球）",
                "一触传球（减少触球次数）",
                "视野开阔（用余光观察位置）",
            ],
        ),
    ]

    def __init__(self):
        self.all_modules = (
            self.TRANSITION_MODULES + self.ATTACKING_MODULES + self.DEFENDING_MODULES + self.POSSESSION_MODULES
        )
        self.module_dict = {m.module_id: m for m in self.all_modules}

    def get_module(self, module_id: str) -> Optional[TrainingModule]:
        """获取单个训练模块"""
        return self.module_dict.get(module_id)

    def get_modules_by_issue(self, issue_id: str) -> List[TrainingModule]:
        """根据问题 ID 获取推荐训练模块"""
        # 问题到训练的映射
        issue_to_modules = {
            "high_shot_low_xg": [
                "final_third_decision",
                "shot_finishing",
                "crossing_accuracy",
            ],
            "low_possession": [
                "build_up_play",
                "progressive_passing",
                "possession_rondo",
            ],
            "weak_pressure": [
                "high_press_1st_pass",
                "defensive_line_shape",
            ],
            "poor_crossing": [
                "crossing_accuracy",
                "final_third_decision",
            ],
            "weak_duels": [
                "1v1_defending",
                "defensive_set_pieces",
            ],
            "high_turnover": [
                "build_up_play",
                "possession_rondo",
            ],
        }

        module_ids = issue_to_modules.get(issue_id, [])
        return [self.module_dict[mid] for mid in module_ids if mid in self.module_dict]

    def get_training_plan_for_team(
        self, problems: List[Dict[str, Any]], top_n_problems: int = 3
    ) -> Dict[str, Any]:
        """为球队生成训练计划"""
        # 取 top N 问题
        top_issues = problems[:top_n_problems]

        training_plan = {
            "total_problems_identified": len(problems),
            "top_problems": top_issues,
            "recommended_training": [],
            "weekly_schedule": self._generate_weekly_schedule(top_issues),
            "total_duration_min": 0,
        }

        # 为每个问题推荐训练
        for issue in top_issues:
            modules = self.get_modules_by_issue(issue["issue_id"])
            if modules:
                training_plan["recommended_training"].append(
                    {
                        "problem": issue["title"],
                        "severity": issue["severity"],
                        "modules": [
                            {
                                "id": m.module_id,
                                "name": m.name_cn,
                                "duration": m.duration_min,
                                "intensity": m.intensity,
                                "players": m.players_required,
                                "coaching_points": m.key_coaching_points,
                                "reference": m.reference_source,
                            }
                            for m in modules
                        ],
                    }
                )
                training_plan["total_duration_min"] += sum(m.duration_min for m in modules)

        return training_plan

    def _generate_weekly_schedule(self, top_issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """生成周训练日程"""
        schedule = []

        days_allocation = {
            "Monday": "恢复 + 技术基础",
            "Tuesday": "战术演练（高强度）",
            "Wednesday": "定位球专项",
            "Thursday": "轻强度 + 恢复",
            "Friday": "完整阵容演练",
            "Saturday": "比赛前准备",
            "Sunday": "比赛日",
        }

        for day, default_focus in days_allocation.items():
            schedule.append({"day": day, "focus": default_focus, "duration_min": 90})

        return schedule


# 全局训练标准库实例
_training_standards = TrainingStandards()


def get_training_modules_for_issue(issue_id: str) -> List[TrainingModule]:
    """获取某个问题的推荐训练"""
    return _training_standards.get_modules_by_issue(issue_id)


def get_training_plan(problems: List[Dict[str, Any]], top_n: int = 3) -> Dict[str, Any]:
    """生成球队的周训练计划"""
    return _training_standards.get_training_plan_for_team(problems, top_n)
