# FluxKernel 开发进展报告

日期：2026-09-19（第三轮评审后更新）· 仓库：`E:\DATA\vscode\fluxkernel` · 29 次提交
配套文档：`INTRODUCTION.md`（架构介绍，面向评审）· `REPORT.md`（初版交付报告）· `docs/design/`（设计文档系列）

> 定位回顾：面向 LLM 的**通用**机械系统工程内核 + CAD CLI（build123d 形态的 `.fcad` DSL + 33 子命令）。核不是几何而是**带证书的内容寻址精化图（CARG）**——几何是节点的求值投影。开发纪律：机制通用、内容（案例/目录/模板）为数据、内核 L0/L1 零第三方依赖且零改动。

## 0. 当前快照（全部数字为本日复跑验证）

| 指标 | 值 |
|---|---|
| 测试 | **36/36 全绿**（`pytest tests/ -q`，≈24s） |
| 规模 | 64 个 git 追踪文件，Python 7875 行 |
| CLI | 33 子命令；`.fcad` DSL 含 `(print ...)`、`:at`、`:machine`、`:template` |
| 求解插件 | 14 个（几何 4 + 仿真 4 + 制造 4 + 任务 2）；目录 6 文件；**架构模板 2 个** |
| 标志案例 SHA-PEK | **119 表单 / 314 对象（153 节点 + 153 边）/ 152 promoted + 1 故意 rejected / 22 条 print 边** |
| 案例终态 | **OPEN GOALS (0)** · verify 全绿 · dc-bus 3820/4000W · 装配干涉门 = 0 干涉 |
| 任务链 | 假设航程 5344.7 km（L/D=14）→ **闭环复算 6127.3 km**（aero-2d 实测 L/D=16.05 覆写假设；数字取自运行证据） |
| 双代闭环 | printer→（机床结构件）+ catalog→（运动件）= 机床；**机床 `:machine`→rib-1 工序**——两条设备链都在 DAG 边的 inputs 里 |

## 1. 开发阶段总览

### 阶段一：初版交付（`Initial commit`…`9cf6766`）
五层内核（L0 内容寻址存储 / L1 数据模型与提交纪律 / L3 合同算术 C1–C4 + lint L1–L6 / L2 插件 / L4 CLI+DSL）+ 适配器 + evolve/watch 策略层；验收测试 1–20 全绿；SHA-PEK 案例首跑通（41 表单）；1:20 几何样机 + file:// 安全的自包含渲染器。

### 阶段二：首轮评审与进化 E0–E5（评审 v01 → 进化方案 v2.0，8 提交）
评审在独立工作区复现全部声明，指出 P1–P5（闭合判定双向错误、传染过粗、证据密度不足、终止靠手工、显示小项）。进化落地：**递归闭合不动点**（被 compose 消费≠已实现；终态成品不误报）、**数据引用传染 + 坍缩洞标注**、evidence-coverage soft 义务、**双终止集**（dfam-print 硬门 + print 算子 + 打印机自举一轮）、**每层仿真矩阵**（aero-2d/prop-map/beam-fe/mass-rollup，公式可手算）、realize 终止集感知升级、evolve termination-swap。案例 41→75 表单，首达 OPEN(0)。

### 阶段三：二轮复核（评审 v02）
独立复跑确认 E0–E5 全部兑现（"审阅意见全部被理解并正确实现，而非表面应付"），指出三个新缺口：**G1** 生产算子身份在 args 不在 inputs（I3 精确链接不覆盖打印机本身）；**G2** 铣床被开发却从未被使用（mill→rib 只在注释里）；**G3** 闭环航程报告值 6143 vs 证据值 6127.3（手算转抄）。

### 阶段四：三轮诊断与骨架层进化（评审 v03 → G1–G3 + E6，6 提交）
用户观察"机翼没拆分、机床不像机床"被证实为更深层问题——**实现跳过了 Skeleton（几何架构）层**：e4d 组合的是未接地合同节点而非 skin-solid/spar-solid（真 bug）；机床分解只有 kind 名字。修复全部落地（§2）。

## 2. 当前通用能力清单（本轮新增机制，全部零 trick）

| 能力 | 机制 | 语义保证 |
|---|---|---|
| **Placement / Location** | `:at [dx,dy,dz]` 或 `((x y z) (ax ay az deg))` 施加于 extrude/revolve | 放置入 `construction` 并在 `rebuild_brep` 重放——谱系稳定；revolve 轴同步参数化（修掉硬编码 Y） |
| **帧系统（Skeleton）** | 任意节点可携 `spec.frames`；`:at (:frame 名字)` 解析 | 布局单源：骨架帧经 decompose 的 `specs` 下发，子件相对父骨架接地 |
| **算子身份链接（G1/G2）** | print 边 `inputs=[工件,打印机]`；`manufacture :machine` 槽并入工艺边 inputs | I1/I2/I3 精确链接覆盖**生产算子实例**——打印机/机床的产出边 rejected 时，使用它的边自动拒绝 |
| **input-realized 硬门（E6-2b）** | compose 对 Part 角色输入的硬义务（U2） | 组合未实现零件 → C0 拒绝（本轮它抓到了案例里的真 bug）；Component 仍可合同级组合 |
| **架构模板（E6-4）** | `decompose :template <名>` 加载 `catalog/archetypes/*.json` | 模板=纯数据（子件/角色/合同/骨架帧/介质引用，介质名字加载时解析为 digest）；显式 args 逐键覆盖 |
| **派生缩放（E6-3）** | `scale-instance :ratio` 从输入祖先子树收集接地几何缩放融合 | construction 按值记录（boolean 模式）可重放；**边 inputs 精确链接每个源**——派生物可证明由这些件组成 |

案例中已验证：wingbox 模板（双蒙皮+双梁+6 肋，全部按骨架帧就位，compose 经**真实干涉门**零干涉）；gantry-mill 模板（床身/立柱/横梁/Z头打印 + 导轨/丝杠/伺服/主轴/CNC 目录）；样机由真实子树 1:20 派生（手画平行几何分支已删除）。

## 3. SHA-PEK 案例与 11 步覆盖度

| 步骤 | 状态 | 证据 |
|---|---|---|
| 1 模糊需求 | ✅ | 九槽合同（可否证 goals/术语/禁项/免责） |
| 2 单质点+参数态 | ✅ | 五洞→Breguet→坍缩→复检 + 故意失败样本永久保留 |
| 3 子系统仿真 | ✅ | wing=aero-2d（L/D≥14 硬断言）、epu=prop-map、rib=beam-fe、装配=mass-rollup |
| 4 坍缩+再拆 | ✅ | **wingbox 模板**分解（骨架就位+零干涉装配）；fuselage→舱壳/座椅/hstab/fin；avionics 目录直闭 |
| 6–9 零件→工艺→产线→设备需求 | ✅ | rib-1 `:machine fab-mill` 加工；line takt/OEE 上卷 |
| 10–11 设备方案→零件 | ✅ | **gantry 模板开发机床**；printer→结构件双代链接；全部叶子落双终止集 |
| 终止性 | ✅ | OPEN GOALS (0)；闭合=递归谓词 |
| 闭环验证 | ✅ | e63 mission 复算用实测 L/D → 6127.3 km ≥ 1300 |

## 4. 质量与验证

- **36 项测试** = 验收 1–20 + 分层纪律（core/store 零第三方 import）+ 回归 21–36：闭合判定/洞坍缩/证据覆盖/print 终止/打印机自举/仿真公式独立复算/realize 终止集/全链案例/termination-swap/**算子身份 I3/Placement 重放一致性/模板加载与介质解析/scale-instance 派生**。
- `fk verify` 全库纯重算全绿（义务/证据/术语/介质账本）。
- fail-closed 的真实回报记录：① 打印机废热误挂客舱介质被账本复检拦截；② input-realized 抓到 e4d 组合未实现件；③ dfam 连通门抓到装配多壳（后修正为"刻意装配=多壳作业"语义）；④ e5 的无证据 range rollup 被闭合规则暴露后删除（由 e2c/e63 硬断言把关）。
- 数字纪律（G3）：报告数字一律取运行证据（本报告 6127.3 来自 store evidence）。

## 5. 已知限制与下一步

1. 闭环 overrides 在 DSL 中是字面值（无动态引用）；一致性由测试断言。→ 下一步：DSL 引用语法。
2. dfam-print 阈值从宽（壁厚 0.5/悬垂 60%/长宽比 12）；"不限尺寸打印"是需求层 Assume。→ 随案例标定收紧。
3. 启发式仿真器是 tier-1 估算（公式在 docstring，禁止冒充高保真）。
4. runner 异常捕获不含 TypeError（有意：bug 不吞成证据）。
5. realize 的自动分解是预算均分启发；evolve 的 termination-swap 未接成本模型。
6. 单机文件存储；rejected 永久保留（特性，无 GC）。

优先级建议：目录库真实数据扩充 → DfAM 标定 → overrides 动态引用 → evolve 成本压力 → 更多架构模板（其余机型/设备类）。

## 6. 复核命令

```bash
cd E:\DATA\vscode\fluxkernel
.venv\Scripts\python.exe -m pytest tests\ -q       # 36 passed
.venv\Scripts\fk.exe run examples\sha_pek.fcad     # rc=1（e2x 故意拒绝）
.venv\Scripts\fk.exe goals                        # OPEN GOALS (0)
.venv\Scripts\fk.exe verify                       # verify OK
.venv\Scripts\fk.exe why rib-1-solid              # 谱系：decompose [e4a] -> :at 接地 [e4c] -> beam-fe [e32]
.venv\Scripts\fk.exe log                          # e5a 工艺计划与工序边的 inputs 含 fab-mill（G2 绑定）
.venv\Scripts\fk.exe ledger dc-bus                # 3820/4000 W
start preview\index.html                          # 真实分解可视化（wingbox/gantry/打印机/派生样机）
```
