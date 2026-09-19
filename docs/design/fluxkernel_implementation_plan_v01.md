# FluxKernel 实现方案（开发交接版 v1.0）

> **本文档用途**：交给开发 agent 直接实施的完整方案。自包含，不依赖任何对话上下文。
> 读完后应能：搭起仓库、实现内核、跑通抽象案例、通过验收测试。
>
> **⚠️ 必读附件**：
> - `fluxkernel_design_addendum_v11.md`（v1.1：局部集成 integrate / co-design / 遗传优化）
> - `fluxkernel_design_addendum_v12.md`（v1.2：**合同原生规格模型**——spec 从自由字典
>   改为五槽位合同 + 四段式 Assume/Guarantee/Budget/Effluent；新增 Medium 角色；
>   compose 核验升级为 C1–C4 有损耗组合规则；obligation 分 hard/soft）。
> 两份增补的改动清单分别见其 §16/§25——L0/L1 内核均零改动。

---

# 1. 目的

## 1.1 要造什么

**FluxKernel**：一个 CLI 形式的 CAD + MBSE 设计系统内核——可以粗略理解为
"命令行形态的 SolidWorks × MBSE × git × Lean 战术证明器"。

用户（人类工程师或 LLM agent）从一句模糊需求（如"我想飞，往返 A 到 B"）出发，
通过**逐层拆解**（单质点模型 → 多部件方案 → 子部件 → 零件 → 工艺 → 产线环节 →
机床/工位 → 机床的零件 → …），递归展开直到所有叶子都是**标准件（电机/螺丝等
目录件）或外购件**；然后沿拆解路径**逐层回装验证**，回到顶层需求。

## 1.2 它服务的上层目标（为什么这样设计）

本内核是 PRSI（Physical Recursive Self-Improvement）生态的物理构造内核：
每一次构造动作都是一条**可审计的生产边**（带证书、资源向量、身份链接），
整条设计轨迹可被独立的 Lean 验证核（MechanogenesisBench）复算。
因此内核的三个不可妥协的性质：

1. **一切身份即内容哈希**（digest），谱系精确可链（`o_i = t_{i+1}` 为 digest 相等）；
2. **每条边携带证书与资源向量**，fail-closed（义务未履行 = rejected，永不可被下游引用，
   但永久保留为证据）；
3. **内核可信基极小**（不含几何/数值知识），所有重计算在可插拔的求解插件层。

## 1.3 反 scope（明确不做）

- 不做 GUI / 渲染器 / 3D 交互（预览 = 导出 STL/STEP + 外部查看器 + watch 模式）；
- 不做完整仿真平台（仿真是 evaluate 边调用的外部引擎，证据按 tier 登记）；
- 不重写 B-rep 几何内核（用 OCP/OpenCascade 作为首个几何后端，隔离在插件层）；
- 不做 URDF/USD 工具链（那是上层工作台的事，内核只投影）。

---

# 2. 设计哲学：与 Lean 的对应关系

本系统的交互范式是 **Lean 战术证明在物理设计上的同构**。"逐层拆解到标准件"
在形式上**就是**一个 tactic proof。开发时每个模块都应问自己"这在 Lean 里对应什么"。

| Lean | FluxKernel | 实现落点 |
|---|---|---|
| 命题/类型 `P` | **goal**：待实现节点的规格 spec | Node.spec |
| 项 `t : P` | 已接地设计（参数全坍缩、证据齐备） | Node.ground ≠ None 且义务全履行 |
| 战术 tactic | **refine / compose / abstract / eval / exact / procure / manufacture** | 算子引擎（L3），每战术 = 一条 Edge |
| 子目标 subgoals | 分解出的子节点 | refine 边的输出节点集 |
| `exact lemma` | **标准件/库设计直接关闭 goal** | exact 算子 + 目录库检索 |
| Mathlib | **标准件与已验证设计库**（资本 K 的载体） | catalog/ 目录，条目带规格类型+证据tier |
| 战术状态 goals view | `fk goals`：未关闭 subgoal / 未坍缩参数 / 未履行义务 | CLI 中心命令 |
| `sorry` | **未坍缩参数（洞）**，允许存在、被追踪、传染标记依赖它的结论 | Node.params 中的 `["param", name]`；`fk sorry` |
| 元变量 `?m` | 参数态属性 | 约束求解 = 元变量赋值 |
| 项模式 vs 战术模式 | **.fcad 完整脚本（LLM 面） vs CLI 逐条命令（人面）** | 同一内核检查，双主角 |
| 阐释器 elaborator | .fcad → 内核对象 | interface/fcad.py |
| 内核 kernel | L1：Node/Edge/Cert/DAG，目标 <5k 行，无第三方依赖 | core/ |
| 终止性 well-founded | 递归拆解必须终止于目录命中/外购 | realize 组合子的停止规则 |
| 类型类推断 | 目录检索"找一个 torque≥50Nm 的电机" | `fk search` |
| 公理 axioms | 物理/计量证据：不证物理，只登记来源与 tier | Evidence.tier + 假设账本 |
| 战术组合子 `<;>` `repeat` | 组合战术：`realize = repeat (decompose <;> try-exact <;> eval)` | CLI realize 命令 |

**错误层级（直接用作 LLM 强化学习的 reward 阶梯）**：
语法错 < 类型错（level/role 不合法）< 义务未履行（obligation undischarged）
< eval 指标不达标 < 物理证据缺失。

---

# 3. 总体架构

## 3.1 分层（依赖只允许自上而下；L1 不得依赖 L2；L2 插件互不依赖）

```
L4 接口面 interface/   .fcad 解析/打印 · CLI · 类型化诊断码 · （后续 MCP）
L3 语义面 semantics/   算子引擎(refine/compose/abstract/evaluate/exact/procure/manufacture)
                       递归角色本体 · 变体空间 · goals/sorry 视图
L2 求解面 solvers/     插件注册表驱动：sketch2d · feature3d(OCP) · mate · dfam ·
                       mission(低保真任务分析) · process · line · catalog
L1 核     core/        Node/Edge/Certificate/ResourceVector · DAG 提交纪律 ·
                       生命周期状态机 · promotion 判定   ← 可信基，零几何
L0 存储面 store/       内容寻址对象库 · append-only 边日志 · 名字索引   ← 哑存储
```

## 3.2 递归角色本体（**注意：不是固定层级表**）

早期草案用固定八级 Intent→…→MetaLine，已被否决。正确模型：

- 节点携带 `role ∈ {Intent, System, Component, Part, Process, Line, Resource}`，
  **不携带全局层号**；"第几层"由 DAG 中从根到它的路径决定；
- **Resource（机床/工位）与 System（飞行器）是同构对象**：当 Line 节点的需求
  被 refine 出 Resource 规格、且该 Resource 被当作 System 继续拆解时，
  PRSI 递归边自然成立——"造机器的机器"是同一类型在不同递归轮次的实例；
- 终止规则内建于算子：`Part` 节点的 realize 方式三选一——
  `procure`（标准件/外购，终止）/ `manufacture`（转向工艺树）/ `decompose`（继续拆）。

## 3.3 边的生命周期（fail-closed）

```
proposed → executed → evidenced → verified → promoted
     └──────── 任何失败 → rejected（永久保留为证据，不可被下游引用）
```

- `executed`：L2 插件跑完，产出投影+原始证据；
- `evidenced`：证据装订成证书，评测者身份写入（独立于执行者）；
- `verified`：L1 本地有限检查全过（身份链接、义务履行、预算非负闭环）；
- `promoted`：verified 且有证据 → 允许被下游边引用为输入。

---

# 4. 核心数据结构（L1，冻结优先级最高）

所有对象以**确定性 JSON**（sorted keys, 紧凑分隔符, UTF-8）为 canonical 字节；
digest = `fk1:<kind>:<sha256(canonical)>`，域分隔。
**lineage 是元数据，永不进入 digest**（由边日志 + 索引 `@lineage/<node>` 派生）。

```python
Node = {
  "role":     "Intent|System|Component|Part|Process|Line|Resource",
  "kind":     str,               # 自由类型名，如 "aircraft","wing","motor","milling-op"
  "spec":     dict,              # 规格=goal 类型：约束、接口、指标（可含参数域）
  "params":   dict,              # 参数态：值 或 ["param", name]（= sorry 洞）
  "variants": list,              # 未坍缩的方案空间
  "ground":   dict | None,       # 求值投影：{type, blobs:{step,stl}, volume_mm3, mass_g,
                                 #           bbox, com, construction:{...可重放构造}}
  "evidence": [ {"solver":str, "tier":int, ...} ],
  "supersedes": [node_digest],   # abstract 回退时标记
}

Edge = {                         # PIPE 形状：ProducedBy(output; inputs, transform)
  "op":      "refine|compose|abstract|evaluate|exact|procure|manufacture",
  "inputs":  [node_digest],      # t_k
  "transform": {"name": str, "args": dict},   # δ_k
  "output":  node_digest,        # o_k
  "certificate": {
     "obligations": [ {"id":str, "prop":str, "holds":bool, "checker":str, "detail":str} ],
     "evaluator": str,           # 评测者身份（独立于执行者）
     "evidence":  [...],
  },
  "resources": {"time_s":0.0,"energy_j":0.0,"material_g":0.0,
                "cost":0.0,"human_s":0.0,"failures":0},   # 共同祖先增量记账
  "state":   "proposed|executed|evidenced|verified|promoted|rejected",
  "reason":  str,                # rejected 时的诊断码+说明
}
```

**诊断码**（typed diagnostics，LLM 训练面）：`S1`语法错 `T2`类型错 `U1`欠约束
`O2`过约束 `I1`输入缺失 `I2`输入非节点 `I3`输入非 promoted `C0`义务未履行
`E1`求值失败 `M1`指标不达标。

---

# 5. .fcad DSL 规范（LLM 面；项模式）

S-表达式，五个顶级构造子，无变量无控制流。数字即 atom，字符串用双引号，
参数引用写 `(param <name>)`。

```lisp
;; 顶级形式
(node  <name> :role <R> :kind <k> :spec (<...>) :params (<...>) :variants (<...>))
(edge  <name> :op <refine|compose|abstract|evaluate|exact|procure|manufacture>
       :in (<node-ref> ...) :out <name>
       :transform (<tname> :key val ...)
       :resources ((:time-s 2.5) (:cost 0)))
(goal  <name> ...)                       ;; = (node ... :role Intent/System)
(eval  <name> :target <ref> :with <solver> :fidelity <int> :expect (<...>))
(exact <name> :target <ref> :from catalog :match "查询串")
```

执行语义：`fk run script.fcad` 顺序执行，每条形式 = 一次算子调用 = 一次 DAG commit；
任一失败 → 该边 rejected，**脚本继续**（失败轨迹是训练资产），退出码非零。

## 5.1 草图 spec（sketch2d 插件的输入）

```lisp
:spec (sketch
  (pts (p0 (param hw) 0) (p1 (param hw) (param hh)) (p2 0 (param hh)) (p3 0 0))
  (constraints (fix p3 0 0) (dist p0 p1 20) (dist p1 p2 40) (horiz p0 p1) (vert p1 p2)))
```

---

# 6. CLI 命令面（人面；战术模式）

命令名：`fk`。状态在 `<cwd>/.fk/` 对象库（类 git）。每条写命令 = 一条边。

```bash
# 库与会话
fk init                          # 建 .fk/（objects/ blobs/ edges.log index.json）
fk run <script.fcad>             # 执行脚本（项模式）
fk goals                         # ★ 战术状态：未关闭 subgoal/洞/未履行义务
fk sorry                         # 全部未坍缩参数及其传染的结论链
fk goal <ref>                    # 聚焦 goal（显示 flow-down 来的上下文约束）
fk next                          # 下一个最浅未关闭 goal

# 战术（每个生成一条边）
fk node <name> --role R --kind k --spec "..."
fk refine <goal> --via <transform> [--into a,b,c] [--arg k=v]...
fk eval  <goal> --with <solver> --fidelity N --expect "range-margin>0"
fk exact <goal> --from catalog --match "torque>=50Nm"
fk procure <goal> --from <catalog>
fk manufacture <goal>            # Part → Process 转向
fk compose <goal> [--roll-up k=v]...
fk abstract <goal> --reason "..." --back-to <ancestor>

# 组合子：主循环
fk realize <root> --until standard-part \
   --strategy "decompose <;> try catalog-exact <;> eval --fidelity ramp"

# 检视
fk check <ref>                   # goal 的规格类型 + 义务履行情况
fk graph [--dot]                 # DAG 可视化（文本/Graphviz）
fk why <ref>                     # 沿谱系回溯到 Intent
fk log                           # 边日志
fk status                        # 全树证书状态汇总
fk search "<查询>"                # 目录实例检索
fk show <ref> [--json]

# 导出与对接
fk export <node> --step x.step --stl x.stl
fk trace --out <dir>/            # MechanogenesisBench 证书包（见 §9）
fk verify                        # 全库 fail-closed 复检（重放检查所有边）
fk watch <script.fcad>           # 保存即重建 + 浏览器预览刷新（three.js 静态页）
```

`<ref>` = 名字（可变引用，存 index.json）或 digest（身份）。

---

# 7. 算子语义（L3 引擎）

所有算子共享执行骨架：

```
execute(op, inputs, transform):
  1. 前置条件（按 op 查表）——失败即 rejected，诊断码注明
  2. 继承不变量（flow-down：父 spec 的义务/接口下发）
  3. 调 L2 插件执行 transform → (node_fields, evidence, obligations)
  4. 附加结构性义务（input-verified / role-transition-legal / budget-closed）
  5. 装订证书 → DAG.commit（生命周期推进，fail-closed）
```

| 算子 | 前置条件 | 生成义务 | Lean 对应 |
|---|---|---|---|
| `refine` | 输入 verified+；role 转移合法（System→Component→Part 等） | flow-down 预算/接口保持 | refine 战术 |
| `compose` | 所有子输入 promoted | roll-up 指标核验父义务 | 回装/eliminator |
| `abstract` | 无（永远允许回退） | 标记 supersedes，旧链保留 | 回退重开分支 |
| `evaluate` | 输入存在（可有洞） | 证据 tier 标注；expect 断言核验 | `native_decide` 的弱化版 |
| `exact` | 目录命中条目规格 ⊇ goal 规格 | 库条目证据 tier 继承 | `exact lemma` |
| `procure` | 目录/供应商条目存在 | 证据 tier=procured（≠verified） | 公理引入 |
| `manufacture` | 输入 role=Part 且非标准件 | 产出 Process 族新 goals | 转向新证明义务族 |

**goals 视图**的实现：`fk goals` = 扫描 DAG，输出三类清单——
① 无 promoted 出边的非叶子节点（未分解/未关闭）；
② 所有 `params` 中残留的 `["param", name]`（洞）及其下游依赖；
③ 所有 rejected 边（失败档案）。

---

# 8. L2 求解插件（契约 + 首批清单）

插件契约：`(input_node_specs: list[dict], args: dict, ctx) -> (node_fields, evidence, obligations)`。
`ctx` 暴露 store（读写 blob）、logger。插件**不可信**：输出必须带证据。

| 插件 | transform 名 | 输入 | 输出/证据 | 后端 |
|---|---|---|---|---|
| sketch2d | `ground-sketch` | 部分约束草图 spec | 接地草图 + 残差 + dof | scipy least_squares |
| feature3d | `extrude / revolve / boolean` | 接地草图节点 | B-rep 投影：STEP/STL blob digest + 体积/质量/质心/bbox + 可重放 construction | OCP |
| mission | `point-mass-model / mission-analysis` | 任务 spec（航程/载荷） | 低保真性能估算（Breguet 级） + tier-0 证据 | 纯 Python |
| dfam | `dfam-check` | B-rep 节点 + 工艺类型 | 壁厚/悬垂/包围盒证据 | OCP mesh + STL 解析 |
| mate | `assemble` | 部件节点 + 放置/配合 | 装配位姿 + 干涉检查（Common 体积>ε） | OCP |
| process | `process-plan` | Part 节点 + 工艺库 | 工序序列 + 资源估计 | 规则库（JSON） |
| line | `line-eval` | Process 节点集 + 流约束 | 产能/节拍（min capacity / max takt） | 纯 Python |
| catalog | `catalog-match` | 查询串（"torque>=50Nm"） | 命中条目 + tier | catalog/ JSON 库 |

**B-rep 永不序列化进节点**；节点记录 `construction`（可重放构造描述），
引用 = 节点 digest + 构造路径（谱系命名，参数变化后引用不漂移）。
OCP 用法要点：`BRepBuilderAPI_MakePolygon/MakeFace` 建面 → `BRepPrimAPI_MakePrism/MakeRevol`
→ `BRepAlgoAPI_Fuse/Cut/Common` → `BRepGProp.VolumeProperties_s` 取质量属性
→ `STEPControl_Writer` / `StlAPI_Writer`（先 `BRepMesh_IncrementalMesh`）导出。

---

# 9. 抽象案例：飞机（验收用端到端走查）

开发完成的标准 = 以下脚本能跑通、`fk goals`/`fk why`/`fk trace` 输出正确。

```lisp
;; examples/aircraft.fcad —— "我想飞，往返 A 到 B"
(goal ac0 :role Intent :kind aircraft
  :spec ((route A B) (range-km (>= 2600)) (payload-kg (>= 500)) (cost-wan (< 200))))

;; ── 第 2 步：单质点模型，全参数态（洞），低保真验证 ──
(refine e1 :in (ac0) :out ac-point :transform (point-mass-model)
  :resources ((:time-s 0.1)))
;;   ac-point.params = {mtow: (param mtow), fuel-frac: (param ff), ...}  ← sorry 洞
(eval e2 :target ac-point :with mission-analysis :fidelity 0
  :expect ((range-margin-km (> 0))))    ;; Breguet 级估算 → tier-0 证据

;; ── 第 3 步：展开多部件，约束下传，子系统升保真验证 ──
(refine e3 :in (ac-point) :out ac-v1
  :transform (decompose :into (wing engine nose tail fuselage)
             :flow-down ((mass-budget wing 0.28) (mass-budget engine 0.22))
             :interfaces ((wing-root ← skeleton.wing-attach))))
(eval e4 :target ac-v1/wing :with aero-2d :fidelity 1
  :expect ((lift-to-drag (> 14))))

;; ── 第 4 步：方案坍缩 + 再拆 ──
(refine e5 :in (ac-v1/wing) :out wing-v2 :transform (select-variant cantilever))
(refine e6 :in (wing-v2) :out wing-v3
  :transform (decompose :into (skin tank rib)))
;;   rib 是机加件 → 先给它建几何：
(refine e7 :in (wing-v3/rib) :out rib-sk
  :transform (ground-sketch
    :sketch (sketch (pts (p0 (param hw) 0) (p1 (param hw) (param hh))
                         (p2 0 (param hh)) (p3 0 0))
              (constraints (fix p3 0 0) (dist p0 p1 20) (dist p1 p2 40)
                           (horiz p0 p1) (vert p1 p2)))))
(refine e8 :in (rib-sk) :out rib-solid
  :transform (extrude :height 3 :material aluminum))   ;; OCP → STEP/STL blob + 质量属性

;; ── 第 7~9 步：机加件 → 工艺 → 产线环节 ──
(manufacture e9 :in (rib-solid) :out rib-proc
  :transform (process-plan :into (stock milling-5axis inspection)))
(compose e10 :in (milling-5axis inspection) :out rib-line
  :transform (line-eval :roll-up ((takt-min (<= 12)) (oee (>= 0.6)))))

;; ── 第 10~11 步：产线 → 机床需求 → 机床作为新 System 递归 ──
(refine e11 :in (rib-line) :out mill-req :transform (resource-spec))
(refine e12 :in (mill-req) :out mill-v1 :role System
  :transform (decompose :into (bed spindle cnc-drive)))
(exact e13 :target mill-v1/spindle-motor :from catalog
  :match "torque>=50Nm rpm>=12000")        ;; 标准件关闭 goal, tier=procured
(procure e14 :target mill-v1/m8-screws :from catalog/gb70)

;; ── 回装（V 右腿）：逐级 compose 清算下传义务 ──
(compose e15 :in (bed spindle cnc-drive) :out mill-5axis)
(compose e16 :in (mill-5axis cmm) :out rib-line-v2)
(compose e17 :in (skin tank rib-line-v2) :out wing-assy)
(compose e18 :in (wing-assy engine nose tail fuselage) :out ac-final
  :transform (roll-up ((range-km (>= 2600) :by tier-2-sim)
                       (cost-wan (< 200) :by bom-rollup))))
```

**PRSI 递归边的体现**：若下一代任务的产线引用 `mill-5axis` 节点 digest 作为输入算子，
则 `o_i = t_{i+1}` 成立，`fk trace` 导出的证书包中应出现两条共享该 digest 的链。

预期 CLI 交互片段：

```
$ fk goals
OPEN GOALS (3)
  wing-v3/skin      role=Part    holes: ?skin-thickness
  ac-v1/engine      role=Component  not decomposed
  rib-line-v2/cmm   role=Resource   not realized
HOLES (1): ?skin-thickness  ← blocks: skin, wing-assy, ac-final
REJECTED (1): e4  [M1] lift-to-drag=13.2 < 14 (evidence kept)

$ fk why mill-v1/spindle-motor
spindle-motor ← mill-v1(System) ← mill-req ← rib-line ← rib-solid ← … ← ac0(Intent: 往返 A↔B)
```

---

# 10. 存储与目录结构

```
<workspace>/.fk/            # 对象库（类 .git）
├── objects/fk1_node_*.json # 节点/边 canonical JSON
├── blobs/fk1_blob_*        # STEP/STL 等二进制投影
├── edges.log               # append-only 边日志（每行 {ts, edge, record}）
└── index.json              # 名字→digest（可变引用）；@lineage/<node>→edge

仓库结构（开发目标）：
fluxkernel/
├── core/    canon.py objects.py dag.py          # L1（零第三方依赖，<5k 行纪律）
├── store/   objstore.py                         # L0
├── semantics/ ontology.py operators.py goals.py # L3
├── solvers/ registry.py sketch2d.py feature3d.py mission.py
│            mate.py dfam.py process.py line.py catalog.py   # L2
├── interface/ fcad.py diagnostics.py cli.py     # L4
├── adapters/ mbench.py fluxmeme.py              # trace→bench证书包；→.flux投影
├── catalog/   motors.json fasteners.json ...    # 标准件库（Mathlib 位格）
├── examples/  aircraft.fcad
└── tests/     run_tests.py + golden vectors
```

**mbench trace 包格式**（`fk trace --out`）：`trace.json`（所有边：digest/op/inputs/
output/state/resources）、`certificates/`（每边证书 JSON）、`chain.json`
（共享 digest 的跨代链接记录）、`summary.json`（向量记分：time/cost/material/failures）。
字段命名对齐 MechanogenesisBench 的 canonical IR（digest/lineage/resources/evidence_tier）。

---

# 11. 验证与测试计划（验收门槛）

`tests/run_tests.py` 全绿才算完成。必含：

1. **黄金向量**：固定 `.fcad` 片段 → 固定 node/edge digest（写死在测试里，跨实现一致性）；
2. **谱系命名稳定性**：改参数重新接地草图 → 新 digest，旧节点仍在，构造路径引用仍解析；
3. **fail-closed**：义务不满足的边 = rejected；以其输出为输入的下游边必须 rejected（I3）；
4. **精确链接**：引用不存在 digest 的边 → I1；
5. **草图求解**：§9 的 rib-sk 收敛，残差 <1e-6，dof 计算正确；
6. **几何正确性**：10×20 矩形拉伸 3mm → 体积 600 mm³ ±1e-6；STEP/STL blob 非空且可回读；
7. **端到端**：`fk run examples/aircraft.fcad` 完成；`fk goals` 输出非空洞清单；
   `fk why` 回溯到 Intent；`fk trace` 包字段齐；
8. **终止性**：`fk realize --until standard-part` 在小树上停机且所有叶子为 exact/procure。

## 环境

- Python 3.12；venv 已建于 `<workspace>/.venv`，**OCP（cadquery-ocp）已装好**；
- 另需 `pip install numpy scipy`（进同一 venv）；core/store 不得 import 任何第三方库；
- Windows 注意：OCP 的 DLL 在未关闭 Smart App Control 的机器上会被拦（ImportError），
  文档中注明（WSL 或关闭 SAC）。

## 已有原型（本工作区 `fluxkernel/`，语法编译通过但未跑通，需修正后采用）

| 文件 | 状态 | 需要的修改 |
|---|---|---|
| `core/canon.py` | 可用 | 无 |
| `core/objects.py` | 可用 | `level` 字段改 `role`（递归角色本体，§3.2） |
| `core/dag.py` | 可用 | 谱系检查逻辑保留；补 goals/sorry 扫描支持 |
| `store/objstore.py` | 可用 | 无 |
| `semantics/ontology.py` | **重写** | 固定八级 → 七角色 + 终止规则 |
| `solvers/registry.py` | 可用 | 无 |
| `solvers/sketch2d.py` | 可用 | 义务生成对齐 §7 |
| `solvers/feature3d.py` | 半成品 | `_finish_solid` 的 construction 记录逻辑有缺陷，重写；补 boolean/mate |
| 缺的 | 新建 | `__init__.py` × 4、`semantics/operators.py`、`semantics/goals.py`、`interface/*`、`adapters/*`、`solvers/{mission,mate,dfam,process,line,catalog}.py`、`catalog/*.json`、`examples/aircraft.fcad`、`tests/run_tests.py`、`pyproject.toml`（console_script `fk`） |

---

# 12. 里程碑

| 里程碑 | 内容 | 验收 |
|---|---|---|
| M0 核 | L0+L1+L3 骨架 + .fcad 解析 + CLI（node/refine/goals/log/show） | 测试 1/3/4 绿；无几何 |
| M1 几何 | sketch2d + feature3d(OCP) + export | 测试 2/5/6 绿 |
| M2 全链 | mission/process/line/catalog + compose/abstract/exact/procure/manufacture + why/status | 测试 7 绿（aircraft.fcad 跑通） |
| M3 对接 | mbench trace 导出 + realize 组合子 + watch 预览 | 测试 8 绿 + trace 包被独立 JSON schema 校验通过 |

**开发纪律**：L1 不 import 第三方库；每个 PR 必须带黄金向量；诊断码表只增不改；
插件永远返回证据；失败轨迹永不删除。
