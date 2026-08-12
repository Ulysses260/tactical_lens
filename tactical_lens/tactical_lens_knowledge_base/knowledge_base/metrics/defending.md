# 防守指标定义 (Defending Metrics)

## 1. PPDA (Passes Per Defensive Action) 压迫强度

**定义**：对方每次成功防守动作（抢断、拦截、犯规）前，允许对方完成的传球次数。

**计算方式**：
```
PPDA = 对方传球次数 / 本方防守动作次数（抢断+拦截+犯规）
```
通常只计算在前场三分之二的防守动作。

**解读**：
- PPDA 越低 = 压迫越积极（每次防守动作前允许的传球越少）
- PPDA 越高 = 压迫越被动
- 典型范围：8-15（低位防守），5-8（高位压迫）

**StatsBomb 对应数据**：
- Pressure 事件（压迫事件）
- 结合 Ball Recovery 事件计算

**战术意义**：
- 反映球队压迫策略（高位/中位/低位）
- 反映体能水平和战术纪律
- 压迫强度变化反映体能下降或战术调整

**训练关联**：
- 高位压迫训练（前场逼抢）
- 团队压迫协调训练
- 体能训练（维持压迫强度）

**数据来源**：StatsBomb 360, FBref

---

## 2. Defensive Actions 防守动作

**定义**：阻止对方进攻的行为。

**StatsBomb 事件类型**：
- **Tackle**（抢断）：成功夺回球权的防守动作
- **Interception**（拦截）：截断对方传球
- **Block**（封堵）：封堵射门或传球路线
- **Clearance**（解围）：将球踢出危险区域
- **Aerial Duel Won/Lost**（高空对抗胜/负）

**细分指标**：
| 指标 | 定义 | 意义 |
|------|------|------|
| Tackles Won % | 抢断成功率 | 防守效率 |
| Interceptions per 90 | 每90分钟拦截数 | 预判和站位能力 |
| Blocks per 90 | 每90分钟封堵数 | 防守积极性 |
| Clearances | 解围次数 | 防守压力程度 |

**战术意义**：
- 高 Tackle 数 + 低成功率 = 防守位置差，需要频繁补位
- 高 Interception 数 = 预判好、站位好
- 高 Clearance 数 = 防守压力大，被动防守多

**训练关联**：
- 1v1 防守训练
- 抢断时机训练
- 站位和预判训练
- 防守阵型协调训练

---

## 3. Defensive Duels 防守对抗

**定义**：防守方球员与进攻方球员的一对一对抗。

**StatsBomb 事件**：`Duel` (type), defensive side

**指标**：
- Defensive Duel Success Rate：防守对抗成功率
- Defensive Duel Frequency：防守对抗频率

**战术意义**：
- 高成功率 = 1v1防守能力强
- 低成功率 = 容易被过，需要提高防守技巧或协防
- 高频次 = 该位置经常面临1v1，可能需要调整防守策略

**训练关联**：
- 1v1 防守训练（正面/侧面/背面防守）
- 协防训练
- 身体对抗训练

---

## 4. Pressure 压迫

**定义**：防守方对持球球员施加的压力。

**StatsBomb 事件**：`Pressure`

**细分**：
- Pressure per 90：每90分钟压迫次数
- Pressure Success Rate：压迫成功率（导致对方丢球的比例）
- Pressure in Final Third：前场压迫次数

**战术意义**：
- 反映球队整体压迫策略
- 反映球员个人压迫能力
- 压迫成功率反映压迫质量（而非仅仅是数量）

**训练关联**：
- 压迫时机训练（何时压、何时退）
- 团队压迫协调训练
- 前场逼抢训练

---

## 5. Ball Recovery 球权夺回

**定义**：夺回球权的行为。

**StatsBomb 事件**：`Ball Recovery`

**细分**：
- Ball Recovery Location：球权夺回位置（前场/中场/后场）
- Counter Press Recovery：反抢成功（丢球后立即反抢）
- Offensive Ball Recovery：进攻性球权夺回（在前场夺回球权）

**战术意义**：
- 前场夺回球权 = 高位压迫有效
- 中场夺回 = 中场控制力强
- 后场夺回 = 防守组织好

**训练关联**：
- 反抢训练（丢球后5秒内反抢）
- 高位压迫训练
- 团队防守转换训练

---

## 6. Aerial Duels 高空对抗

**定义**：争顶头球的对抗。

**StatsBomb 事件**：`Duel` → `Aerial`

**指标**：
- Aerial Duel Won %：争顶成功率
- Aerial Duel Frequency：争顶频率

**战术意义**：
- 高成功率 + 高频率 = 空中优势
- 低成功率 = 需要加强高空防守或调整战术减少高空对抗

**HOPS (Header Oriented Performance System)**：
StatsBomb 独有的头球评估模型，不仅看数量，还看：
- 对谁争顶（对手实力）
- 争顶质量（位置、时机）

**训练关联**：
- 头球训练（进攻/防守）
- 身体对抗训练
- 定位球攻防训练

---

## 7. Goalkeeping 守门员指标

**StatsBomb 事件**：`Goalkeeper`

**细分类型**：
| 类型 | 定义 |
|------|------|
| Shot Saved | 扑救射门 |
| Shot Saved Post | 扑救到门柱 |
| Shot Saved Off Target | 对方射偏（门将位置好） |
| Punch | 拳击球 |
| Claim | 接住传中 |
| Sweep | 出击扫荡 |
| Save Set Piece | 定位球扑救 |

**进阶指标**：
- **Post-Shot xG vs Goals Conceded**：射门后的预期进球 vs 实际失球
  - 正值 = 门将表现差（失球比预期多）
  - 负值 = 门将表现好（扑救比预期多）
- **Cross Claim %**：传中接住率
- **Sweep Actions**：出击次数

**训练关联**：
- 门将专项训练（扑救、出击、传中处理）
- 后卫与门将配合训练
- 定位球防守训练

---

## 防守指标速查表

| 指标 | 衡量什么 | 高了说明什么 | 低了说明什么 |
|------|---------|-------------|-------------|
| PPDA | 压迫强度 | 压迫积极 | 压迫被动 |
| Tackle Won % | 抢断效率 | 抢断精准 | 抢断时机差 |
| Interceptions | 拦截能力 | 预判好 | 预判差 |
| Defensive Duel % | 1v1防守 | 防守能力强 | 容易被过 |
| Pressure Success % | 压迫质量 | 压迫有效 | 压迫无效 |
| Ball Recovery (前场) | 高位反抢 | 高位压迫有效 | 高位压迫无效 |
| Aerial Won % | 高空对抗 | 空中优势 | 空中劣势 |
| PSxG +/- | 门将表现 | 门将扑救好 | 门将表现差 |

---

*参考来源：StatsBomb Glossary, FBref Defensive Metrics, JASPA Course Materials*