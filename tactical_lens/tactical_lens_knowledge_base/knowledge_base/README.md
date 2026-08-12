# 战术透镜知识库 (Tactical Lens Knowledge Base)

基于 StatsBomb 数据标准的足球战术分析指标与训练方法体系。

## 项目结构

```
tactical-lens-knowledge-base/
├── README.md                    # 本文件
├── metrics/
│   ├── attacking.md             # 进攻指标定义
│   ├── defending.md             # 防守指标定义
│   ├── possession.md            # 控球与传球指标
│   ├── transitions.md           # 攻防转换指标
│   └── set_pieces.md            # 定位球指标
├── zones/
│   ├── pitch_zones.md           # 场地分区定义
│   └── possession_flow.md       # 球权流动模式
├── training/
│   ├── by_scenario.md           # 按对抗场景分类的训练方法
│   └── by_zone.md               # 按场地区域分类的训练方法
└── data_to_training/
    └── mapping_framework.md     # 数据→洞察→训练 映射框架
```

## 数据来源

- [StatsBomb Glossary](https://statsbomb.com/resources/glossary)
- [StatsBomb Articles](https://statsbomb.com/articles/soccer/)
- [StatsBomb Open Data](https://github.com/statsbomb/open-data)
- FBref 指标说明
- JASPA 运动表现分析课程

## 使用方式

每个 `.md` 文件包含：
1. 指标/概念的**精确定义**
2. **计算方式**（如适用）
3. **战术意义**（这个数字说明了什么）
4. **训练关联**（对应什么训练场景）

---

## 快速导航

### 核心指标
| 指标 | 定义 | 文件 |
|------|------|------|
| xG | 预期进球 | `metrics/attacking.md` |
| xA | 预期助攻 | `metrics/attacking.md` |
| OBV | 持球价值 | `metrics/possession.md` |
| PPDA | 压迫强度 | `metrics/defending.md` |
| Progressive Passes | 推进传球 | `metrics/possession.md` |
| Line-Breaking Passes | 破线传球 | `metrics/possession.md` |

### 训练映射
| 数据发现 | 训练方向 | 文件 |
|---------|---------|------|
| 射门xG低 | 进攻三区决策训练 | `training/by_zone.md#进攻三区` |
| PPDA高 | 高位压迫训练 | `training/by_scenario.md#防守压迫` |
| 推进传球少 | 中场推进训练 | `training/by_scenario.md#推进配合` |

## 版本

v0.1.0 - 初始版本，基于 StatsBomb 标准定义