# FluxKernel 设计增补 v1.2：合同原生的规格模型（Contract-native Spec）

> 本文档是交接方案的第二个增补（接续 v1.1）。来源：一份关于"为什么形式化卡在抽象而不在证明器"
> 的分析文档。其论点经核对成立，并直接改写本系统的 spec 数据模型。
>
> 一句话：**v1.0 的 `Node.spec` 是自由字典；v1.2 起，spec 是合同（contract）。
> 内核的 compose 核验从"简单合取"升级为"有损耗物理组合规则"。**

---

## 17. 为什么必须改：spec 不是属性包，是合同

原文档的三个核心论断，逐条对应本系统的改造：

1. **"专家方案里大部分内容不是定理，而是经验/折中/隐含环境/未写清的接口"**
   → spec 必须把五类对象分槽存放，不允许混在一起：
   **Goals（可否证的目标）/ Semantics（操作定义）/ Assumptions（环境假设）/
   Contracts（接口合同）/ Forbidden（禁止项）**。答不清的不许进基线——
   "那是未结算的风险，不是已验证的方案"，这正是我们 `fk sorry` 的语义，现在扩展为
   `fk risks`：未结算风险清单。

2. **"抽象不是简化图纸，是换坐标系：从'盒子里有什么'换成'盒子对外承诺什么、
   要求环境提供什么'"** → refine 算子的 flow-down 不再只下传参数预算，
   而是下传**合同义务**：子节点的 Assume 必须由父节点的 Guarantee（或兄弟节点的
   Effluent 上界 + 介质容量）覆盖。

3. **"物理接口是有损耗的：合同必须四段——Assume / Guarantee / Budget / Effluent"**
   → 这是本增补最重的一条。软件的 `f: In→Out` 在物理系统里是
   `(y, r, w) = F(u, d, x)`：有用输出 y、占用共享资源 r、回灌副作用 w，
   在扰动 d 和共享状态 x 之下。**r 和 w 从来不是零**。
   因此 spec 的合同段必须是四段式，且 Budget/Effluent 参与组合核验。

## 18. 数据模型改动（§4 的 spec 字段替换为 contract）

```python
Node.spec = {
  "goals":      [ {"id": "g1", "stmt": "单台飞控失效时仍可在包线内改平着陆",
                   "falsifiable": True, "measure": "..."} ],   # 必须可否证+可测
  "semantics":  ["term-digest", ...],    # 引用的操作定义（见 §20 语义登记处）
  "assumes":    [ {"id":..., "stmt":"输入 22–29V，负载阶跃 ≤ I_step", "bounds":{...}} ],
  "guarantees": [ {"id":..., "stmt":"输出 28V±2%，纹波<ε", "bounds":{...}} ],
  "budget":     { "power_w": ("<=", 30), "mass_g": ("<=", 800),
                  "bandwidth_hz": ("<=", 100), "volume_mm3": ("<=", ...) },
  "effluent":   { "heat_w": ("<=", 4), "harmonic_a": ("<=", 0.5),
                  "vibration_n": ("<=", ...) },                # 回灌共享介质的上界
  "forbidden":  [ {"id":"f1", "stmt":"两套舵机反向同时满偏",
                   "check": "reachability|inspection|test"} ],
  "not_responsible": [ "液压源压力维持", "对端协议版本协商" ],   # 显式免责清单
  "time_scale": "control-tick|monitor-window|mission|thermal-min|fatigue",  # 单一或已分层
}
```

五条"相对客观性"判据（输入空间有界 / 保证可判定 / 故障模式枚举 /
时间尺度单一 / 自由参数有范围或有检测）实现为 **`fk lint`** 的五条规则：
缺任何一项，节点可存在但状态永不高于 `proposed`，并列入 `fk risks`。
**写不出操作定义的词，禁止进入 spec**（lint 规则 L4：spec 中所有名词必须
resolve 到语义登记处的 digest）。

## 19. 共享介质是一等节点（新 role: Medium）

原文档最锋利的一刀："两个作动器各干各的，其实都在写同一根母线和同一块壁板。"
软件把共享内存藏进 API；物理系统的共享内存是**场和介质**——直流母线、液压油、
主结构、舱内热场、电磁环境、时间基准。

实现：

- 新 role `Medium`：介质节点，spec 承载 `{capacity（容量/阻抗/保护语义）, state（共享状态变量）,
  degradation（退化语义）}`；
- 普通节点的 `budget` = 对某 Medium 的抽取声明；`effluent` = 对某 Medium 的回灌声明
  （spec 中通过 `medium: <digest>` 引用介质节点）；
- **介质的账本是派生数据**：`fk ledger <medium>` 汇总所有引用者的 budget 之和
  与 effluent 之和，对照 capacity——超容量 = 义务 `medium-capacity` 不成立；
- 于是"耦合"不再是口头默契：耦合路径 = DAG 中经过介质节点的边，**显式、可审计、可定价**。
  与 v1.1 的 integrate 联动：合并若干子系统时，其 budget/effluent 的并集一致性
  正是 `interface-union-consistent` 义务的实质内容。

## 20. compose 核验规则升级：从合取到有损耗组合

主方案 §7 的 compose 核验原先是"子义务全绿 → 父义务履行"（简单合取）。
原文档证明物理上不成立（两个合格变换器叠加谐振、两个合格散热同舱回流短路）。
v1.2 起 compose 生成四类组合义务，替代简单合取：

| # | 组合规则 | 义务模板 | 判定方式 |
|---|---|---|---|
| C1 | **合同接得上**：每个消费者的 Assume 被对应提供者的 Guarantee 覆盖 | `ag-coverage` | 区间/谓词包含检查（可机判） |
| C2 | **预算可加（带裕度）**：Σ budget_i ≤ capacity × (1 − margin)，不许用标称值相加 | `medium-capacity` | 介质账本算术 |
| C3 | **排放可吞**：下游 Assume 的上界 ≥ 上游 Effluent 的最坏值（非典型值） | `effluent-absorption` | 区间比较 |
| C4 | **时间尺度分层**：同一合同内的量必须同尺度或已显式分层 | `time-scale-stratified` | spec.time_scale 标签检查 |

C1–C4 全部可判定（区间算术/标签检查），仍属"有限协议命题"，**不违反
"内核不证物理"的边界**——物理正确性仍由 evidence tier 承担，内核只管合同算术。
共享动力学（母线阻抗、弹性模态、热网络）按 §19 建成 Medium 节点后，
局部合同只对介质模型成立——这是"共享动力学"规则的内核形态。

## 21. 硬合同 vs Pareto：义务分类，优化被挡在内核外

原文档："形式化管硬约束是否满足、模型是否自洽；不负责在 Pareto 面上选点。"
这与 v1.1 §15 的选择完全一致，现在固化为义务分类：

```python
Obligation.class ∈ {
  "hard",       # 可判定：合同算术、禁止态、协议/离散性质 → 内核/bench 机检
  "soft"        # 不可判定为真，只可比优劣：重量/成本/油耗 → 进 evaluate 证据向量
}
```

- `hard` 义务未履行 → 边 rejected（fail-closed）；
- `soft` 指标不进义务，只进证据向量，供策略层（GA/MAP-elites/总师）选点——
  **"优化找点，合同守门"**就是 `fk evolve` 与 `fk verify` 的分工；
- 两个硬目标互斥 → 不是优化问题，是需求错误：compose 的 C1 核验会把它暴露为
  合同冲突（矛盾区间），在详细设计之前爆掉——这是证明器对总师的真正服务。

## 22. 提取工作流：把专家脑子里的"一坨"抠成对象

原文档的六步追问（先写失败 / 操作定义 / 沿数据-能量-控制三流切合同 /
经验尺寸改带条件不等式 / 显式免责清单 / 只对合同形式化）实现为引导式命令：

```bash
fk elicit <node>      # 交互式（或 LLM 驱动）按固定顺序追问，产出五类对象
```

六步各对应一个 spec 槽位：①最坏十件事 → goals+forbidden；②关键名词 → semantics
登记处条目；③三条流交界 → 模块边界+budget/effluent；④经验参数 → 带前提的不等式
（"对哪个指标/什么扰动谱/越过哪个阈值/谁检测"四问齐全才收）；⑤不负责清单 →
not_responsible；⑥接不上的口子 → 记为 risk（不抹平）。

**这正是 LLM 在系统里的第一位工作**：elicitation 提示链 = Draft 算子的前置形态；
专家（或用户模拟器，对应你 FULL PRSI 笔记里的 Qwen 用户模拟）只需回答追问，
产物直接是合同化 spec。ROI 分层（模式管理/仲裁/电源时序/总线协议先形式化；
气动细节/工艺/工效保持半形式化）= obligation.class 的 hard/soft 分配指南。

## 23. 语义登记处（glossary）

新对象类型 `term`：操作定义（"受控"=过载/迎角/指示空速落在某集合；"总线隔离"=
故障注入后哪些变量不可观测）。内容寻址，spec 按 digest 引用。
**语义一含糊，后面所有证明都在偷换概念**——因此 term 的 digest 变化会使引用它的
所有 spec 的派生证据失效（与 v1.1 的 `plant-model-current` 同一失效机制：
`term-current` 义务）。

## 24. 验收测试新增

17. **四段合同**：含 budget/effluent 的两节点 compose，C1–C4 义务正确生成与判定；
    介质账本超容量时 `medium-capacity` 失败且边 rejected；
18. **矛盾暴露**：两个互斥硬约束的 compose 在 C1 报合同冲突（而非等到详细设计）；
19. **lint 闸门**：五条客观性判据缺一的节点无法 promote；spec 中未登记名词被 L4 拒收；
20. **elicitation**：`fk elicit` 对一个示例子系统走完六步，产出五槽位齐全的合同化 spec，
    且"接不上的口子"出现在 `fk risks` 而非被抹平。

## 25. 对交接方案的改动清单（v1.2）

| 章节 | 改动 |
|---|---|
| §4 Node.spec | 自由 dict → 合同 schema（goals/semantics/assumes/guarantees/budget/effluent/forbidden/not_responsible/time_scale） |
| §3.2 角色 | 增 `Medium`（共享介质节点，账本派生） |
| §4 objects | 增 `term` 对象类型（语义登记处）；Obligation 增 `class: hard|soft` |
| §7 compose | 简单合取 → C1–C4 组合义务模板；`integrate` 的一致性义务 = budget/effluent 并集 + C1–C4 |
| §6 CLI | 增 `fk elicit` / `fk lint` / `fk risks` / `fk ledger <medium>`；`fk goals` 输出增风险列 |
| §11 测试 | 增 17–20 |
| 不变 | L0/L1 存储、digest 纪律、生命周期、fail-closed **仍零改动**——合同是数据，组合规则是义务模板 |
