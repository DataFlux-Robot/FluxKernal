# FluxKernel：一个面向 PRSI 的 build123d 同位替代 CAD 内核 — 架构设计 v0.1

> 目标：不是给 build123d 套壳，而是在同一抽象层级（Python 原生 CAD 构造库）上重建一个
> **内容寻址、携带证书、可逐层精化/重新抽象** 的内核，作为 MechanogenesisBench 的物理内核，
> 支撑「自然语言需求 → 产品 → 产线 → 产线的产线」的 V 模型展开与回装。

---

## 0. 重要性排序（按用户要求）

| 优先级 | 需求 | 内核必须回答的问题 |
|---|---|---|
| 1 | 支撑 PRSI（Machines That Accelerate Machine-Making） | 每一次"造出几何/工艺/产线"的动作如何变成可审计的生产边（PIPE）？ |
| 2 | V 模型 / MBSE（逐层展开 + 重新组装 + 允许重新抽象） | 精化和回装是什么算子？层间如何验证？ |
| 3 | LIVRPS、去中心化、FluxWeave 哲学 | 组合如何非破坏、无全局根、哑存储智应用？ |
| 4 | 兼容 Lean、面向 LLM 的通信形式 | LLM 写的"CAD 程序"如何接近证明项、可被 SFT/RL？ |

结论先行：**这四个需求是同一个数学结构的四个投影。核不是几何，是"带证书的精化图"。**

---

## 1. 共性分析：五个来源指向同一个核

### 1.1 把它们写成同一形状

| 来源 | 核心对象 | 它的形状 |
|---|---|---|
| PRSI 论文 | PIPE 边 `e_k = (P_{k-1}, t_k, δ_k, o_k, P_k)` | **带前提、变换、输出、证据的边**，且 `o_i = t_{i+1}` 精确链接 |
| MechanogenesisBench | 内容寻址 MRS 包 + canonical IR + Lean 核 + refinement adapter | 边 = 可降级到 Lean 可检查对象的 trace |
| V 模型 / MBSE | 需求→功能→结构→几何→工艺→产线，左腿分解、右腿集成验证 | 下行边 = 精化，上行边 = 带验证的组合 |
| FLUXmeme / LIVRPS | 自根节点 + Local/Inherits/Variants/References/Payloads/Specializes + 字段级合并 | 非破坏组合算子；一源多投影 |
| Lean / LLM 训练 | 判断（judgment）：从前提 X 经规则 δ 得 Y，附证据 E | 每条边 = 一步推理；整条链 = 一个证明项 |

**同构映射**：PRSI 的 `ProducedBy(o_k; P_{k-1}, t_k, δ_k)` 就是逻辑里的"构造性判断"，
V 模型的"验证通过"就是该判断的证书，FLUXmeme 的 record/digest 就是它的内容寻址身份，
Lean 就是它的检查器。**一个结构，四种读法。**

### 1.2 因此，核（The Core）是：

> **CARG — Certificate-carrying, content-Addressed Refinement Graph**
> （带证书、内容寻址的精化图）
>
> - **节点 Node** = 某一抽象层级上的"设计状态"：规格 + 约束集 + （可选的）已求值几何 + 证据 + 谱系哈希。
>   节点可以表示**尚未坍缩的设计空间**（参数域、未决变体、部分约束的草图），不只是最终 B-rep。
> - **边 Edge** = 已登记的变换：`(输入节点集, 变换 δ, 输出节点, 证书, 资源向量)`。
>   边有三种基本型：**refine（精化/下行）、compose（组合/回装）、abstract（重新抽象/上行）**。
> - **证书 Certificate** = 有限、可机检的证据包：约束保持、身份链接、资源闭环、验证通过。
> - **内容寻址**：一切身份 = 哈希；`o_i = t_{i+1}` 的"精确链接"退化为 digest 相等性检查。

几何内核（B-rep）只是节点的一种**求值投影**——正如 FLUXmeme "不是内含一个 USD，而是按需渲染 USD 视图"，
FluxKernel 的节点不是"内含一个 Solid"，而是**按需求值出 Solid**。

### 1.3 你的"扩散/flow matching"直觉的形式化

你在笔记里写："噪声本质不是噪声，而是表现形式随迭代逐渐定向量子坍缩"。在 CARG 里这有精确对应：

- **未坍缩态** = 载荷为"设计空间"的节点（约束集 + 变体域 + 自由参数域），对应扩散的高噪声态；
- **一步去噪** = 一条 refine 边：增加约束/选定变体/接地参数，同时**保持已声明不变量**；
- **坍缩完成** = 节点求值为唯一 B-rep / 唯一工艺 / 唯一产线布局；
- **走弯路再回来**（航母弹射器的例子）= abstract 边回到上层节点 + 沿另一支重新 refine——
  因为图是非破坏的，旧分支仍作为证据保留（这正是 PRSI 要求的"有信息的失败"要留存）；
- **软件硬化/硬件软化** = refine 边在"功能 → 实现"层的两种不同 grounding 选择，
  在内核里是同一算子的两个实例，不需要预设。

这也意味着内核必须原生支持**部分指定（partial specification）**——这是 build123d 根本做不到的：
build123d 的每个对象都是完全接地的 B-rep；FluxKernel 的对象默认是"空间"，接地是显式动作。

---

## 2. 与 build123d 的同位差异（为什么是"替代"而不是"套壳"）

| 维度 | build123d | FluxKernel |
|---|---|---|
| 对象语义 | 可变 B-rep 包装（Shape 持有 TopoDS_Shape） | 不可变值；形状是求值结果，可缓存但不携带身份 |
| 构造方式 | 命令式 builder / algebra 双 API | 声明式约束 + 显式 refine 步骤；求值惰性 |
| 命名 | 拓扑命名问题（面/边索引随重建漂移） | **谱系命名**：身份 = 构造路径哈希，重建后引用仍稳定 |
| 约束 | 无求解器（只有几何断言辅助） | 2D 草图求解器 + 3D mate 求解器为一等公民 |
| 证据 | 无 | 每条边携带证书 + 资源向量（时间/能量/材料/失败损失） |
| 组合 | 无（Compound 是几何并集） | LIVRPS 组合弧，非破坏，去中心化自根节点 |
| 序列化 | 无 canonical 形式 | `.fcad` 文本 canonical 源（对齐 `.fluxa`），可 diff、可进 git、可进 Lean |
| 底层引擎 | OCCT via OCP | **同样 OCCT via OCP**——替代的是对象模型，不是几何引擎 |

注意最后一行：重写 B-rep 引擎（OCCT 级别）是十年量级工程，不是"build123d 级"范围。
**build123d 的本体贡献是 Pythonic 对象模型；你要替代的正是这一层。** OCP 继续作为求值后端，
但被隔离在"投影层"，内核对象模型不依赖它（未来可换后端，甚至多后端互为 metrology）。

---

## 3. 分层架构（与 FLUXmeme 三层对齐）

```
[Tier 3] 接口层    Python API（build123d 同级体验） | .fcad DSL | Lean 导出 | MCP/工具 schema
[Tier 2] 内核层    Node/Edge/Certificate + 内容寻址存储 + 求解器 + LIVRPS 组合 + 证据账本
[Tier 1] 格式层    .fcad（文本 canonical 源） ↔ 节点包（可嵌入 .flux 的 BODY/MIND）
```

### 3.1 Tier 2 核心数据类型（最小集）

```python
# 伪代码：内核最小本体（Lean 中一一对应）
Level    ::= Intent | Function | Skeleton | Part | Process | Line | MetaLine   # 可扩展的 kind，不是硬编码层号
Node     ::= { id: Digest, level/kind, spec: ConstraintSet,
               variants: VariantSpace,          # 未坍缩部分
               ground: Option[EvalRef],         # 已求值投影（几何/工艺/布局）
               evidence: List[Evidence],
               lineage: List[EdgeRef] }
Edge     ::= { id: Digest, op: Refine | Compose | Abstract | Evaluate,
               inputs: List[Digest],            # t_k
               transform: Transform,            # δ_k：参数化的构造规则
               output: Digest,                  # o_k
               certificate: Cert,               # 有限可机检证据包
               resources: ResourceVector }      # c(P; μ)：时间/材料/能量/金钱/人力/失败损失
Cert     ::= { obligations: List[Prop], discharged: List[ProofRef | CheckerRef],
               evaluator: Digest,               # 评测者身份（独立于执行者）
               fork: Option[ForkRecord] }       # PRSI 处理/对照叉
```

三条公理直接来自 PRSI：

1. **精确链接**：`Chain` 要求 `edge[i].output == edge[i+1].inputs[j]`（digest 相等）——内核在 commit 时强制；
2. **共同祖先记账**：资源向量只记 `L_inc-build`（相对共同祖先的增量），fork 记录绑定非处理变量；
3. **fail-closed**：证书未通过的边可以存在（作为"有信息的失败"进入资产），但永远不能被 promote / 被下游边引用为输入。

### 3.2 求解器层（"哑存储、智应用"的应用侧）

格式只存约束与身份；求解全部在应用层，新增领域 = 新增 kind + solver，不改内核：

- **SketchSolver**（2D）：距离/角度/平行/垂直/相切/重合/对称约束 → 数值 grounding；
- **MateSolver**（3D）：面/轴/坐标系对齐，闭链一等公民（继承 FLUXmeme graph 立场，超越 URDF 纯树）；
- **Evaluator**：质量属性、DfAM 检查（壁厚/悬垂/支撑体积，参考 text-to-cad 的 dfam-check）、可装配性；
- **ProcessGrounding**：特征 → 工艺（增材/减材/钣金），"软件硬化/硬件软化"在这里分叉；
- 每个 solver 的输出 = EvaluatedProjection + Evidence（残差、收敛、校验和），证据回流节点。

### 3.3 LIVRPS 组合（去中心化）

- 每个节点自根、自治，**无全局场景根**；一条产线 = 若干产线单元节点的对等组合；
- 组合弧优先级 Local > Inherits > VariantSets > References > Payloads > Specializes，
  字段级合并、非破坏——**"重新组装回去"= 沿 compose 边的逆视图重放，而不是重新建模**；
- variant 是一等公民：同一功能节点的多个实现变体共存于 VariantSpace，
  Draft/Improve/Debug/Crossover 里的 Crossover = 两个 variant 支系的合并边，天然落在内核里。

### 3.4 Lean 桥与 LLM 接口（第 4 优先级，但决定训练飞轮）

设计原则：**让 LLM 写的不是"调用序列"，而是"判断序列"**。

```lisp
;; .fcad canonical 源（示例片段）：接近 Lean 的项结构，而非 Python 命令
(node bracket-fn :level Function
  :spec ((load-case 500N :direction -z) (mass-budget 80g) (process fdm)))
(edge e1 :op refine :in (bracket-fn) :out bracket-sketch
  :transform (ground-skeleton :interfaces (mount-a mount-b load-eye))
  :obligations ((interfaces-preserved bracket-fn bracket-sketch)))
(edge e2 :op refine :in (bracket-sketch) :out bracket-solid
  :transform (sweep+shell :profile sketch-1 :thickness (uniform 3mm)))
  :evidence ((dfam-check fdm :wall-ok true :max-overhang 42deg)
             (mass 71.2g)))  ;; 证书：约束满足 + 独立评测者 digest
```

- 语法：S-表达式 / 类 Lean 项结构，文法极小（node / edge / spec / transform / evidence 五个构造子），
  对 SFT 友好；每类错误对应**类型化诊断码**（欠约束 U1、过约束 O2、身份断裂 I1、证书缺失 C0…），
  直接就是 RL 的 reward shaping 信号和 Debug 算子的输入；
- 与 Lean 的关系：`.fcad` → 导出 proof obligations → MechanogenesisBench 的 Lean 核
  （`CanonicalIR / RefinementContract / MetrologyRefinement / Promotion` 等模块已定义对应谓词）
  机检后回写 ProofRef。**内核不追求在 Lean 里证明几何正确性，只证明有限的协议性命题**
  （身份、闭环、预算、promotion 条件）——与 bench 现有 "Lean owns finite claims" 的分工一致；
- 你的遗传 loop 直接映射为边类型：Draft = 首次 refine 链；Improve = 以父代为输入的 refine 边；
  Debug = 以诊断码为条件的修复边；Crossover = compose 边合并两个变体系；
  父代/子代/accepted/rejected/traceback/hash/seed/FLOP 全部落在 Edge 的 resources + evidence 里，
  整条轨迹天然就是一个 DevReady 资产（嵌入 .flux 的 MIND 层）。

### 3.5 与 MechanogenesisBench 的对接（物理内核的职责）

FluxKernel 在 bench 架构中的位置 = **注册的 engine / refinement adapter**：

```
Gθ（设计者 LLM）--.fcad--> FluxKernel 执行 --> trace（Node/Edge/Cert 日志）
                                                    |
                          bench adapter 降级为 canonical Lean 可检查对象
                                                    |
                    Lean 核检查：身份链接、材料闭环、预算、promotion、recursive credit
```

对接要点：

1. 每次求值/构造产生 **trace**，字段对齐 bench 的 canonical IR（digest、lineage、resource vector、evidence tier）；
2. 产线级节点 = 生产算子（operator）；当一代产出的产线节点被下一代引用为输入（`o_i = t_{i+1}`），
   adapter 生成 PIPE 证书包提交 bench 验证——**这就是"产线设计产线"在内核里的唯一定义**；
3. fork（处理/对照）在边级记录，支撑共同祖先因果比较 `τ_k(μ)`；
4. 仿真证据（如 build123d/blender 物理引擎的实验结果）作为低 tier 证据进入，
   与硬件证据分开计 tier——对齐 bench 的 evidence-tier ceilings。

---

## 4. V 模型的形式化：三个算子

| 算子 | V 模型位置 | 内核语义 | 证书义务 |
|---|---|---|---|
| `refine` | 左腿下行 | 增加约束/选定变体/接地参数，设计空间收缩 | 上层不变量保持（接口、载荷、预算） |
| `compose` | 右腿上行 | 子节点按 LIVRPS 弧组合为父节点 | 接口配合验证 + 各子证书汇合 |
| `abstract` | 回退/重新抽象 | 从过具体的节点回到上层，生成新的替代分支 | 标记 supersede 关系，旧链保留为证据 |

"逐层展开然后重新组装回去"= refine 链 + compose 链，且两条链在节点处共享身份——
**回装不是重新建模，是重放已验证的组合关系**。"允许暂时退步"= abstract 边非破坏地开新分支。

层级本体（可扩展，不是硬编码）：
`Intent(需求/MRS) → Function(功能架构) → Skeleton(几何架构：接口/布局/运动链，1D 骨架)
→ Part(2D 草图 → 3D 实体) → Process(工艺) → Line(产线) → MetaLine(产线的产线，即 PRSI 递归层)`。

你原来感觉的 "1D→2D→3D 自下而上" 被重新解释为：**只是 Part 层内部的三个 grounding 阶段**，
而它之上还有五层同样形状的精化——V 模型把 build123d 的轴变成了整个链条的一小段。

---

## 5. 实现路线图（严格控制在 build123d 级，不做完整系统）

| 里程碑 | 内容 | 验收标准 |
|---|---|---|
| **M0 核** | Node/Edge/Cert/ResourceVector + 内容寻址存储 + `.fcad` 读写 + digest 链 | 纯 Python、零几何依赖；100 节点的 refine 链可 round-trip、可 diff |
| **M1 几何层** | OCP 求值后端；Sketch DSL + SketchSolver；extrude/revolve/boolean/fillet/shell 为 transform | 常见零件 API 体验对齐 build123d；**谱系命名**在参数改后引用不漂移（build123d 做不到的测试） |
| **M2 组合** | MateSolver + LIVRPS 弧 + variant；闭链机构图 | 四连杆/Delta 机构可表达、可求 FK；两个变体系可 Crossover 合并 |
| **M3 工艺/产线层** | Process/Line kind + DfAM evaluator + .flux transcoder（BODY 投影）+ bench adapter | `demand_driven_microfactory` 类任务的 trace 可被 bench Lean 核接受 |
| **M4 LLM 面** | 类型化诊断码 + MCP/工具 schema + SFT 语料导出（边=样本） | Draft/Improve/Debug/Crossover 四算子各有 ≥1 条端到端轨迹入 DevReady 资产 |

反 scope（明确不做）：GUI、渲染器、网格生态、完整仿真、URDF/USD 双向工具链——
这些是 FluxWeave/FLUXworkbench 层的职责；FluxKernel 只向它们投影。

## 6. 风险与取舍

1. **OCP 依赖照旧**：替代的是对象模型不是几何引擎；Windows Smart App Control 对 OCP 未签名 DLL 的封锁
   依然适用（text-to-cad 已踩坑），需文档化或提供 conda 渠道；
2. **约束求解器是硬骨头**：2D sketch 求解可先数值法（scipy 最小二乘）起步，勿一开始追求符号完备；
3. **Lean 只证协议不证几何**：几何正确性由 evaluator 证据 + 证据 tier 承担，否则会陷入不可判定的深渊；
4. **未坍缩节点是最大创新也是最大风险**：VariantSpace 的表示（区间域？离散枚举？学习到的隐空间？）
   建议 M0 只支持离散枚举 + 参数区间，隐空间留给 M4 之后的 Gθ；
5. **与 MechanogenesisBench 的 IR 对齐要趁早**：M0 的 digest/lineage/resource 字段应直接照搬 bench 的
   canonical IR 命名，避免 M3 时重做映射。

---

## 7. 一页纸总结

> 五个需求 = 同一个核的五次投影。**核 = 内容寻址、带证书的精化图（CARG）**：
> 节点是（可能未坍缩的）设计状态，边是 refine/compose/abstract 三种已登记变换，
> 每条边携带可机检证书与资源向量，身份即哈希。
> PRSI 的 PIPE = 边的证书形态；V 模型 = refine/compose 链；LIVRPS = compose 的弧语义；
> Lean/LLM = 图的 canonical 文本与检查器；build123d 的几何能力 = 节点的一种求值投影。
> 先做 M0（无几何的核）+ M1（几何投影），用"谱系命名不漂移"和"证书链可 Lean 机检"
> 两个 build123d 做不到的性质作为立身测试。
