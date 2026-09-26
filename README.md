# FluxKernel

## 图片驱动演示：FluxKernel Studio

新增本地网页：GLM-5.3-Flash 图片规划 → 独立 STEP/STL → 一轮参数化加工设备展开 → 制造依赖图 → **实际 Lean 4 计划检查**。支持爆炸图、零件检查、版本修订和可独立复检的交付包。

```bash
uv venv --python 3.12
uv pip install -e '.[demo,dev]'
./scripts/start_studio.sh
```

打开 <http://127.0.0.1:8740>。私有模型配置、演示步骤和能力边界见 [演示指南](docs/demo/RUN_DEMO.md)，形式化命题见 [证明包](PROOF_PACKAGE.md)。
这里证明的是在显式外部能力假设下的**有限制造计划闭合**；图片隐含结构、采购、打印工艺和实物性能仍待验证。参考架构回放始终明确标注。

---

**命令行形态的 CAD + MBSE 设计系统内核** —— "SolidWorks × MBSE × git × Lean 战术证明器" 的 CLI 实现。
面向 LLM agent 与人类工程师：模糊需求 → 逐层拆解到标准件 → 逐层回装验证，每一步都是
**可审计的生产边**（内容寻址 digest + 证书 + 资源向量，fail-closed）。

- 命令 `fk`（战术模式，人面）与 `.fcad` S-表达式 DSL（项模式，LLM 面）共享同一内核检查。
- Lean 同构：goal=spec / tactic=算子 / Mathlib=标准件目录 / sorry=参数洞 / kernel=L1 核。
- v1.2 合同原生规格：spec = 五槽位合同（Goals/Semantics/Assumptions/Contracts/Forbidden），
  四段式接口（Assume/Guarantee/Budget/Effluent），compose 按 C1–C4 有损耗组合规则核验，
  共享介质（直流母线/热场/结构）是一等 `Medium` 节点，账本可派生（`fk ledger`）。

## 布局（L0–L4 分层，依赖只许自上而下）

```
L4 fluxkernel/interface/   .fcad 解析/打印 · fk CLI · 类型化诊断码
L3 fluxkernel/semantics/   算子引擎 · 合同算术(C1–C4) · 角色/术语本体 · goals/sorry/risks
L2 fluxkernel/solvers/     插件：sketch2d · feature3d(OCP) · mission · mate · dfam ·
                           process · line · catalog · cosim
L1 fluxkernel/core/        Node/Edge/Certificate · DAG 提交纪律 · fail-closed 生命周期
L0 fluxkernel/store/       内容寻址对象库 · append-only 边日志 · 名字索引
```

**纪律**：`core/` 与 `store/` 零第三方 import（测试强制）；诊断码表只增不改；
插件不可信、必须返回证据；失败轨迹永不删除。

## 环境

- Python ≥ 3.12；几何层需 `cadquery-ocp`（OCP）。
- Windows：若 Smart App Control 拦截 OCP 的未签名 DLL（ImportError），
  关闭 SAC 或改用 WSL。本仓库 `.venv/` 为本地开发环境（不入库，可随时重建）：

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[all,dev]"   # 或  pip install -e . --no-deps  # 纯内核零依赖
```

## 快速上手

```bash
fk init                                # 建 .fk/ 对象库（类 git）
fk run examples/aircraft.fcad          # 项模式：整脚本 = 一串 DAG 提交
fk goals                               # 战术状态：未关闭 subgoal / 参数洞 / 义务
fk why <ref>                           # 谱系回溯到 Intent
fk ledger <medium>                     # 介质账本：Σbudget/Σeffluent vs capacity
fk risks                               # 未结算风险（洞+lint 不达标+未履行义务）
fk trace --out trace_out/              # MechanogenesisBench 证书包
```

## 文档

设计文档与增补（v1.0 交接方案 / v1.1 integrate+co-design+evolve / v1.2 合同原生 spec）
见 `docs/design/`。验收测试 1–20 见 `tests/run_tests.py`。

## 测试

```bash
.venv/Scripts/python -m pytest tests/ -v     # 或  python tests/run_tests.py
```
