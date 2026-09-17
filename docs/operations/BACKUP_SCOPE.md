# 九骥 Joukir 脱敏备份

本备份包含：

- `source/`：Joukir 后端、企业前端、Skills、测试、文档与源码配置。
- `src/deploy/staffdeck-platform/`：PostgreSQL/Casdoor 部署清单、初始化脚本和部署说明。
- `docs/prd/`：跨境电商数字员工平台 PRD 与综合方案。

已排除：

- `.env`、数据库文件、Token Store、密钥/证书和运行时凭据。
- `node_modules`、Python 虚拟环境、构建产物、缓存和临时目录。

运行时端口和凭据应通过部署环境注入，不从本仓库恢复。
