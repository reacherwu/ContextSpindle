# Mission 2.8.1: Scientific Integrity & Failure-Boundary Patch Report

**Status:** EMPIRICALLY AUDITED & VERIFIED  
**Canonical Test Seeds:** [101, 202, 303]  
**Development Seed:** 999  
**Directive:** CTO/Judge Mission 2.8 Review & Failure-Boundary Audit  

---

## 1. Executive Summary & Three Core Scientific Phenomena

Mission 2.8.1 完成对 Revision 机制的科学完整性审查。正如首席科学官评述：**Mission 2.8 的最大价值不是证明 Revision 很强，而是第一次把 Continuum 的失效边界与运行包络（Operating Envelope）严格测出。**

### 当前已确立的三大核心科学现象：
1. $\boxed{\text{Delayed direct cause can be recovered}}$: 直接延迟因果前置事件（$A \to D$）在超出现有热记忆 12 倍的长流中可通过冷候选区与回溯修订稳定召回。
2. $\boxed{\text{Multi-hop causality currently breaks}}$: 当前修订引擎无法泛化至多跳链条（$A \to B \to D$ 暴跌至 0.0%），证实当前原型仅具备终端对根因的直接匹配能力，缺乏跨节点递归逆向传播能力。
3. $\boxed{\text{Candidate crowding currently breaks}}$: 在候选池充斥大量局部语义重叠的相似诱饵（$\ge 500$）时，单纯依赖余弦相似度与时间衰减的打分器会被近端诱饵截获，精确率与召回率归零。

---

## 2. Revision 运行视界（Horizon）三层体系与种子失败记录

### 2.1 三层视界（Horizon）理论定义
严格修正上一版报告中 "$\Delta t \ge 250$ 时所有无修订模型跌入 0%" 的不严谨表述，正式确立三层视界分界：
- **热记忆直接覆盖视界 ($\Delta t < \Delta t_{\text{hot}} = K_{\text{hot}} = 250$):** 根因在终端到达时尚未被淘汰出热区，系统无需 Revision 即自然实现 100.0% 检索准确率。
- **冷区激活必要性视界 ($\Delta t_{\text{hot}} < \Delta t < \Delta t_{\text{cold}} = K_{\text{hot}} + K_{\text{cold}} = 750$):** 根因被热记忆淘汰并推入冷候选区。无修订模型（E0-E4）准确率降为 0.0%，Revision 是产生恢复收益的唯一必要组件。
- **冷区物理截断视界 ($\Delta t > \Delta t_{\text{cold}}$):** 在固定 $K_{\text{cold}}=500$ 下，长流中持续产生的中间事件会逐渐填满冷区 FIFO 环形缓冲区，导致根因最终被挤出。此视界必须通过按比例冷区扩展或稀疏索引维持。

### 2.2 保留真实的种子级失败事实 ($\Delta t = 1000$)
在 $\Delta t = 1000$ 的评测中，严禁隐瞒失败：
- **Seed 101:** Recall = 100.0%, Precision = 100.0% (成功召回)
- **Seed 303:** Recall = 100.0%, Precision = 100.0% (成功召回)
- **Seed 202 (失败案例):** `root_in_hot = False, root_in_cold = True, restoration_recall = 0.0, false_revision_rate = 1.0`
  *原因分析：* 在 Seed 202 中，根因事件 100 确实在冷区中完好保存，但步数 875 的背景簇转移事件偶然与终端产生了稍微偏高的相似度，在 `max_restorations=1` 的单一名额限制下拦截了根因。这证实了在缺乏更强拓扑约束时，种子级随机性在临界状态下具有实质影响。

---

## 3. 核心失败边界一：多跳因果链断裂 (Multi-Hop Causal Chain Depth)

| 因果拓扑 | 跳数 $L$ | 中间节点数 | 平均根因召回率 | 平均修订精确率 | 虚警率 | Top-1 检索准确率 |
|:---|---:|:---|---:|---:|---:|---:|
| `A -> D` | **2** | 0 个中间节点 | **100.0%** | **100.0%** | 0.00 | **100.0%** |
| `A -> B -> D` | **3** | 1 个中间节点 | **  0.0%** |   0.0% | 0.67 | **  0.0%** |
| `A -> B -> C -> D` | **4** | 2 个中间节点 | ** 33.3%** |  33.3% | 0.33 | ** 33.3%** |
| `A -> B -> C -> D -> E` | **5** | 3 个中间节点 | ** 33.3%** |  33.3% | 0.67 | ** 33.3%** |
| `A -> B -> C -> D -> E -> F` | **6** | 4 个中间节点 | ** 33.3%** |  33.3% | 0.33 | ** 33.3%** |

> **正式科学结论：**  
> **Current Revision Engine does NOT scale to multi-hop causal chains. Current Revision is effective for direct delayed causal attribution but fails to reliably propagate credit across multi-hop causal chains.**  
> 撤回原先 "证明了稀疏级联追溯的必要性" 的断言，将其定性为当前原型的本质结构性缺陷。

---

## 4. 核心失败边界二：候选池语义拥挤 (Candidate-Pool Crowding)

| 相似干扰项数量 | 平均根因召回率 | 平均修订精确率 | 虚警恢复率 | 状态判定 |
|-----------------:|-----------------:|---------------:|--------------------:|:---|
| **   0** | **100.0%** | **100.0%** | 0.00 | 🟢 绝对可靠 |
| **  10** | ** 66.7%** | ** 66.7%** | 0.33 | 🟡 边缘可用 |
| **  50** | ** 33.3%** | ** 33.3%** | 0.67 | 🟡 衰减严重 |
| ** 100** | ** 66.7%** | ** 66.7%** | 0.33 | 🟡 边缘可用 |
| ** 500** | **  0.0%** | **  0.0%** | 0.67 | 🔴 彻底失效 |

> **正式科学结论：**  
> **Current Revision Engine is highly vulnerable to candidate-pool semantic crowding.**  
> 随着候选池膨胀，冷区检索面临严重信噪比塌陷。冷区记忆的关键瓶颈不在于物理 RAM 存储（500 槽 $< 0.1$ MB），而在于大规模候选下的因果可辨识性（Identifiability）。

---

## 5. 动力学因果兼容性 (State Compatibility) 消融实验的严格定性

在干净延迟链消融中：
- `Full (0.4, 0.3, 0.2, 0.1)`: Recall = 100.0%
- `Sim_Only (1.0, 0, 0, 0)`: Recall = 100.0%
- `Sim_Plus_State (0.55, 0.45, 0, 0)`: Recall = 100.0%
- `State_Only (0, 1.0, 0, 0)`: Recall = 0.0%

> **严格表述修正：**  
> **State compatibility provides evidence of complementary discrimination under adversarial controls (e.g., NC2 orthogonal state rejection), but its independent contribution is not established by the clean delayed-chain ablation.**  
> 干净流下纯相似度即可解决检索，动力学状态约束的独立价值需依赖对抗干扰组方能展现。

---

## 6. 算法级多目标 Pareto 优势计算 (剔除标量 Efficiency 误导)

废除容易导致标量误导的人为 Efficiency 公式。基于 $(\text{Recall} \uparrow, \text{Precision} \uparrow, -K_{\text{total}} \uparrow, -\text{Latency} \uparrow)$ 进行严格数学 Pareto 优势筛选：

### 12 个评估点中真实非支配 Pareto 前沿 (5 个点)：

| 序号 | $K_{\text{hot}}$ | $K_{\text{cold}}$ | $K_{\text{total}}$ | 平均召回率 | 平均精确率 | 平均延迟 (ms) | Pareto 角色与工程权衡 |
|:---|---:|---:|---:|---:|---:|---:|:---|
| 1 | 50 | 25 | **75** | 0.0% | 0.0% | **232.5** | 极限极小内存配置（但因过早挤出完全丧失召回） |
| 2 | 50 | 50 | **100** | 0.0% | 0.0% | **228.2** | 评测网格中绝对延迟最低点 |
| 3 | 100 | 100 | **200** | 33.3% | 33.3% | 244.1 | 紧凑内存下的局部低召回折中点 |
| 4 | 100 | 200 | **300** | 33.3% | 33.3% | 235.9 | 比 200 槽延迟更低的部分召回点 |
| 5 | **250** | **500** | **750** | **100.0%** | **100.0%** | 287.3 | **网格中唯一实现 100.0% 召回与精确率的非支配点** |

> **Pareto 结论定性更正：**  
> 严禁称为 "全局 Pareto 最优"。严格表述为：**$K_{\text{hot}}=250, K_{\text{cold}}=500$ ($K_{\text{total}}=750$) 是当前实验评估网格中的最佳观测工作点 (Best Observed Operating Point)。** 其他更大内存点（如 $K=1500$）已被此点严格 Pareto 支配。

---

## 7. Memory Revision Operating Envelope & Failure Map

基于 3 个 Canonical Seeds 自动生成的二维工作包络图 ($X=\Delta t, Y=|D_{\text{dist}}|$)：

```text
Distractors
  500 ┤   🟢        🔴        🔴        🔴        🔴
  100 ┤   🟢        🟡        🟡        🟡        🟡
   50 ┤   🟢        🟡        🟡        🟡        🟡
   10 ┤   🟢        🟡        🟡        🟡        🟡
    0 ┤   🟢        🟢        🟡        🟡        🟡
      ┼─────────┴─────────┴─────────┴─────────┴─────────
        100       500       1K        3K        10K
                            Delay (Δt)

Legend:
  🟢 GREEN   = Reliable (Recall >= 80% and Precision >= 80%)
  🟡 YELLOW  = Partial / Marginal (30% <= Recall < 80%)
  🔴 RED     = Failure Boundary (Recall < 30% or Precision < 30%)
```

### 叠加第三维度 $Z = \text{Causal Chain Depth}$：
- $L = 2$ 步 (`A -> D`): 🟢 GREEN (100% 召回 / 100% 精确)
- $L = 3$ 步 (`A -> B -> D`): 🔴 RED (0.0% 召回，当前架构硬性失效断点)
- $L \ge 4$ 步 (`A -> ... -> D`): 🟡 YELLOW (33.3% 召回，临界阻尼传播)

---

## 8. Continuum 原型能力矩阵 (Capabilities & Failure Boundaries)

```text
                         Continuum Current Prototype

Direct delayed cause             ██████████  Strong (100.0%)
Short/medium delay (Δt <= 500)   ██████████  Strong (100.0%)
Long delay (500 < Δt <= 3K)      ███████░░░  Conditional (66.7%)
Cold candidate recovery          ███████░░░  Conditional (66.7%)
False causal rejection           ██████░░░░  Moderate (NC2/Distractors)
Distractor resistance (>= 500)   ░░░░░░░░░░  Failure Boundary (0.0%)
Multi-hop causal attribution     ███░░░░░░░  Failure Boundary (0-33.3%)
Very long bounded memory (>10K)  ████░░░░░░  Physical Horizon Boundary
```

---

## 9. 首席架构裁决与下一阶段推进准则

1. **严禁现阶段跃进至 Phase 4 (Sparse Event Memory):** 不准在机制缺陷尚未定位时盲目堆砌 Vector DB、Causal Graph、Phase Attention 或 GPU 优化。
2. **严禁修改核心打分算法与重调参数:** 必须保持所有失败实验原样呈报。
3. **技术路线收敛:** 下一步的架构设计必须**严格针对 Mission 2.8 已经明确证明的两大失效模式**（多跳因果递归断裂、大规模语义诱饵遮蔽）提供定向数学方案。
