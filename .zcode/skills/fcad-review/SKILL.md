---
name: fcad-review
description: 四视图渲染 + VLM 评审 + soft issue 留档（感知通道）
---

## 用法
```bash
fk render --png out/scene --view all --title "设计名"   # 四视图 PNG（感知输入）
fk review <goal-ref> [--vs reference.jpg]               # VLM 对照评审
```
- FK_VLM_BASE_URL / FK_VLM_API_KEY / FK_VLM_MODEL 配置端点（OpenAI 兼容）
- review 把发现挂在 review 边上：soft obligation，永不进硬门（结构上无口子）
- fk verify 只校验 review 边 schema（soft-only），永不重跑 VLM
- --vs 进入逆向对照模式（与参考图比较，见 fcad-from-image）

## 颜色图例（渲染）
钢蓝=Part · 琥珀=Component · 砖红=Resource · 紫=System · 青=目录代表性外形
（青色件是包络代表，不是制造商模型；质量永远用目录值）

## 判读要点
- 件堆在原点 = 布局缺失（:at 帧）；缺件 = compose/U4 问题
- 目录件不显示 = 该目录条目没有声明 geometry envelope（诚实渲染）
- 样机组 = 真实子树 1:20 派生，所见即 DAG 所声明
