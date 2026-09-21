---
name: fcad-design
description: 用 FluxKernel 从自然语言需求设计可验证工程系统（perception-action 闭环）
---

## 工作流（闭环）
1. 需求 → (goal ...) 九槽合同；术语先 (term ...) 注册；**案例开头声明
   (case-contract ...)**（类型与 requires——这是"做完"的定义）
2. 逐层 refine/instantiate：先合同后几何；机制命中直接 instantiate；
   形状需求用 :features 协商（缺口会拒绝并列三选一）
3. fk run → 通道 A：rejected 的 reason 是修复提示；case 未满足项在
   goals 的 case 段
4. OPEN GOALS(0) = 目标闭合 ∧ case 剖面满足
5. fk render --png → 通道 B：fk review --vs（FK_VLM_* 环境变量）
6. 收敛或 fk iterate 僵局报告（score 含 case 满足度）

## 检查项 → 验证命令（必须逐条执行）
- 案例合同存在且 schema 合法 → `fk goals`（case 段为空即未声明或全过）
- ≥1 条加工链（product/prsi-full 类）→ `fk lint --rule L8`
- Part 叶子占比 ≤0.8 → `fk lint --rule L7`
- 打印件圆角政策 → `fk run` 的 print-fillet 拒绝即查
- U4 装配完整 → `fk run` 的 subtree-assembled 拒绝清单
- 终态：OPEN(0)+case(0)+verify → `fk goals && fk verify && fk report`
- 冷库验收 → 新目录 `fk init && fk run`（热库旧绑定掩盖错误）

## 设计纪律
- 目录查询必须带类别限定量（两次同型事故：v05 伺服、TK-6x4 车轮）
- margin<5% → 敏感性评估或显式记录"压线接受"
- 形状缺口三选一：升级机制 / 换机制 / 手写后抽象入库

## 反模式
- 删 obligation / 放宽合同"消除拒绝"
- 为渲染好看改几何脱离证据
- VLM 结论写进 guarantee（review 永远 soft）
- 跳过 case-contract 让案例"合法地肤浅"——现在会被 hard 门抓住
