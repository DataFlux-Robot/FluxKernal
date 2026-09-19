# Lean 引导的 CLI 设计系统设计：把"逐层拆解到标准件"做成战术证明 v0.1

> 核心命题：**"meta（总体设计→具体设计）直到拆成电机/螺丝"在形式上就是 Lean 的战术证明（tactic proof）。**
> 因此这个 CLI 系统的正确设计形态不是"CAD 命令行"，而是**物理设计的战术外壳（tactic shell for physical design）**。

---

## 1. 完整的概念映射表

| Lean | 本系统 | 说明 |
|---|---|---|
| 命题/类型 `P` | **目标（goal）**：待实现的节点规格 `S` | "满足航程≥2600km 的飞行器"是一个类型；具体设计是它的一个项 |
| 项 `t : P` | 已接地的设计（所有参数坍缩、证据齐备） | 项 inhabit 类型 = 设计满足规格 |
| 战术（tactic） | **refine / compose / abstract / eval / exact / procure / manufacture** | 每个战术把当前 goal 变成若干 subgoal |
| 子目标（subgoals） | 分解出的子节点（机翼/发动机/…） | `refine decompose [wing, engine]` = 一个 goal 变五个 subgoal |
| `exact lemma` | **引用标准件/库设计直接关闭 goal** | 电机/螺丝 = 库中已证引理；`fk exact motor.torque50` |
| **Mathlib**（库） | **标准件与已验证设计库**（目录件、工艺模板、机床方案） | 库 = PRSI 里的资本 K：可继承、可执行、改变后继成本 |
| 战术状态（goals view） | `fk goals`：当前所有未履行义务/未坍缩参数 | 设计系统的"仪表盘" |
| `sorry`（洞） | **未坍缩参数/未验证假设**，允许存在但被追踪 | "其他属性都是参数状态" = 带 `sorry` 的项；`fk sorry` 列出全部洞 |
| 元变量 `?m` | 参数态属性 `?mass ?thrust` | 约束求解 = 元变量赋值；flow-down = 上下文，roll-up = 向上汇报实例化 |
| 项模式 vs 战术模式 | **.fcad 完整设计项（LLM 批量）vs CLI 逐步战术（人类）** | 两种写法，同一内核检查——双主角的 Lean 式解法 |
| 阐释器（elaborator） | .fcad → 内核对象的展开器 | 表面语法可甜，内核对象唯一 |
| 内核（kernel，小而可信） | L1：Node/Edge/Cert/DAG 检查器 | 战术可以错、可以花，内核只认证书 |
| 终止性检查（well-founded） | **拆解递归必须在标准件/外购件处终止** | 终止测度 = 规格剩余复杂度；目录命中 = 基本情况 |
| 类型类推断（instance search） | **目录检索**："找一个 torque≥50Nm 的电机" | `fk search` 在标准件库做实例搜索 |
| 公理（axioms） | 物理/计量证据：内核不证物理，只登记来源与 tier | 对齐 bench 的 AssumptionLedger：每条物理结论挂着它的假设账本 |
| `have` / `show` | 中间指标的声明与核验（roll-up 锚点） | `fk assume wing.mass ≤ 40kg` 后续 compose 时清算 |
| 战术组合子 `a <;> b`、`repeat`、`first \|` | **组合战术**：`realize = repeat (decompose <;> try-catalog <;> eval)` | 整个主循环是一条组合战术 |
| 证明脚本文本 = 可重放资产 | **设计会话 = 可重放脚本**，进 DevReady 资产 | Draft/Improve/Debug/Crossover 的操作对象就是脚本 |

## 2. CLI 的设计形式：四组命令

```
── 目标操作（goal-oriented，战术模式的核心）──
fk goals                     # 战术状态：未关闭的 subgoal / 未坍缩参数 / 未履行义务
fk goal wing                 # 聚焦某个 subgoal（进入其上下文，约束随 flow-down 可见）
fk next                      # 跳到下一个最浅的未关闭 goal

── 战术（每个 = 一条带证书的边）──
fk refine <g> --via decompose --into wing,engine,tail,fuselage
fk refine <g> --via select-variant cantilever
fk eval   <g> --with mission-analysis --fidelity 0      # 低保真证据
fk exact  <g> --from catalog --match "motor torque>=50" # 库引理关闭 goal
fk procure <g> --from supplier-catalog                  # 标准件终止：证据tier=procured
fk manufacture <g>                                      # 转向：产品树→工艺树（新goal族）
fk compose <g>                                          # 子目标全部关闭后上卷核验父义务
fk abstract <g> --reason "..." --back-to <ancestor>     # 回退开新分支（非破坏）

── 组合子（把主循环写成一条命令）──
fk realize ac0 --until standard-part \
   --strategy "decompose <;> try catalog-exact <;> eval --fidelity ramp"
   # 语义：递归拆解；每层先试目录命中；否则继续拆；逐层升保真验证；
   #       直到所有叶子都是 procure/exact 关闭的标准件

── 检视（Lean 的 #check/#eval/#print）──
fk check wing              # 该 goal 的类型（规格）与已履行义务
fk sorry                   # 全部洞：哪些结论依赖未坍缩参数（sorryAx 式警告）
fk why spindle-motor       # 依赖链回溯：这个电机为何存在 → 一路到 Intent
fk search "torque>=50Nm"   # 目录实例搜索（typeclass resolution）
```

## 3. 飞机例子的完整形态：一段"证明脚本"

```lisp
;; ac.fcad —— LLM 面：项模式/脚本模式；人类可在 CLI 逐条重放同样的战术
(goal flying-machine :spec ((route A B) (range-km (>= 2600)) (cost-wan (< 200))))

(refine flying-machine :via point-mass-model
  :holes (?mtow ?fuel-fraction))          ;; 单质点：属性全是 sorry
(eval flying-machine :with mission-analysis :fidelity 0
  :expect ((range-margin (> 0))))        ;; Breguet 级估算 → tier-0 证据

(refine flying-machine :via decompose
  :into (wing engine nose tail fuselage)
  :flow-down ((mass-budget wing 0.28) (mass-budget engine 0.22) ...)
  :interfaces ((wing@root-load ← skeleton.wing-attach)))   ;; LIVRPS reference 弧

(goal wing :in flying-machine)
(refine wing :via select-variant :choice cantilever)       ;; 方案坍缩
(refine wing :via decompose :into (skin tank rib))
(eval rib :with fea-shell :fidelity 2 :expect ((sigma-y (< 240MPa))))

(goal rib :realize manufacture)          ;; 机加件：转向工艺树
(refine rib :via process-plan :into (stock milling-5axis inspection))
(compose rib-line :from (milling-5axis inspection)
  :roll-up ((takt-min <= 12) (oee >= 0.6)))                ;; 工艺→产线环节
(refine rib-line :via resource-spec :into (mill-5axis-req cmm-req))

(goal mill-5axis-req :as System)         ;; ★ 递归轮次 2：机床=新 System
(refine mill-5axis-req :via decompose :into (bed spindle cnc-drive ...))
(exact spindle-motor :from catalog :match "torque>=50Nm rpm>=12000")
   ;; ★ 标准件：库引理直接关闭；证据 tier = procured
(procure m8-screws :from catalog/gb70)

(compose mill-5axis :roll-up verified)   ;; 机床回装
(compose rib-line ...)                    ;; 产线回装
...
(compose flying-machine :roll-up         ;; ★ 顶层回装：所有下传义务清算
  ((range-km (>= 2600) :by tier-2-sim) (cost-wan (< 200) :by bom-rollup)))
```

整段脚本 = 一个可重放、可机检、可进 DevReady 资产的**证明项**。第 N 代产出的机床
（mill-5axis 节点）若被第 N+1 代产线引用为输入算子，`o_i = t_{i+1}` 即两条链
共享同一 digest——PRSI 递归边在脚本层面可见。

## 4. 这套映射改变了什么（相对前两版设计）

1. **CLI 的中心命令从"建模操作"变成 `fk goals`**。用户面对的不是零件列表，
   而是**义务列表**：还有什么没证明、没坍缩、没验证。这是 MBSE 的灵魂，
   SolidWorks/build123d 都没有这个视图；
2. **"参数态"获得正式身份 = 洞（sorry）**。不再是"还没填的值"，而是被内核追踪、
   会被 `fk sorry` 汇总、且会传染性地标记依赖它的所有结论（Lean 的 sorryAx 机制）；
3. **标准件库 = Mathlib 的位格**。库不是零件文件夹，而是"已证引理集"——每个条目带
   规格类型、证据 tier、适用条件；`exact`/`search` 是实例推断。这直接回答了你笔记里
   "资本 K = 可继承、可执行的设计程序"：库就是 K 的载体；
4. **主循环形式化为组合战术** `realize = repeat (decompose <;> try-exact <;> eval)`，
   递归终止性由"目录命中/外购"保证——Lean 终止性检查器的工程对应物；
5. **LLM 训练面 = 证明脚本语料**。项模式写全脚本（Draft），战术序列改局部（Improve/
   Debug），两脚本合并（Crossover）；评价信号天然分层：语法错 < 类型错 < obligation 未履行
   < eval 指标不达标 < 物理证据缺失——RL reward 的阶梯直接来自 Lean 的错误层级。

## 5. 必须守住的边界（Lean 教我们的诚实）

- 内核只检查**有限协议命题**：身份链接、obligation 履行、预算闭环、终止性；
  **不证物理正确性**——物理结论全部以证据 + tier + 假设账本的形式登记（对齐 bench 的
  AssumptionLedger 与 evidence-tier ceilings）；
- 战术层（L2/L3）可以错、可以试、可以花哨；内核（L1）小而钝。错误永远不会污染可信基；
- 目录条目（公理）必须标注来源与 tier，procured ≠ verified——这与 bench 的立场逐字一致：
  "neither asserts that a physical model is faithful without independent evidence"。
