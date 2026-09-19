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

## 9. 案例研究：SHA-PEK（`examples/sha_pek.fcad`，41 顶级表单）

当前实测（每次运行确定性重现）：

- **109 个内容寻址对象** = 53 节点 + 50 边；**49 边 promoted + 1 边 rejected**（e2x：故意超容的对照表单，验证 fail-closed）。
- 节点角色分布：Intent 1 / System 11 / Component 27 / Part 5 / Process 4 / Resource 2 / Medium 2 / Line 1。
- 边算子分布：refine 38（含全部分解）/ compose 5 / evaluate 3 / exact 2 / manufacture 1 / procure 1。
- 任务分析链：point-mass → Breguet（SI sfc）→ param-perturb（mtow 1200 / ld 14 / sfc 8.333e-6 / v 95）→ **航程 5344.7 km ≥ 1300 km 保证，裕度 +4044.7 km**（e2c 复检表单）。
- 机翼结构分解：wing(260kg) → skin(≤120) + spar(≤80) + rib(≤12)；翼肋经草图约束接地 → 600×200×3 mm 铝板挤压 → `wing-assy` compose 回。
- 制造链：rib `manufacture` → 产线（takt≤60s, OEE≥0.5）→ fab 需求 → 机床 decompose（bed 100W + spindle 3000W + drive 500W，**全部 `:medium dc-bus` 引用**）→ 目录 exact/procure 关闭 → `fab-mill`。`fk why fab-mill` 可全程回溯到 Intent。
- dc-bus 账本：3600W / 可用 4000W（5000×(1−0.2)）。
- 1:20 几何样机分支：五零件草图→拉伸/旋转→装配（含干涉门）→ STEP/STL 导出 → `preview/index.html`（零依赖 canvas 渲染，三组场景：装配体/分解零件/全尺寸翼肋）。

## 10. 策略层（不进内核）

- `evolve`：变体实例化 → eval → 选择 → 五类变异边（param-perturb/integrate/decompose/process-swap/variant-reselect）→ MAP-elites 档案按行为描述子分格存 `kind=archive`，可被 `fk exact --from archive` 命中（代际审计：系谱可回放、拓扑变异后 `fk verify` 通过）。无第三方 GA 库。
- `realize` 组合子：`repeat(decompose <;> try catalog-exact <;> eval)`，`--until standard-part` 保证终止。

## 11. 测试与验收

`python -m pytest tests/ -q` → **21 passed**（验收测试 1–20 全绿 + 分层纪律检查；pytest 兼容亦可 `python tests/run_tests.py` 直跑）。覆盖：黄金向量、fail-closed/I3、精确链接/I1、谱系命名稳定、草图残差、几何体积 600mm³±1e-6 + STEP/STL 回读、端到端、integrate 三性质、co-design 两性质、C1–C4 生成判定 + 超容 rejected + 矛盾暴露、lint 闸门 + L4 拒收、elicit 六步、realize 终止性、evolve 三性质。

规模：git 追踪 56 文件，Python 6107 行，标准库为主；OCP（cadquery-ocp）与 numpy 仅在 L2/策略层。

## 12. 设计决策与权衡（建议评审焦点）

1. **几何是投影不是本体**——评审可探：撤掉某条 ground 边后 `fk goals/risks` 是否正确降级。
2. **矛盾优先于覆盖**（C1）——防父合同环境透传掩盖消费者矛盾；测试 18 覆盖。
3. **soft 义务不拦截**——选择压力留给 evolve；评审可辩：这会不会让 soft 失败被无限遗忘？（现状：进证据向量与 risks。）
4. **lineage 不进 digest**——谱系命名稳定性的根；代价是 digest 不能单独反推历史，需边日志。
5. **rejected 永久保留**——存储单调增长；无 GC（设计上视为特性）。
6. **lint 闸门封顶 proposed 而非删除**——失败轨迹即证据。
7. **evolve/cosim 是策略层最简可验收实现**——不是论文级 MAP-elites。

## 13. 已知限制（诚实清单）

- 单机单用户，无并发控制；`.fk/` 是文件存储。
- OCP 偶发平台问题（Bnd_Box API 变更、TopoDS_Builder 段错误已绕开，走 BRepAlgoAPI_Fuse 路径）。
- 合同算术是区间/账本级，不做符号推理；`covers` 是区间包含判定。
- cosim 为单节点合并模式的最简实现；evolve 未做并行评估。
- 预览渲染器是画家算法（无深度缓冲），超大网格会排序失真；当前 1094 三角面无问题。
- 诊断码与人读消息未做 i18n。

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
