# 发布验证

验证日期：2026-10-02；本地 Python 3.13。使用现有安装依赖，尚未在全新虚拟环境重新安装验证。

- `python -m pytest -q`：363 passed，12.25 秒。
- `python -m src.runner --run-id portfolio_demo --input data/issues.json --mode mock --run-mode auto`：status 为 success，输出机会卡及中英文报告。
- Markdown 相对链接检查：无缺失目标。
- 历史原型的 snapshot、icons、cards、report、图标许可证文件存在；本轮没有重新做浏览器交互验收。
- 对待发布源码、数据与文档执行常见 GitHub/OpenAI token 及私钥格式扫描：无匹配。此为模式扫描，不是安全审计认证。
- 发布版不包含真实 `.env`；生成的输出、数据库与缓存由 `.gitignore` 排除，不进入提交。

这次验证针对离线程序行为和发布完整性，未验证真实 GitHub 检索效果、跨领域质量或任何 100% 业务指标。完整本地评估记录保留在原开发目录。
