# 攻防转换指标 (Transition Metrics)

## 1. Counter-Press 反抢

**定义**：丢球后立即对持球者施压，试图在短时间内夺回球权。

**StatsBomb 事件**：`Counterpress` (boolean flag on events)

**指标**：
- Counter-Press Recoveries：反抢成功次数
- Counter-Press Duration：反抢持续时间（丢球后几秒内）
- Counter-Press Success Rate：反抢成功率

**战术意义**：
- 高频反抢 = 高位压迫体系（如克洛普的Gegenpressing）
- 高成功率 = 反抢组织有效
- 反抢失败后的防守漏洞 = 体能下降或组织混乱

**训练关联**：
- 丢球后5秒反抢训练
- 小组反抢协调训练
- 体能训练（维持高强度反抢）

---

## 2. Transition Speed 转换速度

**定义**：从夺回球权到完成射门的时间。

**计算方式**：
```
Transition Time = 射门时间 - 球权夺回时间
```

**分类**：
- **快速转换**（<10秒）：反击打法
- **中速转换**（10-20秒）：半转换
- **慢速转换**（>20秒）：阵地进攻

**战术意义**：
- 快速转换进球多 = 反击效率高
- 慢速转换 xG 高 = 阵地组织能力强
- 转换速度慢 = 从防守到进攻的衔接有问题

**训练关联**：
- 快速反击训练
- 由守转攻第一传训练
- 前插跑位训练

---

## 3. Direct Attacks 直接进攻

**定义**：从后场直接推进到前场进攻的序列（通常指5秒内完成至少3次传球并到达前场）。

**StatsBomb 标签**：`Direct Attack` (play pattern)

**指标**：
- Direct Attack Frequency：直接进攻频率
- Direct Attack xG：直接进攻创造的xG
- Direct Attack Success Rate：直接进攻成功率

**战术意义**：
- 高频直接进攻 = 打法简洁、快速
- 低效直接进攻 = 后场出球能力不足
- 高效直接进攻 = 反击/快速进攻体系成熟

**训练关联**：
- 快速出球训练
- 纵深跑位训练
- 后场组织训练（应对高位压迫）

---

## 4. Turnover Location 球权丢失位置

**定义**：丢失球权的位置分布。

**StatsBomb 数据**：`Ball Recovery` 事件的反面

**分类**：
- **进攻三区丢失**：在前场丢球
- **中场丢失**：在中场丢球
- **后场丢失**：在后场丢球

**战术意义**：
- 前场丢失多 = 进攻冒险性高，但反抢机会多
- 中场丢失多 = 中场控制力弱
- 后场丢失多 = 极度危险，容易被反击得分

**训练关联**：
- 控球保护训练
- 传球安全选择训练
- 不同区域的控球策略训练

---

## 5. Counter Attacks 反击

**定义**：从防守状态快速推进到进攻状态。

**StatsBomb 标签**：`Counter Attack` (play pattern)

**指标**：
- Counter Attack Frequency：反击频率
- Counter Attack xG：反击创造的xG
- Counter Attack Speed：反击速度（秒数）
- Counter Attack Shots：反击射门数

**战术意义**：
- 高频反击 = 反击型球队
- 高反击 xG = 反击质量高
- 反击射门多 = 反击终结能力强

**训练关联**：
- 反击推进训练
- 前插跑位训练
- 快速传球训练
- 1v1/2v1 终结训练

---

## 6. High Turnover 高位抢断

**定义**：在对方半场（通常是进攻三区）夺回球权。

**StatsBomb 数据**：`Ball Recovery` 事件中 location 在前场的

**指标**：
- High Turnovers：高位抢断次数
- High Turnover Shots：高位抢断后射门数
- High Turnover xG：高位抢断创造的xG

**战术意义**：
- 高位抢断是最高效的进攻方式之一（离球门近、对方防守未到位）
- 高频高位抢断 = 前场压迫有效
- 高位抢断后射门 = 压迫转化为进攻威胁

**训练关联**：
- 前场逼抢训练
- 高位抢断后快速进攻训练
- 前锋/前场球员压迫训练

---

## 7. Recovery Speed 回防速度

**定义**：丢失球权后回到防守位置的速度。

**衡量方式**：
- 从丢球到形成防守阵型的时间
- 防守阵型的紧凑度恢复

**战术意义**：
- 回防快 = 防守纪律好、体能好
- 回防慢 = 容易被反击、防守漏洞大

**训练关联**：
- 攻转守训练
- 回防跑位训练
- 体能训练

---

## 转换指标速查表

| 指标 | 衡量什么 | 高了说明什么 | 低了说明什么 |
|------|---------|-------------|-------------|
| Counter-Press Success | 反抢效率 | 反抢有效 | 反抢无效 |
| Transition Speed | 转换速度 | 打法快 | 打法慢 |
| Direct Attack xG | 直接进攻质量 | 快速进攻有效 | 快速进攻低效 |
| 前场丢失率 | 进攻区域丢球 | 进攻冒险 | 进攻保守 |
| Counter Attack xG | 反击质量 | 反击威胁大 | 反击威胁小 |
| High Turnovers | 高位抢断 | 前场压迫有效 | 前场压迫无效 |
| Recovery Speed | 回防速度 | 防守纪律好 | 容易被反击 |

---

*参考来源：StatsBomb Play Patterns, FBref Transition Metrics, Gegenpressing Literature*