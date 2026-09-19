# FluxKernel 开发总结报告

> 交付日期：2026-09-19 · 仓库：`E:\DATA\vscode\fluxkernel` · 10 次提交 · 54 个入库文件
> Python 5,852 行 + `.fcad` 示例 228 行 · 验收测试 **21/21 全绿**（pytest 4.9s）

---

## 1. 项目定位

**FluxKernel** 是一个面向 LLM 的命令行 CAD + MBSE 设计系统内核，可概括为
"命令行形态的 SolidWorks × MBSE × git × Lean 战术证明器"。

| 对比对象 | 它是什么 | FluxKernel 的差异 |
|---|---|---|
| build123d | Python 原生 CAD 构造库（可变 B-rep 包装） | 对象模型同位替代：不可变内容寻址节点、几何只是求值投影、带证书与资源向量 |
| text-to-cad | LLM 单发写 build123d 代码、一步产出一个零件 | LLM 写的是"判断序列"（.fcad），每步是一条可审计的生产边，分解/合同/证据链齐备 |

三个不可妥协的性质（设计文档 §1.2）：

1. **一切身份即内容哈希**（`fk1:<kind>:<sha256>`），谱系精确可链（`o_i = t_{i+1}` = digest 相等）；
2. **每条边携带证书与资源向量**，fail-closed（硬义务未履行 = rejected，永久保留为证据）；
3. **内核可信基极小**（core/ + store/ 零第三方依赖，测试强制），重计算全部在插件层。

## 2. 架构（L0–L4 分层，依赖只许自上而下）

| 层 | 模块 | 职责 |
|---|---|---|
| L4 `interface/` | `fcad.py` `runner.py` `diagnostics.py` `cli.py` | `.fcad` S-表达式解析、`fk` CLI 全命令面（33 个子命令）、类型化诊断码（只增不改） |
| L3 `semantics/` | `contracts.py` `operators.py` `goals.py` `ontology.py` | 合同算术（C1–C4）、lint 六规则、术语登记处、8 算子引擎、goals/sorry/risks/why 视图、递归角色本体（8 角色含 Medium） |
| L2 `solvers/` | 9 个插件 | sketch2d（scipy 求解）、feature3d（OCP 挤出/回转/布尔+构造重放）、mission（Breguet）、mate（装配+干涉）、dfam、process、line、catalog、cosim |
| L1 `core/` | `objects.py` `dag.py` `canon.py` | Node/Edge/Certificate/Obligation(hard/soft)、fail-closed 生命周期、lint 闸门注入 |
| L0 `store/` | `objstore.py` | 内容寻址对象库、append-only 边日志、名字索引 |
| 策略层 | `strategy/` `adapters/` | evolve 遗传循环 + MAP-elites 档案、watch 预览（自包含 canvas 渲染器）、mbench trace 导出、.flux 投影 |

## 3. v1.2 合同原生规格模型（本次交付的核心特性）

- **spec = 合同**，九槽位：goals / semantics / assumes / guarantees / budget / effluent / forbidden / not_responsible / time_scale；
- **四段式物理接口**（Assume/Guarantee/Budget/Effluent）：占用与回灌从来不是零，参与组合核验；
- **compose 从简单合取升级为有损耗组合规则**：
  - C1 `ag-coverage`：消费者 Assume 被提供者 Guarantee 覆盖（区间包含判定；**矛盾优先**——同量矛盾区间报 K1 合同冲突，在详细设计前爆掉）；
  - C2 `medium-capacity`：Σbudget 与 Σeffluent ≤ capacity×(1−margin)（介质账本算术，含组合上卷/目录关闭/refine 链的扣除去重）；
  - C3 `effluent-absorption`：下游按**最坏值**（非典型值）吸收上游回灌；
  - C4 `time-scale-stratified`：同合同内时间尺度单一或显式分层；
- **共享介质是一等 Medium 节点**（直流母线/热场/结构壁板），`fk ledger` 账本为派生数据，耦合路径显式可审计；
- **lint 六规则**（L1 输入有界 / L2 保证可判定 / L3 故障枚举 / L4 名词必须解析到术语登记处 / L5 时间尺度单一 / L6 自由参数有界或有检测）：任一缺失 → 节点永不高于 `proposed`，列入 `fk risks`；
- **义务分 hard/soft**：hard 未履行 → rejected；soft（重量/成本）只进证据向量，"优化找点、合同守门"。

## 4. 验收测试（21/21 全绿）

| 里程碑 | 测试项 |
|---|---|
| M0 | 1 黄金向量（跨实现一致性）· 3 fail-closed/I3 级联 · 4 精确链接/I1 · 19 lint 闸门+L4 拒收 |
| M1 | 2 谱系命名稳定（改参数旧引用仍解析）· 5 草图求解残差<1e-6 · 6 几何 10×20×3=600mm³±1e-6 + STEP/STL 回读 |
| M2 | 7 端到端 aircraft.fcad · 9–11 integrate（多 goal 关闭/非破坏/结构共享）· 12–13 co-design（plant-model-current 失效检测 / co-ground 联合接地）· 17 四段合同 C1–C4+超容 rejected · 18 矛盾暴露 K1 · 20 elicit 六步 |
| M3 | 8 realize 终止性 · 14–16 evolve（系谱可审计 / 拓扑变异后 verify 通过 / 档案沉淀可被 exact 命中） |
| 纪律 | 分层检查：core/ store/ 零第三方 import（AST 强制） |

## 5. 两次端到端实测

### 5.1 examples/aircraft.fcad（M2 验收走查）

30 个表单、0 拒绝、33 条边全部 promoted：Intent → 点质量洞模型 → Breguet 评估 →
五子系统分解 → 机翼分支几何（草图→拉伸 600mm³）→ 工艺族 → 产线节拍 →
机床 Resource→System（PRSI 递归）→ 目录 exact/procure 关闭叶目标 → 逐级 compose 回装；
双介质账本（直流母线 3600/4000W、舱内热场）全程实时核验；trace 包 42 条跨代链路。

### 5.2 examples/sha_pek.fcad —— "我想要从上海飞到北京"（41 个表单）

- **任务合同**：SHA→PEK 大圆 1088km、带储备航程 ≥1300km、2 人 180kg、MTOW 1500kg 级；
- **拆分链**：点质量（全参数洞=sorry）→ Breguet 评估（航程 5344.7km、裕度 +4044.7km）→
  参数坍缩（MTOW 1200 / ff 0.28 / L/D 14 / sfc 8.33e-6 / V 95）→ 分解
  wing/epu/fuselage/avionics（质量预算 260+320+380+40≤1500 逐项核验）→
  EPU 从目录 exact 关闭 → compose 回装；
- **机翼结构拆分**：wing → skin/spar/rib（预算 120+80+12≤260kg），翼肋接地
  （草图含参数洞 hw∈[500,700] → 600×200×3mm 铝制件 972g），回装 wing-assy；
- **配套产线/机床（PRSI 递归边）**：rib-solid → manufacture 工艺族（备料/三轴铣/检验）→
  产线（节拍 56.9min、OEE 0.83）→ 机床 Resource → 机床作为 System 分解
  （床身/主轴电机/伺服驱动）→ 目录 exact/procure 关闭 → fab-mill 回装；
  直流母线账本 Σ3600≤4000W 实时把关，`fk why fab-mill` 沿"机床←翼肋←机翼←飞机 Intent"
  全程可溯；
- **1:20 几何样机**：五零件全部接地（机身=纺锤回转体 449cm³/557g、机翼=550×60×6 平板、
  平尾、后掠垂尾=拉伸+90° 旋转、电机=铝圆柱），assemble 装配（总 665cm³、826.6g），
  STEP/STL 导出，`fk verify` 全库通过（53 节点/50 边，49 promoted + 1 故意拒绝）；
- **fail-closed 现场演示**：故意不可达的期望（裕度>999999）被 `expect-met` 拒绝并永久留档；
- 预览：`preview/index.html` 自包含渲染器（拖拽旋转/滚轮缩放），`file://` 双击即开。

## 6. 实测发现并修复的问题（测试的真实价值）

| # | 问题 | 后果 | 修复 |
|---|---|---|---|
| 1 | mission 插件 SFC 单位差 1000 倍（/3.6 误代 /3600） | 航程算出 5.3km | 量纲修正为 kg/(N·s) |
| 2 | 航程需求只扫 goals 槽位 | 裕度检查"空真" | goals/guarantees/assumes 全扫 + 双 bounds 形态 |
| 3 | C1 环境透传让消费者自己的 Assume"自覆盖" | 同量矛盾区间被掩盖 | 矛盾检测优先于覆盖检测（K1 先报） |
| 4 | 介质账本重复记账（组合上卷/exact 关闭/refine 链） | Σbudget 虚高数倍 | 三类上卷扣除规则 |
| 5 | OCCT `StlAPI_Writer` 默认输出 ASCII STL | 预览解析到 5.4 亿三角形炸掉；dfam 悬垂检查静默失效 | 强制二进制 + 解析端 ASCII 回退 |
| 6 | OCCT 8.0.1 `TopoDS_Builder.Add` 段错误 | 装配体导出崩溃 | 改走 `BRepAlgoAPI_Fuse` 路径 |
| 7 | OCP 8.0 `Bnd_Box.Get()` 返回类型变更 | 几何属性崩溃 | `CornerMin/CornerMax` |
| 8 | 预览页 ES module + CDN + XHR 在 `file://` 全被 CORS 拦截 | 页面空白 | 零依赖自包含 canvas 渲染器（base64 内嵌） |
| 9 | 装配干涉（垂尾切入平尾 120mm³） | —— | 被 `no-interference` 义务当场拒绝（系统正常工作的证明），抬高 3mm 后放行 |

## 7. 快速上手

```bash
fk init                                # 建 .fk/ 对象库（类 git）
fk run examples/sha_pek.fcad           # 项模式：整脚本 = 一串 DAG 提交
fk goals / fk sorry / fk risks         # 战术状态：未关闭子目标 / 参数洞 / 未结算风险
fk why sha-pek-model                   # 谱系回溯到 Intent
fk ledger <medium>                     # 介质账本：Σbudget/Σeffluent vs capacity
fk lint / fk elicit <node>             # 合同完备性检查 / 六步引导式合同提取
fk export sha-pek-model --step x.step --stl x.stl
fk trace --out dir/                    # MechanogenesisBench 证书包
fk verify                              # 全库 fail-closed 复检
fk realize <root> --until standard-part   # 组合子：拆解到标准件自动停机
fk evolve <goal> --pop 8 --gen 3 --select-by range_km   # 遗传优化（策略层）
```

## 8. 设计决策要点（为什么这样建）

- **几何 = 节点的求值投影**，不自动生成：接地是显式动作（sketch→extrude/revolve），携带证据 tier——与 text-to-cad 的"单发代码生成"是根本不同的信任模型；
- **优化在内核外**（evolve/NSGA-II/MAP-elites 属策略层）：内核只管合同算术与 fail-closed，"优化找点，合同守门"；
- **两个硬目标互斥不是优化问题，是需求错误**：C1 在详细设计之前就把矛盾区间暴露为 K1；
- **失败是资产**：rejected 边永久保留（有信息的失败），脚本失败继续执行、退出码非零；
- **诊断码表只增不改**：S1…M1 + K1/G2/G3/T3/U2/L1–L6/P1，直接构成 LLM 强化学习的 reward 阶梯。

## 9. 当前边界与后续路线

| 项 | 现状 | 下一步 |
|---|---|---|
| 几何精细度 | 挤出/回转/布尔 + 平板/回转体级样机 | shell/放样/倒角插件，蒙皮-翼梁-翼肋逐件接地 |
| 标准件目录 | 机床电机/紧固件/材料（演示数据） | 接入真实航电/动力/紧固件供应商目录 |
| Lean 对接 | trace 包字段对齐 bench canonical IR | Lean 核复算回写 ProofRef（M3 完整形态） |
| LLM 面 | .fcad 项模式（文法极小，SFT 友好） | MCP/工具 schema、SFT 语料导出（边=样本） |
| 仿真证据 | tier-0/1 启发式 + 闭环代理 | 外部仿真引擎按 tier 登记 |

## 10. 交付物清单

```
fluxkernel/            内核包（L0–L4 + 策略层 + 适配器）
catalog/               标准件库（motors / fasteners / materials）
examples/aircraft.fcad 验收走查（30 表单）
examples/sha_pek.fcad  上海→北京实测 + 1:20 几何样机（29 表单）
tests/run_tests.py     验收测试 1–20 + 分层纪律（21/21）
tools/                 示例/预览生成器
preview/index.html     自包含模型预览（file:// 可开）
docs/design/           设计文档全套副本（v1.0 主方案 + v1.1/v1.2 增补）
```
