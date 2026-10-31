## 这个改动做了什么

<!-- 一到三句。对应 issue 编号写在最后。 -->

## 为什么这样改

<!-- 说清取舍。只改必须改的，顺手优化请单独提。 -->

## 验证方式

<!-- 贴实际执行的命令与结果。"应该能过" 不算验证。 -->

```powershell
uv run python -m pytest tests -m "not integration and not h3_local"
```

- [ ] 受影响范围的测试已跑通（贴了输出）
- [ ] 涉及前端时 `npm run test -- --run` 与 `npm run build` 已通过
- [ ] 涉及真实 H3 / ComfyUI 时，在 PR 里注明是实测还是未执行

## 是否触碰设计底线

- [ ] 没有新增绕过人工审核或发布闸门的路径
- [ ] 没有把 mock / dry-run 结果当作真实证据
- [ ] 没有提交凭证、cookie、个人数据或模型权重
- [ ] 没有并发加载大模型

## 相关 issue

Closes #
