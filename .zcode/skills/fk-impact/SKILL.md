---
name: fk-impact
description: 参数变更传播工作流（digest 失效集 + 影子库重放）
---

## 用法
```bash
fk impact sha-pek-v1 --set wing/span=3600          # dry-run：受影响表单/边
fk impact sha-pek-v1 --set wing/span=3600 --apply  # 影子库重放 + verify
```
- 脚本本身入库（@last-script），重放注入 (params-override ...) 后全链复验
- 旧 store 不动（历史不可篡改）；失败成 rejected 边留档
- 政策全检在重放中照常执行（rib-spacing 等可能因新跨度变红——按 hint 加肋）

## 注意
- 跨度类参数变更会连锁 rib-count 表达式、takt、质量账本——看全清单再 apply
- 数字一律从 fk why / 证据复读，不手算转抄
