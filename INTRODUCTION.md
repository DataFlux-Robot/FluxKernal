# FluxKernel 实现介绍（评审用）

> 本文面向评审 agent，自包含。仓库：`E:\DATA\vscode\fluxkernel`（git，单 `master` 分支）。
> 所有数字与命令均在 2026-09-19 当前 HEAD 验证过；文末给出复核命令。

## 1. 定位：这是什么，不是什么

FluxKernel 是一个**面向 LLM 的机械系统工程内核 + CLI**，设计参照 build123d 的"CLI 优先、代码即界面"形态，但解决的是不同层次的问题：

| | build123d / text-to-cad | FluxKernel |
|---|---|---|
| 核心产物 | 几何体（B-Rep） | **带证书的精化图**（CARG），几何只是节点的求值投影 |
| 接口对象 | Python API / 提示词 | `.fcad` S-表达式 DSL + 32 个 CLI 子命令 |
| 正确性来源 | 几何内核的布尔运算 | 算子前置/后置条件、合同组合核验、义务生命周期 |
| 失败处理 | 抛异常 | fail-closed：失败轨迹永久保留为证据节点 |

一句话：**build123d 回答"这个零件长什么样"，FluxKernel 回答"从'上海飞北京'这个意图出发，每一层拆解决策凭什么成立、证据在哪、哪条腿还是 sorry"**。

## 2. 核心抽象：CARG

Certificate-carrying, content-Addressed Refinement Graph。

- **内容寻址**：每个对象（节点/边/术语/介质/档案）的 digest = `fk1:<kind>:<sha256(canonical_json)>`，规范化 JSON（排序键、紧分隔符、UTF-8）。同名不同内容 = 不同对象；谱系（lineage）**永不进 digest**，由边日志 + 索引派生——这是"改参数后旧引用仍可解析"（谱系命名稳定性）的基础。
- **证书携带**：每条边携带 certificate（义务判定记录 + 证据引用）；几何、仿真、目录条目都要经过显式 `refine/evaluate` 接地并附带证据后才可被后续组合引用。
- **fail-closed 生命周期**：`proposed → executed → evidenced → verified → promoted`，任一环节失败停在原地或转 `rejected`（永久保留）。C0（硬义务）拒绝优先于 lint 闸门；lint 失败的边封顶在 `proposed` 并列入 `fk risks`。

## 3. 五层架构

```
L4  interface/   fcad.py(S-表达式解析) runner.py cli.py(32命令) diagnostics.py(诊断码注册表)
L3  semantics/   operators.py(八算子引擎) contracts.py(合同算术C1-C4+lint+ledger) ontology.py goals.py
L2  solvers/     9 个插件（全部可失败计算唯一居所；OCP/numpy 只允许出现在这里）
L1  core/        objects.py dag.py(提交纪律) canon.py —— 零第三方依赖（有测试强制）
L0  store/       objstore.py（内容寻址对象存储，`.fk/` 目录）
+   strategy/    evolve.py(遗传优化) watch.py(预览) preview.py(自包含渲染页) —— 不进内核
+   adapters/    mbench.py(trace.json/certificates/chain.json) fluxmeme.py(.flux 投影)
```

分层纪律有测试守卫：`core/` 与 `store/` 的第三方 import 白名单为空，违反即测试失败。

## 4. 数据模型（L1）

- **Node**：`role ∈ {Intent, System, Component, Part, Process, Line, Resource, Medium}`（递归角色本体，**无全局层号**，Resource≅System 支持 PRSI 递归——"为造机床而造机床"合法）；`facet ∈ {BODY, MIND}`；`spec`（v1.2 九槽位合同）；`params`/`variants`/`ground`/`evidence`/`supersedes`。
- **Edge**：`op ∈ {refine, compose, abstract, evaluate, exact, procure, manufacture, integrate}` + `inputs/output/state/certificate/coverage/resources`。分解（decompose）实现为 refine 的多输出 + flow-down。
- **Obligation**：`class ∈ {hard, soft}`。hard 失败 → 边 rejected；soft 不拦截，只进证据向量（作为 evolve 的选择压力）。

## 5. 合同系统（v1.2 增补，`semantics/contracts.py`）

九槽位 spec：`goals / semantics / assumes / guarantees / budget / effluent / forbidden / not_responsible / time_scale`；接口四段式 Assume/Guarantee/Budget/Effluent。真实示例（摘自 `examples/sha_pek.fcad`）：

```lisp
(goal sha-pek :kind aircraft
  :spec (contract
    (goals (r1 "fly Shanghai Hongqiao to Beijing Capital nonstop with reserves"
               :falsifiable t
               :measure "mission sim: range_km vs 1088km great-circle + 45min reserve"
               :terms (range aircraft))
           (p1 "carry two occupants plus baggage" :falsifiable t
               :measure "W&B sheet at MTOW" :terms (payload)))
    (assumes (route1 "SHA-PEK great-circle corridor"
                     :bounds ((dist_km (>= 1050) (<= 1120)))))
    (guarantees (gr1 "delivers the mission with reserves"
                     :bounds ((range_km (>= 1300)) (payload_kg (>= 180)))))
    (budget (mass_kg (<= 1500)))
    ...)))

;; 共享介质：直流母线（Medium 一等节点，budget 经 ":medium" 引用）
(node dc-bus :role Medium :kind dc-bus
  :spec (medium (capacity (power_w (<= 5000))) (margin 0.2)))
```

**四条有损组合规则**（compose/integrate 时机判生成判定，机判非提示词判）：

- **C1 ag-coverage**：父 Guarantee 区间包含子 Assume 区间；同量矛盾**优先**报 K1（先于覆盖判定，防环境自掩盖）。
- **C2 medium-capacity**：Σbudget ≤ capacity×(1−margin)，账本算术含上卷扣除（`_subsumed_allocations` 防组合上卷/exact 关闭/refine 链重复记账）。
- **C3 effluent-absorption**：下游 assume 上界 ≥ 上游 effluent 最坏值；介质中介的回灌交账本。
- **C4 time-scale-stratified**：跨时间尺度组合需显式分层声明。

**lint 六规则 L1–L6**（客观性闸门）：输入空间有界 / 保证可判定 / 故障模式枚举 / 时间尺度单一 / 自由参数有范围或检测 / **L4：名词必须解析到术语登记处 term digest**（term 亦是内容寻址对象，digest 变更触发 `term-current` 失效传播）。

`fk ledger <medium>` 派生介质账本；`fk elicit` 六步固定追问把口头需求逼成五槽位合同（口子进 risks 不抹平）。

## 6. 八算子与 Lean 同构

| Lean | FluxKernel |
|---|---|
| goal/spec | 合同 goals 槽位 |
| tactic | 算子（refine/compose/...） |
| exact lemma | 目录关闭（catalog `exact`） |
| sorry | 参数洞 `(param x)` + `fk sorry` 传染链 |
| Mathlib | 标准件目录 catalog/ |

算子统一骨架：前置条件 → flow-down 合同下发 → L2 插件执行 → 结构性义务 → 证书装订 → `dag.commit`（I1/I2/I3 检查 + C0 + lint 闸门）。`evaluate` 断言 expect→证据分级；`abstract` 非破坏（supersedes）；`integrate` 做跨子树接口一致性（interface-union-consistent）+ 关闭祖先 goal 逐一核验。

## 7. 接口层

**CLI（32 子命令）**：`init run goals sorry risks goal next lint ledger elicit node refine eval exact procure compose integrate abstract manufacture realize evolve watch check graph why log status search show export trace verify`。诊断码注册表（S1/T2/U1/O2/I1/I2/I3/C0/E1/M1...）只增不改。

**`.fcad` DSL**：S-表达式，顶级构造子 + 合同子语法 + `(param x)` 洞。`fk run` 语义：任一表单失败 → 该边 rejected、脚本继续、退出码非零（脚本内可含故意拒绝的对照表单）。`fk why <name>` 沿边回溯谱系。

## 8. L2 插件（9 个）

`feature3d`（construction 完整记录 + `rebuild_brep` 可重放；STEP/STL 导出）、`sketch2d`（约束残差<1e-6）、`mission`（Breguet 航程，SI 单位 kg/(N·s)）、`catalog`（区间 admits 查询）、`mate`（装配位姿 + 干涉 Common>ε）、`process`（工步 takt/cost）、`line`（OEE 上卷）、`dfam`（壁厚/悬垂）、`cosim`（BODY+MIND 联合仿真）。每个插件返回 `(result_fields, evidence, obligations)`。

## 9. 案例研究：SHA-PEK（`examples/sha_pek.fcad`，75 顶级表单）

当前实测（每次运行确定性重现，v03 进化后）：

- **314 个内容寻址对象** = 153 节点 + 153 边；**152 边 promoted + 1 边 rejected**（e2x：故意超容的对照表单，验证 fail-closed）。
- 边算子分布含 **22 条 print 边**；机翼经 wingbox 架构模板分解（10 子件按骨架帧就位、装配零干涉）；机床按 gantry 模板开发；样机由 scale-instance 从真实子树派生。
- 任务分析链：point-mass → Breguet（SI sfc）→ param-perturb → **航程 5344.7 km ≥ 1300**（假设 L/D=14）；**闭环复算 6127.3 km**（fidelity 1，用 aero-2d 实测 L/D=16.05 覆写假设值——下层证据替换上层假设，指标仍成立）。
- 每层证据（E2 仿真矩阵）：wing `aero-2d`（L/D≥14 硬断言）、epu `prop-map`（推力/电流）、rib `beam-fe`（截面惯量/应力/挠度 vs 屈服）、装配 `mass-rollup`（质量/质心/盒惯量）、整机 mission 复算。
- 机翼结构：wing → skin/spar/rib；skin/spar 接地（3000×1500×2 铝蒙皮、3000×200×30 铝梁）后由 reference-printer 打印；翼肋保留完整制造分支（manufacture → 工艺 → 产线 → 机床）。
- 机床链：rib `manufacture` → 产线 → fab 需求 → decompose（bed/spindle/drive on dc-bus）→ spindle/drive 目录关闭；**bed 接地 800×600×60 并由 reference-printer 打印——printer→bed 双代链接真实存在于 DAG**。
- **打印机自举（E1-3 硬性要求）**：reference-printer 自身 decompose 一轮（frame/stepper/board），frame 由它自己打印（同 digest 自举边），stepper/board 目录关闭——设备开发递归 ≥1 级且全闭合。
- dc-bus 账本 3700/4000W；cabin-air 热账目平衡（曾故意把打印机废热挂进客舱介质，被 `fk verify` 的介质复检抓住后修正——fail-closed 在案例层的真实回报）。
- 1:20 样机分支：五零件接地 → 装配（干涉门）→ **五个样机零件全部由 reference-printer 打印终止**。
- 终态：**`fk goals` = OPEN GOALS (0)**；`fk why bed-printed` 逐行带 DSL 边名（`[e42]`，P5 修复）回溯到 Intent。

## 10. 策略层（不进内核）

- `evolve`：变体实例化 → eval → 选择 → 五类变异边（param-perturb/integrate/decompose/process-swap/variant-reselect）→ MAP-elites 档案按行为描述子分格存 `kind=archive`，可被 `fk exact --from archive` 命中（代际审计：系谱可回放、拓扑变异后 `fk verify` 通过）。无第三方 GA 库。
- `realize` 组合子：`repeat(decompose <;> try catalog-exact <;> eval)`，`--until standard-part` 保证终止。

## 11. 测试与验收

`python -m pytest tests/ -q` → **30 passed**（验收测试 1–20 + 分层纪律 + 进化回归 21–29：闭合判定/洞坍缩/证据覆盖/print 终止/打印机自举/仿真矩阵/realize 终止集/全链案例/termination-swap）。覆盖：黄金向量、fail-closed/I3、精确链接/I1、谱系命名稳定、草图残差、几何体积 600mm³±1e-6 + STEP/STL 回读、端到端、integrate 三性质、co-design 两性质、C1–C4 生成判定 + 超容 rejected + 矛盾暴露、lint 闸门 + L4 拒收、elicit 六步、realize 终止性、evolve 三性质。

规模：git 追踪 56 文件，Python 6107 行，标准库为主；OCP（cadquery-ocp）与 numpy 仅在 L2/策略层。

## 12. 设计决策与权衡（建议评审焦点）

1. **几何是投影不是本体**——撤掉某条 ground 边后 `fk goals/risks` 正确降级。
2. **矛盾优先于覆盖**（C1）——防父合同环境透传掩盖消费者矛盾；测试 18 覆盖。
3. **soft 义务不拦截**——evidence-coverage（E0-3）只进 risks；选择压力留给 evolve。
4. **闭合是递归谓词而非出边启发**（E0-1）——被 compose 消费 ≠ 已实现；终态成品不误报 open。几何接地不再单独闭合 Part：必须分配终止路线（catalog/print/manufacture）。分解的作用域边实现其父，子边不行。
5. **双终止集**（E1）——结构件收敛到共享打印资本（reference-printer），"不限尺寸"作为 Assume 存在（需求层承诺，非内核可验证）；机床递归不被打印汇聚吞掉：打印机自身完整开发一轮（自举边）。
6. **lineage 不进 digest**——谱系命名稳定性的根；代价是 digest 不能单独反推历史。
7. **rejected 永久保留**；lint 闸门封顶 proposed 而非删除。
8. **启发式仿真器的诚实**——aero-2d/prop-map/beam-fe/mass-rollup 的 tier 如实标注（1=一阶估算/2=几何记账），公式写在 docstring 里可手算复核；禁止冒充高保真。
9. **realize 的终止度量**——每步要么关闭 goal，要么分解出严格更小的预算份额；无预算节点不自动分解；自动分解总量封顶 8。

## 13. 已知限制（诚实清单）

- 单机单用户，无并发控制；`.fk/` 是文件存储。
- OCP 偶发平台问题（Bnd_Box API 变更、TopoDS_Builder 段错误已绕开，走 BRepAlgoAPI_Fuse 路径）。
- 合同算术是区间/账本级，不做符号推理；`covers` 是区间包含判定。
- cosim 为单节点合并模式的最简实现；evolve 未做并行评估。
- 预览渲染器是画家算法（无深度缓冲），超大网格会排序失真；当前 1094 三角面无问题。
- 诊断码与人读消息未做 i18n。
- runner 对插件异常捕获 `(ContractError, ValueError, RuntimeError, KeyError)`——插件自身的 TypeError 会 crash 而非转 rejected（**有意**：bug 不该被吞成证据，但应在部署环境配外层看护）。
- dfam-print 阈值从宽（壁厚 0.5mm/悬垂 60%/长宽比 12）——误判"不可打印"会让树退化成全制造分支；随证据积累收紧。
- .fcad 闭环 overrides 用字面值写入（DSL 无动态引用）；字面值与子树证据的一致性由测试 28 断言。

## 14. 快速复核命令

```bash
cd E:\DATA\vscode\fluxkernel
.venv\Scripts\fk.exe run examples\sha_pek.fcad        # 退出码 1 = 预期（含故意拒绝表单）
.venv\Scripts\fk.exe goals | more                     # open goals / risks
.venv\Scripts\fk.exe why fab-mill                     # 机床←翼肋←机翼←飞机←Intent 回溯
.venv\Scripts\fk.exe ledger dc-bus                    # 3600/4000 W
.venv\Scripts\python.exe -m pytest tests\ -q          # 21 passed
```

配套文档：`REPORT.md`（交付报告，10 节）、`docs/design/`（原始设计文档系列）、`README.md`。

## 15. 给评审 agent 的建议切入点

1. fail-closed 是否有旁路（例如 transform 抛异常被 `except Exception` 全捕后，边处于什么状态？为何这样选？）
2. C2 账本的上卷扣除六类是否完备（compose/integrate/exact/procure/refine/evaluate）？
3. 内容寻址 + lineage 派生：改一个参数后，为什么旧名字仍解析？（测试 2 的机制）
4. L4 term 失效传播的粒度是否过粗/过细？
5. Medium 的 margin 语义：capacity×(1−margin) 作为"可用容量"是否在所有 C2 判定中一致？
