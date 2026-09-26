# FluxKernel Studio 演示指南

## 启动

本地仓库目录运行：

```bash
./scripts/start_studio.sh
```

打开 <http://127.0.0.1:8740>。默认绑定本机，接口密钥留在服务端。需要不同端口可加 `--port 8741`。

当前工作站已由用户级服务 `fluxkernel-investor-demo` 保持运行，可直接打开页面。查看或停止：

```bash
systemctl --user status fluxkernel-investor-demo
systemctl --user stop fluxkernel-investor-demo
```

停止现有服务后才能在同一端口使用启动脚本。验收结果与真实案例链接见 [ACCEPTANCE.md](ACCEPTANCE.md)。测试环境版本记录在 `requirements-tested.txt`。

首次安装需要 Python 3.12、uv 和 elan / Lean：

```bash
uv venv --python 3.12
uv pip install -e '.[demo,dev]'
lake build
```

项目用 `lean-toolchain` 固定 Lean 4.34.1。首次构建可能下载工具链。无需本地 Qwen 或 GPU。

私有配置文件为 `~/.config/fluxkernel/model.json`，或由 `FK_MODEL_CONFIG` 指向。示例：

```json
{
  "provider": "anthropic",
  "base_url": "https://api.z.ai/api/anthropic",
  "model": "glm-5.3-flash",
  "api_key": "YOUR_PRIVATE_KEY"
}
```

配置文件权限应为 `0600`，父目录 `0700`。密钥不进入前端、运行交付包或 Git。默认直连 API；确需系统代理时在私有配置中添加 `"trust_env": true`。

## 三分钟展示流程

1. 选择手机图片或上传另一张图片，保持“参考架构回放”关闭，点击生成。模型真实收到规范化后的图片、需求和有限几何 schema。
2. 解释当前生成的是可追溯的候选工程重构。单图观察、隐藏结构推断、主动设计选择分别标注。规划可需要数分钟；界面展示当前阶段，原始响应保留。
3. 拖动旋转模型，滑动到爆炸图，点击零件查看来源、材料、尺寸和制造路线，下载独立 STEP/STL。
4. 切到“加工设备 M₁”：展示根据毛坯尺寸生成的龙门加工设备概念，继续拆到打印结构与具体规格的采购候选。
5. 切到“制造依赖图”：展示 K₀ → 设备构成件 → M₁ → 工件 → 产品的先后顺序。设备确实被加工路线引用，未使用的设备不能算递归制造成果。
6. 展示“当前计划：条件化闭合已证明”。证明文件来自本次实际计划，包含具体依赖索引和收据引用。点击完整交付包，将 ZIP 解压后运行 `python verify.py`，独立复检文件、收据、计划翻译和 Lean 证明。
7. 输入一个修订要求，例如“只把外壳壁厚改为 3 mm，其余部件保持”，生成带父版本身份的新方案。`trajectory.json` 列出新增、删除、修改和未变部件；旧方案保留。

如现场网络不可用，可明确勾选“参考架构回放”。页面会标记未调用模型。历史记录可以重放真实运行，也会保留真实模型与参考回放的区别。

## 可以准确表达的结论

“系统把图片、需求、候选产品、制造设备与证据连接成可操作的设计状态。它生成独立 CAD 零件，并对本次制造计划进行真正的 Lean 4 检查。当前闭合结论建立在显式给定的打印与装配能力上。”

目前不能宣称从任意一张照片恢复全部隐藏结构，也不能宣称手机、汽车、飞机已经达到实际使用性能。打印件仅完成构造几何检查；标准件是型号或标准规格候选与布局包络；加工件导出毛坯，刀路、配合特征和工艺能力尚待验证。飞机不会因为图闭合就成为可飞行方案。

不限尺寸意味着取消成型包络约束，不能取消材料、精度、支撑、热处理、刚度、电气与装配要求。设备本身仍需采购匹配、刚度/行程/主轴能力与基准加工验证。

## 交付与数据

每次运行位于 `.demo/runs/<id>/`，包括图片、冻结需求、模型请求与响应、设计、修订轨迹、产品和设备三维网格、独立 CAD、几何检查、制造计划、收据、实际 Lean 源码、检查日志、FluxKernel 存储及校验 manifest。

照片样例来源见 `fluxkernel/demo/static/references/sources.json`。Three.js 随项目本地提供，许可证位于 `static/vendor/THREE-LICENSE.txt`，三维渲染无需 CDN。

## 验证

```bash
lake build
env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
```

负例覆盖自引用、未来依赖、深度超限、设备缺失、孤立节点与收据/输入篡改。完整证明边界见根目录 `PROOF_PACKAGE.md`。
