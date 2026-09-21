---
name: fcad-review
description: 四视图渲染 + VLM 评审 + soft issue 留档（感知通道）
---

## 检查项 → 验证命令
- 渲染可读（整车组、亮底、轮廓线）→ `fk render --png <p> --theme light`
- 含装备渲染（可选）→ `fk render --png <p> --with-equipment`
- VLM 评审留档 → `fk review <goal>`（review 边 soft-only）
- 逆向对照 → `fk review <goal> --vs <ref.jpg>`
- 保真计数（case-contract 的 issues-max）→ `fk goals` case 段

## 颜色图例
钢蓝=Part · 琥珀=Component · 砖红=Resource · 紫=System · 青=目录包络
