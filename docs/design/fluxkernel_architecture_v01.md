# FluxKernel 总体架构 v0.1

> 本文回答的是"整体架构"：这个内核作为**一个系统**由哪些子系统构成、各自边界与职责、
> 数据与控制如何流动、部署形态是什么、与 FluxPRSI 生态其他部分如何拼接。
> 设计决策的细节论证见 `fluxkernel_design_v01.md`，本文不重复。

---

## 1. 定位：它在生态里的位置

FluxKernel 不是独立产品，是 FluxPRSI 生态的**物理构造内核（physical construction kernel）**：

```
                         ┌──────────────────────────┐
                         │  Gθ（设计者 LLM / Agent）  │  需求理解、MRS 生成、
                         │  Draft/Improve/Debug/    │  更新配方提出
                         │  Crossover               │
                         └────────────┬─────────────┘
                                      │ 只通过 .fcad DSL 通信
                                      ▼
   ┌──────────────┐        ┌──────────────────────┐         ┌───────────────────┐
   │ Mechanogenesis│◄─trace─│     FluxKernel        │─.flux──►│ FLUXmeme          │
   │ Bench         │ adapter│  （本系统）            │ BODY投影 │ （DevReady 资产库） │
   │ Lean 验证核   │        └──────────┬───────────┘         └────────┬──────────┘
   └──────────────┘                   │ mesh/URDF/工艺                 │ 资产
                                      ▼                                ▼
                          ┌──────────────────────┐         ┌───────────────────┐
                          │ 物理引擎/真实硬件       │         │ FLUXworkbench /    │
                          │ (blender/Isaac/机床)  │         │ FluxWeave 工作台    │
                          └──────────────────────┘         └───────────────────┘
```

三条边界纪律：

1. **对内**：FluxKernel 不做 GUI、不做渲染、不做仿真编排——那些是工作台层的事；
2. **对上**：LLM 永远不见 Python 对象，只见 `.fcad` 文本与类型化诊断——通信面即训练面；
3. **对外**：bench 只信 trace 与证书，不信内核的口头结论——内核是可被独立复算的。

## 2. 架构风格：三个成熟系统的合体

整体架构直接类比三个已被验证的系统，每一层都有现成心智模型：

| 类比 | 对应能力 | 解决的问题 |
|---|---|---|
| **Git**（内容寻址对象库 + DAG + 分支合并） | 身份、谱系、变体、非破坏历史 | PRSI 的 lineage Z_k、`o_i=t_{i+1}` 精确链接、走弯路保留证据 |
| **LLVM**（canonical IR + pass 管线 + 可插拔后端） | .fcad IR、refine/compose/abstract 算子即 pass、OCP 等求值后端可换 | V 模型逐层展开；几何引擎不锁定 |
| **Lean**（小可信核 + 证书/义务分离 + 独立 checker） | fail-closed 验证、proof obligation 导出 | 可信基最小化；bench 可独立重放 |

这三个类比同时也是**三个不变式**：身份不可伪造（Git）、IR 是唯一的通信介质（LLVM）、
核之外的任何东西都不被信任（Lean）。

## 3. 内核分层架构（进程内）

```
┌─────────────────────────────────────────────────────────────────┐
│ L4 接口面 interface                                              │
│   .fcad 解析器/打印器 │ Python API │ MCP 工具面 │ CLI             │
│   职责：语法 ↔ IR 的双向无损转换；类型化诊断码生成                  │
├─────────────────────────────────────────────────────────────────┤
│ L3 语义面 semantics                                              │
│   V 模型算子引擎（refine / compose / abstract / evaluate）         │
│   层级本体注册表（Intent→Function→Skeleton→Part→Process→Line→Meta）│
│   变体空间管理（VariantSpace / MAP-elites 式档案）                 │
│   职责：算子的前置条件检查、不变量登记、obligation 生成             │
├─────────────────────────────────────────────────────────────────┤
│ L2 求解面 solving（全部插件化，注册表驱动）                        │
│   SketchSolver(2D) │ MateSolver(3D,闭链) │ 特征求值器(OCP 后端)    │
│   DfAM/质量评测器   │ 工艺 grounding     │ 产线布局求值            │
│   职责：把"约束+参数"grounding 成具体几何/工艺/布局，产出证据      │
├─────────────────────────────────────────────────────────────────┤
│ L1 核 core（可信基，目标 <5k 行）                                  │
│   Node / Edge / Certificate / ResourceVector 数据类型             │
│   DAG 一致性、LIVRPS 组合弧求值、证书本地检查、promotion 判定       │
│   职责：唯一被信任的组件；fail-closed；不含任何几何知识             │
├─────────────────────────────────────────────────────────────────┤
│ L0 存储面 store                                                  │
│   内容寻址对象库（digest→bytes）│ append-only 边日志 │ 索引        │
│   .flux 容器投影（DevReady 资产打包/解包）                         │
│   职责：哑存储。无解析、无求解、无调度（FluxWeave 哲学）            │
└─────────────────────────────────────────────────────────────────┘
```

分层的依赖规则：**只允许上层依赖下层，L2 插件之间互不依赖，L1 不依赖 L2**。
这保证：换掉几何引擎只动 L2 的一个插件；换掉存储只动 L0；核（L0+L1）可以独立进 Lean 复刻。

### 为什么是这个切法

- L0/L1 = **Git + Lean 核**：小、可审计、可被 bench 的 Lean 实现逐行对照复刻；
- L2 = **LLVM 后端**：所有"重的、可能错的、会演进的"东西都在这里，且每个插件的输出
  都必须附带证据（残差、收敛标志、校验和），证据进 L1 的证书，插件本身不进可信基；
- L3 = **V 模型的家**：算子语义与层级本体独立于任何求解器，保证"产线设计产线"和
  "草图拉伸"用的是同一套算子机制；
- L4 = **训练飞轮的接触面**：LLM 只碰这一层，诊断码在这一层生成。

## 4. 核心数据流：一次完整 V 链走查

以"低成本器件做满足严苛需求的飞行器"的简化版为例，展示数据如何流过五层：

```
① Intent   需求节点 N0（模糊需求 + 约束域：成本上限、指标下限、器件白名单）
   │  refine[需求澄清]  ← LLM 提交，L3 检查前置条件，生成 obligation
② Function 功能架构节点 N1（推进/结构/航电/热管理 功能分解 + 功能间接口）
   │  refine[功能→几何架构]
③ Skeleton 骨架节点 N2（布局曲线、接口坐标系、运动链——纯 1D/框架，无实体）
   │  refine[骨架→部件] ×n（每个部件一条边，可并行）
④ Part     部件节点 N3a/N3b/...（2D 草图 → 约束求解 → 3D 实体，经 L2 OCP 求值）
   │  compose[装配]（LIVRPS 弧：接口由 ③ 的骨架节点 reference 进来，非破坏）
⑤ Process  工艺节点 N4（DfAM 评测证据回流；软件硬化/硬件软化在此分叉选择）
   │  compose[产线组合]
⑥ Line     产线节点 N5（产线单元 = 自根算子节点，对等组合，无全局根）
   │  当 N5 被下一代任务引用为输入算子（digest 相等）──► PRSI 递归边成立
⑦ MetaLine N5' 的构造本身是一条边：o_i = t_{i+1}，adapter 生成 PIPE 证书包
```

回装方向（V 右腿）：每一层的 compose 边在 commit 时重放子证书 → 汇集成父证书；
任何一层验证失败 → 产生 abstract 边回到上层开新分支（旧分支保留为"有信息的失败"资产）。

整条走查中，**LLM 在每一层提交的都只是 .fcad 片段**；内核在每一层返回的只是
类型化诊断 + 证书状态。这个"提交—诊断"循环就是 Draft/Improve/Debug 的运行时形态。

## 5. 关键子系统详述

### 5.1 对象模型与身份（L0/L1）

- 一切对象（节点、边、证书、变换定义、证据）内容寻址：`digest = hash(canonical_bytes)`；
- canonical 序列化只有一种（deterministic encoding），文本形态 = `.fcad`，二进制形态可嵌入 `.flux`；
- 引用即 digest，因此 `o_i = t_{i+1}` 的"精确链接"在 commit 时由 L1 强制（digest 不等即拒绝）；
- 谱系命名：几何元素的稳定引用 = `节点digest + 构造路径`，参数变化重建后引用依然解析得到——
  这是相对 build123d 拓扑命名漂移的结构性解法，不是补丁。

### 5.2 边的生命周期（L1 状态机）

```
proposed ──► executed ──► evidenced ──► verified ──► promoted
    │            │            │             │
    └────────────┴────────────┴─────────────┴──► rejected（保留，可检索，不可被引用）
```

- `executed`：L2 求解器跑完，产出投影与原始证据；
- `evidenced`：证据装订成证书包，评测者身份（独立于执行者的 digest）写入；
- `verified`：L1 本地检查通过（有限命题：身份、闭环、预算、不变量）；
- `promoted`：满足 promotion 谓词（对齐 bench 的 Promotion 模块），允许被下游边引用；
- **fail-closed**：任何一步失败都落入 rejected，但对象不删除——它是有信息的失败，
  进入变体档案供 Crossover 与 SFT 使用（对齐你笔记里的 SEAL 后验原则与轨迹保留要求）。

### 5.3 算子引擎（L3）

四个算子共享同一执行骨架（这也是"一个核"的具体含义）：

```
execute(op, inputs, transform):
    1. 前置条件：op 的层级规则 + 输入节点的证书状态（必须 verified）
    2. 登记不变量：从输入节点继承 + transform 新增
    3. 调用 L2 插件执行 transform → 投影 + 证据
    4. 生成 obligations（上层不变量保持、接口保持、预算闭环…）
    5. 装订证书，写边，commit 到 DAG
```

refine/compose/abstract/evaluate 只是这个骨架上不同的前置条件集与 obligation 模板。
新增层级（比如未来加"供应链层"）= 注册新 kind + 模板，不改引擎。

### 5.4 求解面插件注册表（L2）

每个插件声明：`accepts(kind, transform类型) → produces(投影类型, 证据字段)`。
首批插件与边界：

| 插件 | 输入 | 输出 | 后端 |
|---|---|---|---|
| sketch-2d | 部分约束草图 | 接地草图 + 残差 | 数值求解（scipy 起步） |
| feature-3d | 草图+特征变换 | B-rep 投影 + 质量属性 | OCP |
| mate-3d | 部件+配合约束（含闭链） | 装配位姿图 + 干涉报告 | 自研图求解 |
| dfam | B-rep + 工艺类型 | 可制造性证据 | 规则+几何分析 |
| process | 特征+工艺选择 | 工艺步骤 + 资源估计 | 规则库 |
| line | 产线单元+流约束 | 布局 + 产能/节拍证据 | 离散事件（轻量） |

插件可独立替换、可并存多版本（digest 区分），同一 transform 可被两个后端各算一遍
互为独立计量（metrology）——这直接对应 PRSI 的"独立 metrology"能力。

### 5.5 验证拓扑：信任是怎么分布的

```
LLM 提交（不可信）──► L4 解析（语法检查）──► L3 算子（前置条件）──► L2 求解（产出证据）
                                                              │
                        ┌─── L1 本地 verifier（可信，有限命题）◄┘
                        │
bench Lean 核（独立复算，协议命题）◄── trace adapter（L4 的导出器）
                        │
              物理证据（硬件计量，最高 tier）◄── 真实执行（可选）
```

三层验证各管一段：L4/L3 管"说得对不对"，L1 管"链得对不对"，bench/物理管"是不是真的"。
内核永不自我宣称物理真实——这与 bench 架构文档"neither asserts that a physical model is
faithful without independent evidence"的立场严格对齐。

## 6. 部署与进程拓扑

- **形态一（默认）：库**。`pip install fluxkernel`，进程内使用，供 Gθ 的 harness 调用；
  等价于 build123d 的使用方式，但 API 是 .fcad 的 Python 投影；
- **形态二：服务**。`fluxkernel serve` 暴露 MCP/JSON-RPC，供 Agent 框架远程调用；
  多会话共享同一对象库（内容寻址天然去重，天然支持多项目共生）；
- **形态三：bench engine**。被 MechanogenesisBench 以进程方式拉起，stdin/stdout 走
  submission ABI，trace 落盘为证书包——对应 bench 架构里的 "registered engine"；
- **无全局服务依赖**：对象库是本地文件（类 Git），去中心化 = 每个工作区自根，
  库与库之间靠 digest 交换对象（类 Git fetch/push），不依赖中心服务器。

## 7. 仓库目录结构（草案）

```
fluxkernel/
├── core/            # L1：Node/Edge/Cert/DAG/compose/promote（目标 <5k 行，无第三方依赖）
├── store/           # L0：对象库、边日志、索引、.flux 投影
├── semantics/       # L3：算子引擎、层级本体注册表、变体空间
├── solvers/         # L2：sketch2d / feature3d(ocp) / mate3d / dfam / process / line
├── interface/       # L4：fcad 解析打印、Python API、MCP、CLI、诊断码
├── adapters/
│   ├── mbench/      # → MechanogenesisBench：trace→canonical IR→Lean 证书包
│   └── fluxmeme/    # → FLUXmeme：节点包 ↔ .flux BODY/MIND
├── formal/          # Lean 复刻 core 的有限命题（与 mbench 核共享谓词定义）
└── tests/
    ├── conformance/ # 谱系命名稳定性、round-trip、fail-closed、精确链接
    └── vectors/     # 黄金向量：固定 .fcad → 固定 digest（跨实现一致性）
```

## 8. 与 build123d 的正面回答（架构层，而非 feature 层）

"同位替代"在架构上的含义是：**占用同一个生态位（Python 原生 CAD 构造库），但骨架不同**。
build123d 的骨架是"OCCT 对象的 Python 包装 + 命令式构造器"；FluxKernel 的骨架是
"内容寻址 DAG + 算子引擎 + 插件求解面"，几何能力只是求解面里最先做的一个插件。
因此 build123d 能写的每个脚本原则上都能翻译成一条 refine/evaluate 边序列，
而 FluxKernel 能表达的（未坍缩空间、证书链、变体合并、产线递归）build123d 在架构上没有放置它们的位置。
兼容路径：提供 `fluxkernel.bridge.b123d`，把 build123d 脚本执行结果 ingest 为
一条"黑盒 evaluate 边"（证据 tier 最低），保证存量资产可进入谱系但不被当作已验证。

## 9. 架构上的主要风险

1. **核膨胀**：最大的架构风险是把求解逻辑渗进 L1。纪律：L1 不含任何 import 几何/数值库；
2. **IR 冻结过早**：.fcad 是训练面也是资产面，M0 期间必须允许 breaking change，
   用版本字段 + 迁移边（migrate 作为第五种内部算子）兜底；
3. **插件证据造假**：L2 插件不可信是设计前提；长期需要双后端互算 + 物理证据 tier 兜底；
4. **Lean 复刻漂移**：formal/ 与 core/ 必须共用黄金向量测试，CI 里跨实现 digest 对比。
