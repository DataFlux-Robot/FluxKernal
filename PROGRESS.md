# FluxKernel 开发进展报告

日期：2026-09-20（整机装配完整性收口后更新）· 仓库：`E:\DATA\vscode\fluxkernel` · 43 次提交
配套文档：`INTRODUCTION.md`（架构介绍，面向评审）· `REPORT.md`（初版交付报告）· `docs/design/`（设计文档系列）

> 定位回顾：面向 LLM 的**通用**机械系统工程内核 + CAD CLI（build123d 形态的 `.fcad` DSL + 33 子命令）。核不是几何而是**带证书的内容寻址精化图（CARG）**——几何是节点的求值投影。开发纪律：机制通用、内容（案例/目录/模板）为数据、内核 L0/L1 零第三方依赖且零改动。

## 0. 当前快照（全部数字为本日冷库复跑验证）

| 指标 | 值 |
|---|---|
| 测试 | **45/45 全绿**（`python tests/run_tests.py`，≈18s） |
| 规模 | 79 个 git 追踪文件，Python 7750 行 |
| CLI | 33 子命令；`.fcad` DSL 含 `(print ...)`、`:at`、`:machine`、`:template`、`:roles`、`:no-assembly` |
| 求解插件 | 14 个（几何 4 + 仿真 4 + 制造 4 + 任务 2）；目录 6 文件；架构模板 2 个；机制库 1 条目（wingbox） |
| 标志案例 SHA-PEK | **111 表单**（冷库 181 节点/180 边/458 名字）/ 45/45 测试 / OPEN(0) / verify 全绿 |
| 案例终态 | **OPEN GOALS (0)** · verify 全绿 · dc-bus Σbudget 3820/4000W（容量 5000、margin 0.2）· 装配干涉门 = 0 干涉 |
| 整机形态 | 翼盒（10 件）+ 舱壳（5 面板）+ U 型尾梁 + 平尾 + 垂尾 = **18 件真实装配**；派生样机融合 18 件、10.2 g、质心 [75.5, 39.6, 7.0] |
| 任务链 | 假设航程 5344.7 km（L/D=14）→ **闭环复算 6127.3 km**（aero-2d 实测 L/D=16.05 覆写假设；数字取自运行证据） |
| 双代闭环 | printer→（机床结构件）+ catalog→（运动件）= 机床；机床 `:machine`→rib-1 工序——两条设备链都在 DAG 边的 inputs 里 |

## 1. 开发阶段总览

### 阶段一：初版交付（`Initial commit`…`9cf6766`）
五层内核（L0 内容寻址存储 / L1 数据模型与提交纪律 / L3 合同算术 C1–C4 + lint L1–L6 / L2 插件 / L4 CLI+DSL）+ 适配器 + evolve/watch 策略层；验收测试 1–20 全绿；SHA-PEK 案例首跑通（41 表单）；1:20 几何样机 + file:// 安全的自包含渲染器。

### 阶段二：首轮评审与进化 E0–E5（评审 v01 → 进化方案 v2.0，8 提交）
评审在独立工作区复现全部声明，指出 P1–P5（闭合判定双向错误、传染过粗、证据密度不足、终止靠手工、显示小项）。进化落地：**递归闭合不动点**（被 compose 消费≠已实现；终态成品不误报）、**数据引用传染 + 坍缩洞标注**、evidence-coverage soft 义务、**双终止集**（dfam-print 硬门 + print 算子 + 打印机自举一轮）、**每层仿真矩阵**（aero-2d/prop-map/beam-fe/mass-rollup，公式可手算）、realize 终止集感知升级、evolve termination-swap。案例 41→75 表单，首达 OPEN(0)。

### 阶段三：二轮复核（评审 v02）
独立复跑确认 E0–E5 全部兑现（"审阅意见全部被理解并正确实现，而非表面应付"），指出三个新缺口：**G1** 生产算子身份在 args 不在 inputs（I3 精确链接不覆盖打印机本身）；**G2** 铣床被开发却从未被使用（mill→rib 只在注释里）；**G3** 闭环航程报告值 6143 vs 证据值 6127.3（手算转抄）。

### 阶段四：三轮诊断与骨架层进化（评审 v03 → G1–G3 + E6，6 提交）
用户观察"机翼没拆分、机床不像机床"被证实为更深层问题——**实现跳过了 Skeleton（几何架构）层**：e4d 组合的是未接地合同节点而非 skin-solid/spar-solid（真 bug）；机床分解只有 kind 名字。修复全部落地（§2）。

### 阶段五：总路线图实施（master roadmap v1.0，P0→P5，7 提交）

按《总实施路线图》完成 P 参数系统 / R 政策库 / M 机制库 / G 几何梯的全部六个里程碑：

| 里程碑 | 交付 |
|---|---|
| **M1 参数系统**（P0） | `core/params.py`：非图灵完备表达式 + 单一来源路径参数 + 环检测（带修复提示）；`:param`/`:expr` 全通道解析；`(params ...)` 命名参数集；param-bindings 证据随边入库 |
| **G1 实体草图**（P1） | line/arc/circle/spline 图元 + 孔环；约束 5→12；`fully-constrained` soft；带孔圆角件体积手算核对 |
| **G3 变更传播**（P1） | 脚本入库；`fk impact --set <set>/<key>=v [--apply]` 影子库重放 + 复验（历史不可篡改）；`fk why` 显示每跳参数绑定 |
| **M2 政策库**（P2） | code-as-policy：`policies/*.json+.py` 内容寻址、digest 入 DAG、C0 零改动直通；首批 rib-spacing（含修复提示）/min-wall/mass-budget/fastener-edge-distance |
| **G2 特征算子**（P2） | fillet/chamfer（三锚边选择）/loft/shell/pattern-linear（表达式驱动 count）/mirror，全部 construction 按值可重放 |
| **G4 mate-solve**（P3） | 命名特征（bbox 平面锚按值入 construction）；解析平移求解 + 有效位置链；`fully-mated` 报告自由轴 |
| **M3 机制库**（P4） | `mechanisms/wingbox`：frames 从字面量变**函数**（layout(span,chord,height,rib-count)），rib-count 由表达式推导（ceil(span/500)）+ 政策强制；`(instantiate ...)` 一表单展开为普通 DAG；案例机翼 80 行 → 1 行 |
| **M4 回卷清零**（P5) | compose 自动几何回卷：全接地输入自动 assemble 干涉门 + **装配 ground 物化到节点**；部分/零/豁免三态显式标记；`fk why` 每跳证据标记——治复核 G4/G5 |

P6（G5 b123d-script / G6 solve）按路线图为可选增强，本轮未实施。

### 阶段六：整机装配完整性（用户连续三轮观察驱动，5 提交）

用户观察"**机翼为什么没在飞机上**"→ 诊断 → 修复 → 通用守卫 → "**依然没有完整整机**" → 机身真实结构。这轮的真正主题是：**节点级正确 ≠ 装配级正确**，而 fail-closed 体系此前对后者全盲。

| 提交 | 内容 |
|---|---|
| `70c589f` 飞机级布局 | 诊断出三个机身件只连着自己的打印边、从未 compose 回整机（样机如实渲染出"光杆机翼"）。以翼盒为锚补 `:at` 帧布局；compose 接回三件；顺带暴露并修复**前向引用**（热库旧绑定掩盖、冷库即炸）与 OCCT `gp_Trsf.SetTranslation` 重置矩阵陷阱 |
| `7de7113` U4 守卫 | 上述根因的**通用化**：`subtree-assembled` 硬义务——compose 引用分解子系统，其子树全部终止产物（打印件+目录件）必须在装配输入链上（直接或经中间装配 compose），违例拒绝并列缺失件清单；`:no-assembly <理由>` 显式豁免。上线即抓到案例三处同型残留：座椅目录件未入 e5、三轴模组终止集未装配、打印机自身终止集未装配——全部修复（轴/打印机各补装配 compose） |
| `dd5014c` 机身真实结构 | 机身从"三张纸"变为真结构：舱壳五面板（地板/双侧壁/前后隔框，围合 800×1397×400）+ 打印 U 型尾梁（160×160 壁 3 长 700）+ 尾翼移到梁端。本体发现：**Part 的默认子角色是 Process**（零件默认拆工艺步），结构面板须 decompose `:roles` 显式声明 |

## 2. 当前通用能力清单（全部零 trick）

| 能力 | 机制 | 语义保证 |
|---|---|---|
| **Placement / Location** | `:at [dx,dy,dz]` 或 `((x y z) (ax ay az deg))` 施加于 extrude/revolve | 放置入 `construction` 并在 `rebuild_brep` 重放——谱系稳定；revolve 轴同步参数化 |
| **帧系统（Skeleton）** | 任意节点可携 `spec.frames`；`:at (:frame 名字)` 解析 | 布局单源：骨架帧经 decompose 的 `specs` 下发，子件相对父骨架接地 |
| **算子身份链接（G1/G2）** | print 边 `inputs=[工件,打印机]`；`manufacture :machine` 槽并入工艺边 inputs | I1/I2/I3 精确链接覆盖**生产算子实例**——打印机/机床的产出边 rejected 时，使用它的边自动拒绝 |
| **input-realized 硬门（U2）** | compose 对 Part 角色输入的硬义务 | 组合未实现零件 → C0 拒绝（曾抓到 e4d 真 bug）；Component 仍可合同级组合 |
| **subtree-assembled 硬门（U4）** | compose 引用分解子系统时，子树全部终止产物必须在装配输入链上（覆盖经中间装配 compose 传递，对终产边对称：列实体即覆盖其打印件，反之亦然） | 节点级闭合（每叶到终止集）看不到"悬空接地件"；U4 补上装配级覆盖；违例拒绝并列缺失件清单；`:no-assembly <理由>` 豁免（备件/工装）记入证据 |
| **架构模板（E6-4）** | `decompose :template <名>` 加载 `catalog/archetypes/*.json` | 模板=纯数据（子件/角色/合同/骨架帧/介质引用）；显式 args 逐键覆盖 |
| **派生缩放（E6-3）** | `scale-instance :ratio` 从输入祖先子树收集接地几何缩放融合 | construction 按值记录可重放；边 inputs 精确链接每个源——派生物可证明由这些件组成 |
| **decompose 角色/类型槽** | `:roles ((slot 角色))` / `:kinds`；默认子角色按本体推导（System→Component、Component→Part、**Part→Process**） | 零件默认拆成工艺步、结构面板须显式 Part——本体语义显式可查 |

案例中已验证：wingbox 机制（双蒙皮+双梁+6 肋按骨架帧就位，真实干涉门零干涉）；**舱壳+尾梁机身**（5 面板围合座舱、U 型梁承载尾翼，1:1 十对件零干涉）；gantry-mill 模板（床身/立柱/横梁/Z头打印 + 导轨/丝杠/伺服/主轴/CNC 目录，三轴各含装配 compose）；打印机自举装配（机架打印件+目录电机/板）；样机由真实子树 1:20 派生（18 件融合）。

## 3. SHA-PEK 案例与 11 步覆盖度

| 步骤 | 状态 | 证据 |
|---|---|---|
| 1 模糊需求 | ✅ | 九槽合同（可否证 goals/术语/禁项/免责） |
| 2 单质点+参数态 | ✅ | 五洞→Breguet→坍缩→复检 + 故意失败样本永久保留 |
| 3 子系统仿真 | ✅ | wing=aero-2d（L/D≥14 硬断言）、epu=prop-map、rib=beam-fe、装配=mass-rollup（18 件样机 10.2 g） |
| 4 坍缩+再拆 | ✅ | wingbox 机制 instantiate；**fuselage→舱壳（→地板/侧壁/隔框）+尾梁+座椅+尾翼**；avionics 目录直闭 |
| 6–9 零件→工艺→产线→设备需求 | ✅ | rib-1 `:machine fab-mill` 加工；line takt/OEE 上卷 |
| 10–11 设备方案→零件 | ✅ | gantry 模板开发机床（三轴模组各含装配）；printer→结构件双代链接；全部叶子落双终止集 |
| 终止性 | ✅ | OPEN GOALS (0)；闭合=递归谓词 + U4 装配覆盖 |
| 闭环验证 | ✅ | e63 mission 复算用实测 L/D → 6127.3 km ≥ 1300 |

## 4. 质量与验证

- **45 项测试** = 验收 1–20 + 分层纪律（core/store 零第三方 import）+ 回归 21–45：闭合判定/洞坍缩/证据覆盖/print 终止/打印机自举/仿真公式独立复算/realize 终止集/全链案例/termination-swap/算子身份 I3/Placement 重放/模板加载与介质解析/scale-instance 派生/参数系统/实体草图/impact 影子重放/政策库/特征算子/mate-solve/instantiate/compose 回卷/**U4 三态（拒+列缺失件/完整链过/豁免过）**。
- `fk verify` 全库纯重算全绿（义务/证据/术语/介质账本）；**案例验收以冷库为准**（`fk init` 新库跑，见 §6）。
- fail-closed 的真实回报记录：① 打印机废热误挂客舱介质被账本复检拦截；② input-realized 抓到 e4d 组合未实现件；③ dfam 连通门抓到装配多壳（后修正为"刻意装配=多壳作业"语义）；④ 无证据 range rollup 被闭合规则暴露后删除；⑤ **U4 上线即抓到三处悬空终止集**（座椅/三轴/打印机——被点名后才看见）；⑥ 冷库复跑暴露 compose 前向引用（热库旧绑定掩盖）。
- 数字纪律（G3）：报告数字一律取运行证据（6127.3/3820W/10.2g 均来自 store evidence 复读）。

## 5. 已知限制与下一步

1. U4 只覆盖"引用了子系统但漏装零件"；**整棵子系统被完全遗漏**（连合同节点都不进 compose）仍无提示——需要"顶层 compose 覆盖分解树第一层"规则（涉及 design→Intent 链接语义）。
2. 开发热库的过期名字绑定可能掩盖错误（两次事故均靠冷库复跑定位）→ 候选：`fk run` 前置名字新鲜度检查，或干脆默认一次性库。
3. 闭环 overrides 在 DSL 中是字面值（无动态引用）；一致性由测试断言。
4. dfam-print 阈值从宽（壁厚 0.5/悬垂 60%/长宽比 12）；"不限尺寸打印"是需求层 Assume。
5. 启发式仿真器是 tier-1 估算（公式在 docstring，禁止冒充高保真）。
6. 机身面板布局仍是手写 `:at` 帧（"手写→抽象→入库"的第一步）→ 下一步抽象为 `cabin-fuselage` 机制条目（路线图 §7 终态形态）。
7. 单机文件存储；rejected 永久保留（特性，无 GC）。

优先级建议：cabin-fuselage 机制条目化 → 目录库真实数据扩充 → DfAM 标定 → overrides 动态引用 → 更多架构模板。

## 6. 复核命令

```bash
cd E:\DATA\vscode\fluxkernel
.venv\Scripts\python.exe tests\run_tests.py      # 45/45 passed
# 冷库验收（防热库旧绑定）：
mkdir %TMP%\fkcheck && cd %TMP%\fkcheck && E:\DATA\vscode\fluxkernel\.venv\Scripts\python.exe -m fluxkernel.interface.cli init
E:\DATA\vscode\fluxkernel\.venv\Scripts\python.exe -m fluxkernel.interface.cli run E:\DATA\vscode\fluxkernel\examples\sha_pek.fcad
#   forms: 111  rejected: 1（e2x 故意样本）
... goals    # OPEN GOALS (0)
... verify   # verify OK（介质 3820/4000W 达标）
... why mockup-solid   # 18 件派生谱系
python tools\gen_preview.py                     # 29 shapes / 800 tris
start preview\index.html                        # ①整机1:1 ②gantry铣床 ③打印机 ④派生样机
```
