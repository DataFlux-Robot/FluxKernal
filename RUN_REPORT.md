# FluxKernel 运行报告

日期：2026-09-21（BX-45 图像逆向 + 保真度修正后）· 仓库：`E:\DATA\vscode\fluxkernel` · 60 次提交
数字口径：全部取自当次冷库运行（`fk report` JSON 快照），单跑语义

---

## 一、系统终态

| 指标 | 值 |
|---|---|
| 测试 | **50/50 全绿**（`python tests/run_tests.py`） |
| 规模 | 103 个 git 追踪文件 · Python 9389 行 |
| 案例 | **四案例冷库全绿**（见下表） |
| CLI | 37 子命令（run/goals/verify/why/render/review/iterate/report/impact/evolve/…） |
| 求解插件 | 15 个 · 机制条目 3（wingbox 3.0 / cabin-fuselage / empennage） |
| 目录 | 10 类条目，5 类带代表性几何包络（motor/rail/screw/board/panel/wheel/axle） |
| 政策 | rib-spacing / min-wall / mass-budget / fastener-edge / **print-fillet**（硬） |
| skill | 5 件（fcad-design / fcad-review / fcad-from-image / fk-mechanism-author / fk-impact） |

### 四案例矩阵（当日冷库复跑）

| 案例 | 来历 | 表单/边 | rejected | OPEN | verify |
|---|---|---|---|---|---|
| SHA-PEK 轻型飞机 | 手写+机制混合 | 96 / 191 | 1（e2x informative） | 0 | OK |
| SR-4M 侦察无人机 | fcad-design 首测 | 40 / 120 | 1（同） | 0 | OK |
| TK-6x4 卡车 | fcad-design 第二类 | 51 / 105 | 1（同） | 0 | OK |
| **BX-45 厢式货车** | **fcad-from-image 照片逆向** | 48 / 101 | 1（同） | 0 | OK |

每案例唯一拒绝均为刻意保留的 informative 失败样本——失败要么修复、要么声明，不静默。

---

## 二、本轮（第十一阶段）：fcad-from-image 实跑 + 用户驱动的保真度修正

### 2.1 六站流水线首次端到端（`3ed91d6`）

输入一张 204×192 像素平头厢式货车照片：

1. **视觉解析**：平头驾驶室前置、厢体后接且更高、4×2——像素量测整车跨度
2. **外部调研**：同类车型（奥铃底盘 5400×1840/轴距 3000，康铃 J6 厢体 4180×2300×2200，GVW 4495 级）
3. **合同化**：全部图像/网络数字入 assumes，带 `:tier image-inferred` / `:tier web-sourced`；guarantees 只引任务
4. **架构落地**：cabin-fuselage ×2 + 打印纵梁 + running-gear 目录（新增 750 轮胎）
5. **对照闭环**：首版任务物理不达标（102km<150），按设计改进修复（导流罩意图 L/D 6.5 → 165.7km），未动指标
6. **制造链**：打印 + 目录 + 打印机自举全落地

### 2.2 用户驳回与保真度修正（`4058357` / `7e0a4a0`）

用户指出"渲染图与照片相差太大"——属实。并排对照列出全部差异后修正：

| 差异 | 修正 |
|---|---|
| 八角管截面（最大差距） | 机制新增 `section` 枚举参数（octagon/rect），垂直壁矩形截面 |
| 厢体收缩尾部 | `tail-frac 1.0` 等截面 |
| 悬浮 430mm | 车体下沉至轮上方 130mm |
| cab/box 50mm 缝 | 平接 |

### 2.3 修正过程沉淀的通用修复（内核/机制）

1. **精确多边形内缩**（逐边偏移线求交）：原平均法向法逐顶点不一致（3.5/5.6mm），壳体实际壁厚 6.2 vs 预算 3.5——**预算说谎 25%**。修正后八角/矩形壁厚均精确 3.5、对称（面积法验证）
2. **矩形壳应力棱处理**：挖芯前整体圆角（print-fillet 政策正确拒绝裸棱柱；薄壁口撞 OCCT 限制的规避时序）
3. **机制枚举参数**：`instantiate` 传 `(section rect)`；range 检查切 options 成员校验；裸字符串默认值不再误当参数引用
4. **机制 range 放宽**：height/width 至卡车级（2250/2450），tail-frac 至 1.0

### 2.4 BX-45 终态证据

- 任务航程 **165.7 km** ≥ 150（mtow 4495 / L/D 6.5 / v 25）
- 整车结构 **715.7 kg**（驾驶室 ~182 + 厢体 ~446 + 底盘 ~87）≤ 4495 GVW
- 尺寸按照片比例：驾驶室 1250×1900×2250，厢体 3600×2050×2450
- 四视图渲染存档：`preview/bx45_4views.png`（等轴测/前/俯/右）

---

## 三、perception-action loop 的运行实效（累计）

| 回合 | 通道 | 抓到的问题 | 沉淀 |
|---|---|---|---|
| SR-4M 轮 | B（渲染） | 机翼偏置机身 1m+ | `(:expr ...)` 布局表达式 + 参数解析器 |
| SR-4M 轮 | A | 铝/PLA 密度错、嵌套质量不物化 | 机制密度统一 + nested 物化 |
| TK-6x4 轮 | A | 车轮查询命中座椅（第二次同型） | 类别限定量纪律入 skill |
| TK-6x4 轮 | A+B | 车架横放、轮胎压纵梁 | 干涉门物理分离 |
| BX-45 轮 | ⑤对照 | 任务物理不达标 | 设计改进（非指标放松） |
| BX-45 轮 | 用户视觉 | 截面形状/姿态/接缝三大差异 | section 参数 + 精确内缩 |
| v05 评审 | 冷库对账 | 机床分支阵亡 + 闭合失明 | U5 规则 + sabotage 测试 |
| v06 评审 | 冷库对账 | （仅装饰性） | 橙块=打印机机架（刻意）等 4 项 |

六轮外部评审严重度单调下降：内核缺陷 → 案例回退/规则盲区 → 装饰问题。近四轮的每个发现都转为带测试的通用规则或机制能力。

---

## 四、红线执行状况

- **VLM 只进 soft**：review 边 class 硬编码，verify 只查 schema——从未违反（test_46 机械断言）
- **包络不冒充模型**：质量永远用目录值，渲染青色标识——BX-45 全程遵守
- **image/web 数字不作 guarantee 依据**：全部在 assumes + tier 标注——BX-45 的 spec 可 `fk why` 回溯 img1/web1/web2
- **预算重谈走正规变更**：cab 125/box 290/fuselage 60 均在 flow-down 源修改，非消音
- **失败必须表态**：`:informative t` 显式声明（每案例恰 1 个样本）

## 五、待办（按优先级）

1. **VLM 通道实机**：GLM-5.3-Flash 接 `FK_VLM_*` 跑 `fk review`/`fk iterate` 实机闭环（协议零改动，P7 最后一块）
2. **margin<5% 敏感性**：BX-45 165.7/150 = 10.4% 安全，但 SR-4M 541/300、TK 153/150（2%）应补敏感性评估（skill 已有纪律，未执行）
3. **渲染细节层**：门窗/风挡开口、双色涂装——包络模型的既定边界外，若需要须升级为特征算子
4. **回收 SK-PEK 旧案例的 `.zcode/skills` 位置说明**（跨 agent 分发注意路径）

---

## 六、复核命令（单跑口径；重复跑同库拒绝数累计是特性）

```bash
cd E:\DATA\vscode\fluxkernel
.venv\Scripts\python.exe tests\run_tests.py                    # 50/50
# 四案例冷库（每案例新目录）：
#   ... init && ... run examples\<case>.fcad && ... goals && ... verify && ... report
python tools\gen_preview.py                                    # SHA-PEK 三场景
# BX-45 四视图已存档 preview\bx45_4views.png
```
