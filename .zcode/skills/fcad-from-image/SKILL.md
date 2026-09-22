---
name: fcad-from-image
description: 图像驱动逆向设计（照片→合同→FluxKernel 建模→对照闭环→制造链）
---

## 四站准备 + 不动点循环

### 四站准备（只走一次）
1. **视觉解析**（VLM）：结构化输出——类别、部件清单与空间关系、参照物
   估尺寸（给区间不给点值）、材料/工艺猜测
2. **外部调研**（web）：同类产品真实尺寸/标准件型号/典型结构/工艺
3. **合同化**：全部数据带来源层进 spec（:tier image-inferred / web-sourced；
   红线：这两类永不作 guarantee 验证依据）
4. **架构落地**：部件清单 → 机制库匹配；命中 instantiate；未命中走
   fk-mechanism-author 手写流水线

### 不动点循环（核心——不是"第五站"，是反复回到的圆心）
```
REPEAT:
    fk run → fk render --png → fk review --vs original.jpg
    读三样：rejected + review_issues + case_verdict
    修复 → 改 .fcad
UNTIL: OPEN GOALS(0) ∧ case requires 全过 ∧ review_issues ≤ N
       （N 来自 case-contract；预算 50 轮与停滞检测硬编码不可关）
```
僵局出口：连续 5 轮 score 不升 → 停机出僵局报告。

**硬性规则**
- 没有跑过 fk review 的设计不许声称"完成"——fk run 会替你记住（perception-missing）
- 保真问题修设计，不修照片，不修判据；豁免必须 :waive + 理由入证据

### 制造链展开
几何接地后 manufacture/procure/dfam 自动可用——打印/机加/采购清单 + 全链 verify
