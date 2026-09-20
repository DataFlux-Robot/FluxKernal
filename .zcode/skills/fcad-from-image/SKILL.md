---
name: fcad-from-image
description: 图像驱动逆向设计（照片→合同→FluxKernel 建模→对照闭环→制造链）
---

## 六站流水线
1. **视觉解析**（VLM）：结构化输出——类别、部件清单与空间关系、参照物
   估尺寸（给区间不给点值）、材料/工艺猜测
2. **外部调研**（web）：同类产品真实尺寸/标准件型号/典型结构/工艺；
   调研清单：总体尺寸、质量、接口标准、子系统划分、可采购 vs 自制
3. **合同化**：全部数据带来源层进 spec——
   ```lisp
   (assumes (img1 "overall length 380–420mm inferred from photo w/ hand"
                  :bounds ((length_mm (>= 380) (<= 420))) :tier image-inferred)
            (web1 "comparable products use 2212-class motors" :tier web-sourced))
   ```
   红线：image-inferred / web-sourced 永不作 guarantee 验证依据；由它们
   生成的几何证据自动 tier 0（surrogate 级），直到被实测/目录数据替换
4. **架构落地**：部件清单 → 模板/机制库匹配（fk lint --suggest-template）；
   命中 instantiate；未命中走 fk-mechanism-author 的手写流水线
5. **图像对照闭环**：
   ```bash
   fk render --png out/re            # 四视图，尽量对齐原图视角
   fk review <goal> --vs original.jpg  # VLM 对比渲染图与原图
   ```
   soft issues → 修 .fcad → 循环（fk iterate 可驱动，预算/停滞不可关）
6. **制造链展开**：几何接地后 manufacture/procure/dfam 自动可用——
   到网格结束的环境从这里才开始：打印/机加/采购清单 + 全链 verify
