# FluxKernel

**面向 AI Agent 的设计与制造证据内核。**

[English](README.md) · [交互演示](https://www.datafluxdynamics.ltd/technology/fluxkernel/) · [快速开始](docs/QUICKSTART.md) · [贡献指南](CONTRIBUTING.md)

把产品图片与需求推进为具名零件、独立 CAD、制造依赖和可复检的证据；允许修改设计，并保留父版本与未变几何。当前仓库保持私有，克隆需要访问权限。

![FluxKernel Studio](docs/media/studio.png)

当前已有：三类参考设计、真实图片模型调用、STEP/STL 导出、一轮加工设备展开、实际计划的 Lean 4 检查、交付包独立复检。单张图片不能恢复全部隐藏结构，图上的条件化闭合也不等于实物制造、采购或整机性能已经通过。

## 第一次使用

Python 3.12 及以上，在仓库目录创建并激活虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell 使用 .venv\Scripts\Activate.ps1
python -m pip install -e .
fk doctor
```

零依赖内核体验：

```bash
mkdir my-first-design
cd my-first-design
fk example
fk init
fk run hello.fcad
fk show housing-v2 --json
fk verify
```

`hello.fcad` 记录两个不同尺寸版本及其内容身份，不需要 GPU、模型密钥、OCP 或 Lean。`fk verify` 复核存储和记录的义务，不会替代仿真。

## 无密钥生成 CAD 与制造计划

回到仓库根目录，在同一环境运行：

```bash
python -m pip install -e '.[demo]'
fk doctor --profile studio
fk demo --reference phone --output ./runs --json
fk-studio
```

打开 http://127.0.0.1:8740。无模型配置时，在界面勾选“参考架构回放”。要让网页读取命令行生成的记录，启动前将 `FK_DEMO_DATA` 指向相同的输出目录。

参考模式不调用模型，不能称为图片识别。安装固定 Lean 工具链后可得到实际证明；未安装时照常生成几何，但证明状态保持 open。自动化任务可使用 `--require-proof`，没有证明就返回非零退出码。

Python 接口：

```python
from fluxkernel.studio import generate_reference
run = generate_reference("phone", output_dir="./runs")
print(run.to_dict())
```

真实图片生成、GLM 配置、Lean 安装和交付包复检见[快速开始](docs/QUICKSTART.md)。密钥只放在私有配置或环境变量中。当前尚未发布到 PyPI，请从源码或构建出的 wheel 安装。

## 带冻结约束的局部修订

新增 `fk task`、`fk inspect`、`fk revise --preview` 和版本化 Python 接口。Agent 可以修改具名零件的尺寸、位置、旋转或壁厚；不能通过修订请求改掉验收条件、零件身份和制造路线，也不能直接缩放采购件。

```bash
fk task enclosure --output ./runs --require-proof --json
fk inspect ./runs/<id> --json
fk schema revision
fk revise ./runs/<id> --patch change.json --preview --json
fk revise ./runs/<id> --patch change.json --require-proof --json
fk benchmark --output ./revision-evaluation
```

外壳任务允许把壁厚从 2 mm 改为 3 mm；改成 5 mm 会因冻结条件不满足而拒绝。成功修订复用未变 CAD，重建制造计划与证明；失败请求单独留档，父版本不被覆盖。

[Agent API 指南](docs/AGENT_API.md)包含完整 Python 示例、请求格式和诊断码。三个固定任务检查外壳容纳、轴套名义配合与安装基准间距；数值检查由 Python 执行，Lean 另行证明制造计划闭合，尚未进行物理装配试验。

## 工程边界

- 核心图与存储采用 Python 合同及完整性检查；制造计划另外使用真正的 Lean 4 检查。
- 证明覆盖有限依赖、先后顺序、路线类型、设备深度和最终产品覆盖。
- 标准件为待核验采购候选；加工件为毛坯；结构与功能还需仿真、供应商资料及物理实验。
- 不限打印尺寸是显式前提，不取消材料、精度、支撑、后处理和装配限制。

详见[证明范围](PROOF_PACKAGE.md)、[架构与扩展](docs/ARCHITECTURE.md)和[路线图](ROADMAP.md)。

## 开发与测试

```bash
python -m pip install -e '.[demo,dev]'
lake build
python -m pytest -q
python -m build
python scripts/smoke_distribution.py --studio
```

分发测试会创建全新环境，安装 wheel，离开源码目录运行完整参考设计，再复检证明并验证篡改会被拒绝。

代码采用 [MIT](LICENSE)；Three.js 与样例图片保留各自许可和来源信息。

## 通过 MCP 接入 Agent

```bash
python -m pip install -e '.[demo,agent]'
fk doctor --profile agent
fk-mcp --workspace /absolute/path/to/design-runs
```

在 MCP 客户端中配置上述启动命令。十三个工具支持任务发现、CAD 生成、跨产品资产复用、父版本检查、
修改预览、局部修订和证据读取；`--read-only` 可仅开放检查与预览。
服务通过本地 stdio 通信，不调用模型。接入方式见 [MCP 文档](docs/MCP.md)。

不用 LLM 也能复现完整客户端流程：

```bash
python -m fluxkernel.agent_smoke --workspace ./agent-runs --require-proof
```

该命令实际生成 CAD、复用未变零件、拒绝违约修改并复检 Lean 证据。
它验证协议与工程流程，不代表模型已经能推断任意产品，也不代表实物制造验证。

## 图片与 CAD 的视觉反馈闭环

Studio 的真实模型生成默认开启最多 3 轮“实际 CAD 渲染 → 对照原图评审 → 局部修订”。
修改违背约束时返回原因并允许一次纠错；每轮截图、反馈、动作与候选选择全部保留。
外观未达模型评审门槛时显示“仍需改进”，与 Lean 制造计划证明分开。

```bash
# 调用真实模型，在新目录中修订已保存的设计
fk perceive ./runs/<id> --rounds 3 --output ./visual-runs --require-proof --json
```

详见 [Perception–Action Loop](docs/PERCEPTION_ACTION_LOOP.md)。评分是模型意见，
不是客观相似度、人工验收或实物性能证明。

### v0.6：GLM 独立执行的规则闭环

GLM-5.3-Flash 先判断对称性，声明配对、例外与参数化方式，再进行评审、修改和候选选择。执行器提供真实镜像、机翼语义参数、机身截面和约束校验；不注入人工设计修正。每阶段实际加载打包的 skill，失败与模型选择均留档。[流程与边界](docs/PERCEPTION_ACTION_LOOP.md)。

## 跨产品资产复用（v0.8）

通过内容寻址资产库，在汽车、卡车、飞机、人形机器人之间复用组件、参数化模块和完整加工设备配方。
匹配功能类别、接口和带单位的能力范围；变更参数会使原有能力声明失效，目标产品重新生成 CAD 与制造计划证据。

```bash
fk asset benchmark --output ./asset-evaluation --json
```

测试使用明确编写的子系统样例，不代表自动重建整车、整机或取得物理适用认证。
详见[跨产品资产接口与边界](docs/CROSS_PRODUCT_ASSETS.md)。
