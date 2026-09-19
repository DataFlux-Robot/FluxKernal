# FluxKernel 设计增补 v1.1：局部集成 / 本体-控制 co-design / 选择压力与遗传优化

> 本文档是 `fluxkernel_implementation_plan_v01.md`（下称"主方案"）的增补，编号接续主方案。
> 回答三个承压问题，每个给出：机理分析 → 新增机制（数据结构/算子/CLI）→ 验收测试。
> 共同主题：**分解树只是计划，DAG 才是现实**。三个能力都是"DAG 相对于树"的兑现。

---

## 13. 局部集成：方案切换 / 局部路径调整 / 局部流程合并

### 13.1 问题

拆解到一半发现市场上能买到多功能集成件（如"八合一/十二合一"电驱），
可以把原先规划为多个子系统的分支**合并成一个节点**。这要求：
一个节点同时关闭来自**不同子树**的多个 goal；原先的子树计划不删除（可回退）；
合并波及工艺树（机加工序减少、装配工序变化）。

### 13.2 机理：这在内核里是什么

- 分解产生的是树；集成产生的是**菱形（diamond）**——一个节点有多个来自不同子树的父。
  内核底层本来就是 DAG（边允许多输入、节点可被多条边引用），所以集成不需要新存储结构，
  需要的是**语义层的新算子与义务记账**；
- Lean 对应物：**一条引理同时关闭多个 goal / `let` 共享子项**。集成件就是被多个父 goal
  共享的公共子项；
- LIVRPS 对应物：集成件以 **reference/payload 弧**接入（引用外部目录/供应商件，不重建），
  它对多个子系统规格的满足 = **字段级合并**（多个 flow-down 约束集的并集 + 一致性检查）；
- 扩散视角：这证明精化算子**非单调**——不仅拆小，也能合并。这正是用户笔记里
  "不只是精化，还有重新抽象"的具体形态。

### 13.3 新增机制

1. **新算子 `integrate`**（compose 的变体）：
   - 前置条件：输入节点集可来自不同子树；各自的 flow-down 约束并集必须一致
     （一致性检查 = 新义务 `interface-union-consistent`）；
   - 输出：一个节点 + 一张 **goal 覆盖表（coverage map）**：`{goal_digest: 由本节点的哪项证据关闭}`；
   - 义务：对被关闭的**每一个**祖先 goal 分别核验（不是只对公共祖先）；
2. **非破坏切换**：原分解子树通过 `abstract` 标记 superseded，完整保留（旧方案的证据
   仍是资产）；集成方案是新分支。切换 = 新增边，不是改写历史；
3. **局部路径调整**：子树替换 = abstract 到公共祖先 + 新 refine 分支，未受影响的子树
   被新分支**按 digest 原样引用**（结构共享，类 git tree 复用），不重算；
4. **流程合并的传播**：integrate 发生在 Part/System 层后，其 Process 子树触发
   `replan-process`（规则：被合并零件的机加工序作废，新增集成件装配/测试工序），
   同样是新增边而非修改。

### 13.4 CLI

```bash
fk integrate byd-8in1 --closes ac-v1/motor,ac-v1/inverter,ac-v1/reducer \
   --from catalog/byd --match "8in1-edrive voltage>=400V"
# 输出：coverage map（3 个 goal 被哪些证据关闭）+ 一致性义务结果
fk status   # 原三个子系统分支显示 superseded-by: byd-8in1，证据保留
```

### 13.5 验收测试（并入主方案 §11）

9. **多 goal 关闭**：integrate 一条边关闭 ≥2 个不同子树的 goal，coverage map 正确，
   每个被关闭祖先的义务逐一核验；
10. **非破坏**：superseded 子树可被 `fk why` 完整回溯；`fk verify` 全库复检通过；
11. **结构共享**：abstract+rebranch 后，未受影响子树的 digest 不变、不发生重新求值。

---

## 14. 本体-控制 co-design

### 14.1 问题

本体（形态/结构）与控制（策略/软件）需要联合设计，而不是"先定本体再调控制"。

### 14.2 机理

- FLUXmeme 已经给出答案：**一个节点有 BODY / MIND 两个 facet**（机身与心智同体）。
  co-design = 同一个 System 节点下 BODY 子树与 MIND 子树的**耦合精化**；
- co-design 的经典失败模式是"控制器对着过时形态调的"。内核给出结构性解法：
  **模型-本体身份链接**——控制器的被控对象模型引用本体节点的 digest；
  本体一旦被新边改变，引用旧 digest 的控制证据自动失效（义务
  `plant-model-current` 不成立）。"控制是否仍匹配当前本体"成为可机检命题；
- 联合目标求解 = 一条 **co-design 边**：输入同时来自 BODY 与 MIND 子树，
  transform 为联合 grounding（形态参数与控制参数同时作为元变量求解），
  eval 为**联合仿真**（动力学模型取 BODY 当前投影 + 策略取 MIND 当前投影），
  证据同时覆盖两侧义务。

### 14.3 新增机制

1. **节点 facet 维度**：`Node.facet ∈ {BODY, MIND}`（默认 BODY）；
   MIND 节点载荷 = 控制器结构/策略参数/模型引用，ground = 仿真/实机证据；
2. **`plant_ref` 字段**：MIND 节点 spec 中必须声明 `plant_ref: <BODY节点digest>`，
   L1 在每次 commit 涉及该 MIND 子树时核验 `plant-model-current`；
3. **新 transform `co-ground`**：BODY×MIND 联合参数求解（共享元变量；
   例如腿长同时进几何与控制器模型）；**新插件 `cosim`**：联合仿真评测，
   证据 tier 按仿真/实机分级；
4. co-design 迭代 = BODY 与 MIND 交替/联合 refine，DAG 自然记录交错历史。

### 14.4 CLI

```bash
fk node ctrl0 --role Component --facet MIND --kind gait-controller \
    --spec "plant_ref=<leg-body-digest>"
fk refine leg-assy --via co-ground --with ctrl0 --arg objective="energy*0.6+stability*0.4"
fk eval leg-assy --with cosim --fidelity 2 --expect "tracking-error<0.05"
# 本体变更后：
fk goals   # 自动浮现: ctrl0 [plant-model-current] FAILED — 控制证据失效,需重新 eval
```

### 14.5 验收测试

12. **身份链接失效检测**：BODY 节点参数变更后，`fk goals` 必须报出依赖旧 digest 的
    MIND 证据失效义务；
13. **联合接地**：co-ground 边同时坍缩 BODY 与 MIND 参数，证据覆盖双方义务。

---

## 15. 选择压力与遗传优化（方案 + 加工方案）

### 15.1 问题

后续要引入选择压力，用遗传算法优化设计方案与整体加工方案。

### 15.2 机理

- 内核早已备妥两处挂钩：**VariantSpace**（节点内未坍缩方案域）与
  **DAG 分支**（abstract/refine 产生的替代支系）。GA 的种群 = 这两者的实例化集合；
- 关键升级：因为分解选择本身是 DAG 中的边，**GA 的搜索空间包含拓扑而不只是参数**——
  变异算子可以合并（integrate）/拆分（decompose）/换分支（abstract+refine），
  这意味着遗传搜索能自己发现"八合一"式集成机会，这是树状工具架构上给不出的；
- 与 FULL PRSI 笔记的对应逐字成立：Draft=初代种群生成；Improve=变异边；
  Debug=诊断码驱动的修复边；Crossover=两分支 compose 合并边；
  **后验选择（SEAL 原则）= 只有 eval 证据装订后才允许 promote**，内核 fail-closed 天然执行；
- 适应度不做单标量化：保留证据向量（成本/质量/takt/能量/失败率），
  选择算子（NSGA-II / MAP-elites 档案）在内核之上的策略层——对齐 bench
  "vector scoring, leaderboard policy belongs above the kernel" 的立场；
- **谱系即家谱**：每个候选的父代记录在边的 inputs 里，系谱完全可审计，
  token/FLOP/GPU 时间进 resources——满足笔记里轨迹保留的全部字段。

### 15.3 新增机制

1. **策略层命令（不进内核）**：`fk evolve <goal> --pop N --gen M --select-by cost,mass
   --archive map-elites` —— 驱动循环：实例化变体 → eval → 选择 → 变异/交叉边 → 下一代；
2. **变异算子库**（都是普通边，无特权）：参数扰动 / 变体重选 / integrate / decompose /
   abstract-rebranch / 工艺替换（process 子树的同构变异）；
3. **MAP-elites 档案**：以行为描述子（如质量×成本×产能）为格的变体档案，存为
   特殊 catalog 条目（`kind=archive`），可被 `exact` 检索复用——**进化结果沉淀为库**，
   这就是资本 K 的增长方式；
4. 加工方案优化复用同一机制：Process/Line 子树的变体空间走同样的 evolve 循环。

### 15.4 CLI

```bash
fk evolve wing-v3 --pop 32 --gen 50 \
   --mutate "param-perturb:0.1, integrate:0.05, process-swap:0.1" \
   --select-by mass,cost,takt --archive map-elites:4x4
fk goals   # 每代的最佳候选、档案覆盖率、rejected 失败轨迹全部可见
```

### 15.5 验收测试

14. **系谱可审计**：evolve 跑 ≥3 代，任一子代的父代链可通过 `fk why` 完整回溯，
    resources 记录完整；
15. **拓扑变异**：变异算子集中包含 integrate/decompose，且发生过至少一次拓扑变异
    的 run 中 DAG 复检（`fk verify`）通过；
16. **档案沉淀**：evolve 结束后 archive 条目可被 `fk exact --from archive` 命中并关闭新 goal。

---

## 16. 对主方案的改动清单（交接用）

| 章节 | 改动 |
|---|---|
| §4 Node | 增 `facet: "BODY"|"MIND"`（默认 BODY）；MIND 节点 spec 必含 `plant_ref` |
| §4 Edge | 增 `coverage: {goal_digest: evidence_ref}` 字段（integrate 使用，默认空） |
| §7 算子表 | 增 `integrate`；`evaluate` 增 expect 断言核验说明；义务表增
  `interface-union-consistent` / `plant-model-current` |
| §6 CLI | 增 `fk integrate` / `fk evolve` / `--facet` 参数 |
| §8 插件 | 增 `cosim`（联合仿真）、`catalog/byd` 等集成件条目示例、archive 条目格式 |
| §11 测试 | 增补第 9–16 项 |
| 不变 | L0/L1 存储与 DAG 提交纪律**零改动**——三个能力全部落在语义层/策略层，
  这本身验证了"小可信基"设计的正确性 |
