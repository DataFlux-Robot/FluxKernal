# FluxKernel 实现进展报告

日期：2026-09-19 · 仓库：`E:\DATA\vscode\fluxkernel` @ HEAD `99fd826`（22 提交）
配套文档：`INTRODUCTION.md`（架构介绍，面向评审）、`REPORT.md`（初版交付报告）、`docs/design/`（设计文档系列）

## 0. 当前快照

| 指标 | 值 |
|---|---|
| 测试 | **30/30 全绿**（`pytest tests/ -q`，≈16s） |
| 规模 | 60 个 git 追踪文件，Python 7378 行；内核 L0/L1 零第三方依赖（测试强制） |
| CLI | 33 个子命令（新增 `print`）；`.fcad` DSL 新增 `(print ...)` 表单 |
| 求解插件 | 13 个（新增 dfam-print、aero-2d、prop-map、beam-fe、mass-rollup） |
| 标志案例 | SHA-PEK：**75 表单 / 184 对象（90 节点 + 86 边）/ 85 promoted + 1 故意 rejected** |
| 案例终态 | **`fk goals` = OPEN GOALS (0)**；`fk verify` 全绿；dc-bus 3700/4000W；cabin-air 平衡 |
| 闭环验证 | 假设航程 5344.7 km（L/D=14）→ **实测复算 6127.3 km**（aero-2d 实测 L/D=16.05 覆写假设） |

一句话：按"11 步 meta 展开"标准，**主链贯通且每一层有该层保真度的证据，全部环节落在双终止集上，制造递归经打印机自举在终止层闭合**。

## 1. 三个阶段

### 阶段一：初版交付（commit 至 `c961ab1`…`9cf6766`）
- M0→M3 全量：五层内核（L0 存储/L1 数据模型/L3 合同算术/L2 插件/L4 接口）+ 33 命令 CLI + `.fcad` DSL + 9 插件 + 适配器 + evolve/watch 策略层；验收测试 1–20 全绿。
- SHA-PEK 案例首跑通：41 表单，航程 5344.7 km（评审方独立复算确认），机翼结构分解与机床链（PRSI 递归）落地。
- 1:20 几何样机 + file:// 安全的自包含 canvas 渲染器。

### 阶段二：外部评审（fluxkernel_review_v01.md，Kimi）
评审在独立工作区从零复现，结论：**INTRODUCTION 声明全部属实，骨架满足；但证据密度不足**。发现 P1–P5：
- **P1** `fk goals` 闭合判定双向错误（终态成品误报 open；被 compose 消费的未实现件误报 closed）
- **P2** sorry 传染链是图可达过近似且不分活跃/已坍缩
- **P3** compose 不要求证据覆盖（"每层更详细的仿真验证"只有 fidelity-0 演示）
- **P4** "拆到标准件"的终止性靠手工
- **P5** why 双角色显示易误读、异常捕获策略未文档化等小项

### 阶段三：进化实施（进化方案 v2.0，E0–E5，8 提交）

| 里程碑 | 提交 | 核心改动 | 验收 |
|---|---|---|---|
| **E0** 语义修复 | `3fcd7aa`, `89937f1` | 闭合改为递归不动点（叶子=目录/打印/工艺分配；分解全子闭合；compose 全输入闭合+rollup 履行；realized-by 传递——分解作用域边实现其父、子边不算）；传染改数据引用传播+坍缩洞标注 `collapsed-at`；compose 增 evidence-coverage soft 义务→risks | 终态不再误报、skin/spar/bed 正确暴露（测试 21–23） |
| **E1** 双终止集 | `b66865c` | dfam-print 硬门（壁厚/悬垂/顶点焊接连通域/翘曲）；`print` 算子（manufacture 特化，promoted 即过 DfAM）；printer.json BOM；**几何接地不再单独闭合——必须分配生产路线** | 测试 24–25（不可打印拒绝；打印机一轮自封闭 OPEN(0)） |
| **E2** 仿真矩阵 | `f924548` | aero-2d/prop-map/beam-fe/mass-rollup 四插件（公式在 docstring 可手算，tier 如实）；mission `:overrides`；`_subtree_metrics` 子树证据收集 | 测试 26（公式独立复算） |
| **E3** realize 升级 | `e02801d` | 最深优先终止集循环（catalog→print→manufacture→强制预算均分分解）；Resource 强制作为 System 完整开发；耗尽目标标记+分解封顶保证终止；顺带修复旧实现 docstring 与行为不符（`--until` 从未被使用） | 测试 27（无打印机诚实失败；有打印机 OPEN(0)） |
| **E4** 案例全链 | `2003f54` | sha_pek 41→75 表单（详见 §2）；`fk why` 逐行带 DSL 边名（P5）；runner 边名绑定 | 测试 28 |
| **E5** evolve 衔接 | `75d87bf` | termination-swap 变异（print↔catalog 双路线作普通 fail-closed 边尝试，证据向量做选择压力） | 测试 29 |
| 可视化 | `330dbd2`, `99fd826` | 全几何场景 → 飞行器+加工设备双代闭环场景（§3） | 浏览器视觉验收通过 |

**内核零改动原则全程保持**：`core/`、`store/` 在整个进化中 0 行改动；print 作为 manufacture 语义特化、闭合谓词全部落在语义层（分层纪律测试持续绿）。

## 2. SHA-PEK 案例终态（11 步覆盖度）

对照评审的覆盖度表，修复后的状态：

| 步骤 | 评审时 | 现在 |
|---|---|---|
| 1 模糊需求 | ✅ | ✅ 九槽合同 |
| 2 单质点+参数态 | ✅ | ✅ 五洞→Breguet→坍缩→复检+故意失败样本 |
| 3 展开多部件+子系统仿真 | ⚠️ 半 | ✅ wing=aero-2d(L/D≥14 硬断言)、epu=prop-map、rib=beam-fe、装配=mass-rollup——**每层有证据** |
| 4 方案坍缩+再拆 | ⚠️ 半 | ✅ wing→skin/spar/rib 全部接地+打印；fuselage→舱壳(打印)+座椅(目录)；avionics 目录直闭（"可拆可不拆"演示） |
| 6 拆到零件级 | ✅ | ✅ |
| 7–9 零件→工艺→产线→机床需求 | ✅ | ✅ 保留 rib 完整制造分支（takt/OEE/dc-bus 账本 3700/4000W） |
| 10–11 机床方案→零件 | ⚠️ bed 未闭合 | ✅ **bed 接地 800×600×60 并由 reference-printer 打印（printer→bed 双代链接）**；spindle/drive 目录关闭 |
| 终止性 | ⚠️ 手工 | ✅ **OPEN GOALS (0)**，全部叶子落在 {目录} ∪ {打印} |
| 闭环验证（V 右腿） | 无 | ✅ compose 后 mission 复算：实测 L/D 16.05 替换假设 14 → 6127.3 km ≥ 1300 |

**打印机自举（E1-3 硬性要求）**：reference-printer 自身 decompose 一轮，机架由它**自己**打印（同 digest 自举边 `e53`），步进电机/控制板目录关闭——设备开发递归 ≥1 级且全闭合，o_i = t_(i+1) 在终止层成立。

期间 fail-closed 的一次真实回报：把打印机废热误挂到客舱热介质（700W > 360W 允许值），被 `fk verify` 的介质复检当场抓住并修正。

## 3. 可视化

`preview/index.html`（file:// 双击即开，拖拽旋转/滚轮缩放）：飞行器样机 1:20（①）｜3 轴铣床身 800×600×60 + 床上翼肋工件（②③）｜打印机机架 600×600×8 立面（④）——按 ④打印→②床身→铣③翼肋→装①飞行器 的双代闭环排布；目录件（主轴/驱动/步进/控制板）无几何不渲染，图例如实注明。

## 4. 质量与验证

- 测试 30 项 = 初版 1–20 + 分层纪律 + 进化回归 21–29（闭合判定/洞坍缩/证据覆盖/print 终止/打印机自举/仿真公式复算/realize 终止集/全链案例/termination-swap）。
- `fk verify`：promoted 边 hard 义务、证据存在性、MIND plant-model-current、term-stale、介质账本全库纯重算——当前全绿。
- 数字可独立复算：Breguet、阻力极曲线 L/D、桨盘推力、梁应力/挠度、体积质量、账本——公式全部写在插件 docstring。
- 谱系可审计：`fk why bed-printed` 逐行带边名（`[e42]`）回溯 18 级到 Intent。

## 5. 已知限制与下一步

诚实清单（继承 INTRODUCTION §13 并增补）：
1. 闭环 overrides 在 `.fcad` 中是字面值（DSL 无动态引用）；与子树证据的一致性由测试 28 断言。下一步：DSL 引用语法 `:ld (from sha-pek-v1/wing ld_ratio)`。
2. dfam-print 阈值从宽（壁厚 0.5mm/悬垂 60%/长宽比 12）；"不限尺寸打印"是需求层 Assume，物理成立性属证据 tier 问题。随案例积累收紧。
3. 启发式仿真器是 tier-1 估算（非 CFD/FEA）；已如实标注，禁止冒充高保真。
4. runner 捕获 `(ContractError, ValueError, RuntimeError, KeyError)`，插件 TypeError 会 crash（有意：bug 不吞成证据）。
5. realize 的自动分解是预算均分启发（人写分解仍优于它）；evolve 的 termination-swap 只比较证据向量，未接成本模型。
6. 单机单用户文件存储，无并发控制；rejected 永久保留（视为特性，无 GC）。

建议下一步优先级：① 目录库扩充（真实供应商数据+tier 标注）→ ② DfAM 阈值标定与收紧 → ③ overrides 动态引用 → ④ evolve 接入成本/takt 选择压力。

## 6. 复核命令

```bash
cd E:\DATA\vscode\fluxkernel
.venv\Scripts\python.exe -m pytest tests\ -q       # 30 passed
.venv\Scripts\fk.exe run examples\sha_pek.fcad     # rc=1（e2x 故意拒绝）
.venv\Scripts\fk.exe goals                        # OPEN GOALS (0)
.venv\Scripts\fk.exe verify                       # verify OK
.venv\Scripts\fk.exe why bed-printed              # 经 [e42] print 边回溯到 Intent
.venv\Scripts\fk.exe ledger dc-bus                # 3700/4000 W
.venv\Scripts\fk.exe sorry --all                  # 10 洞全部 collapsed-at 标注
```
