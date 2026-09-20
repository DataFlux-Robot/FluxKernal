---
name: fcad-design
description: 用 FluxKernel 从自然语言需求设计可验证工程系统（perception-action 闭环）
---

## 工作流（闭环）
1. 需求 → (goal ...) 九槽合同；术语先 (term ...) 定义（goals 的 :terms 必须已注册）
2. 逐层 refine/instantiate：先合同后几何；机制库命中直接 (instantiate ... :mechanism <名>)
3. fk run → 读通道 A：rejected 边的 reason 是修复提示——
   - C0 拒绝 = 硬义务未过，看 detail 里的参数与建议区间
   - I3 = 输入的产出边被拒，先修上游
   - param-cycle = 按环报告断边
4. OPEN GOALS 逐目标闭合：目录命中 (exact/procure)；接地结构件
   (ground-sketch → extrude :at 帧 → fillet → print)；机制 instantiate
5. fk render --png（四视图）→ 通道 B：看图核对"像不像声称的东西"
   （fk review 需要 FK_VLM_BASE_URL/FK_VLM_MODEL 环境变量）
6. 循环至 OPEN GOALS(0) + fk verify 全绿；或连续 5 轮无进展 → 输出僵局报告停机

## 硬性规则
- 永不手写坐标字面量（(:param)/(:expr)）；字面量仅限探索期，稳定后抽象入库
- 永不绕过 C0 拒绝——拒绝是信息，DAG 留档使作弊可见
- 每个数必须能 fk why 回溯；无来源的数写进合同 bounds 并标注 surrogate
- compose 引用分解子系统时，其全部终止产物必须在装配链上（U4 守卫，
  违例拒绝并列缺失清单——照清单补 compose，不要豁免）
- 打印件必须 fillet/chamfer ≥0.5mm（print-fillet 政策；曲面 loft 体豁免）
- 冷库验收：mkdir 新目录 fk init && fk run（热库旧绑定会掩盖前向引用）

## 反馈速查表（obligation → 对策）
- subtree-assembled 缺件 → 按缺失清单补 compose 输入
- print-fillet → 印刷前加 (refine ... :transform (fillet :edges all :radius 0.6))
- rib-spacing → hint 给出肋数区间，减距或加肋
- mass-budget → 减材或到 flow-down 源重谈预算
- medium-capacity → Σbudget 超容量：省电或按真实负载扩容（数字取证据）
- wall-ok/overhang/connected/warp → dfam 硬门：加厚/改向/拆件
- budget-closed → 子件预算和 ≤ 父预算，重新分配
- role-transition-legal → 查本体表：System→Component→Part，Part 默认拆 Process
  （结构面板要显式 :roles ((slot Part) ...))

## 反模式
- 删 obligation / 放宽合同来"消除拒绝"
- 为让渲染好看而改几何脱离证据
- 把 VLM 的看图结论当作已验证事实写进 guarantee（review 永远是 soft）
- 在热库上验证脚本正确性

## 终止判据
- 成功：OPEN GOALS(0) + hard obligations 全过 + fk verify 全绿
- 僵局：连续 5 轮无进展 → 输出缺什么机制/政策/数据的报告，停机
