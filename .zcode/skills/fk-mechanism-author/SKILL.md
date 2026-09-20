---
name: fk-mechanism-author
description: "手写分支→抽象→入库"机制条目创作流水线
---

## 何时用
同一个 .fcad 分支写了第二遍 → 抽象成机制条目（mechanisms/*.json + 包内模块）。

## 条目结构
- mechanisms/<名>.json：id/version/params（range + default-expr，常量默认值
  是裸数字不是表达式！）/module（fluxkernel.mechanisms.<名>）/policies/
  termination（print 列表 + reserve）
- fluxkernel/mechanisms/<名>.py：layout(p)→帧表、profile(p,part)→件几何、
  mass_kg、generate→flow_down、kinds_of、assemble→compose 配方

## 几何原语可靠域（OCCT 实测）
- 棱柱挤出（任意多边形）✓；≥12 点 ruled loft = 无效体（布尔静默作废）✗
- 薄壁筒：外棱柱 − 内缩芯（cut 算子），不用 MakeThickSolidByJoin（放置
  后的 loft 上不挖空）
- 薄壁筒口倒角/圆角会撞 ChFi3d "only 2 faces"——外棱处理在实体上做再挖芯
- 多边形点序：命名用数字后缀（存储按字典序规范化，p10<p2 会打乱环序）
- 干涉门要求件件零交叠：内壁间隙按法向内缩欠偏移留裕量（CLEAR≈壁厚）

## 验收清单
- 冷库 instantiate 全绿（decompose→逐件→print→assemble 干涉=0）
- mass_kg 估计覆盖真实几何（预算 MARGIN 1.3）
- frames 全部由参数计算，无手算坐标
- 机制条目政策（policies 列表）在拒绝信息里给出修复提示
