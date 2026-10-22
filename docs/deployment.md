# 当前部署与交接

核验日期：2026-10-22（北京时间）。本文件用于现有部署交接，不包含登录凭据、服务器访问密钥或生产数据。

## 访问入口与当前版本

| 项目 | 当前值 |
| --- | --- |
| 看板入口 | https://mikeywa.site/brandingdatabse/ |
| 公开真实快照 | https://mikeywa.site/brandingdatabse/?view=public |
| 健康检查 | https://mikeywa.site/brandingdatabse/api/health |
| 当前前端/API版本 | 20261022-public-poc |
| 当前应用代码基线 | 9bd0825 |
| 正式空间 | 独立密钥保护；生产密钥通过私有渠道管理 |

`brandingdatabse`按现有指定网址保留拼写。源码仓库后续文档提交不等于新的线上发布；核对部署版本与代码改动范围后再发布。

## 架构与部署位置

浏览器加载Nginx静态资源；同域`/brandingdatabse/api/`转发到本机Python API。SQLite保存正式数据。采集器独立运行并通过任务协议上传数据，云端部署不表示平台采集器正在持续运行。

| 组成 | 位置 / 作用 |
| --- | --- |
| 前端当前链接 | `/var/www/branding-database/current` |
| 前端版本目录 | `/var/www/branding-database/releases/<release>` |
| 后端当前链接 | `/opt/branding-database/current` |
| 后端版本目录 | `/opt/branding-database/releases/<release>/server` |
| 后端服务 | `branding-database.service`，使用独立系统账号 |
| API监听 | `127.0.0.1:8836`，由Nginx转发 |
| 正式数据库 | `/var/lib/branding-database/branding.sqlite`，独立于代码版本 |
| 私有环境文件 | `/etc/branding-database.env`，管理员/采集器密钥分离 |
| Nginx路径配置 | `/etc/nginx/snippets/branding-database.conf` |
| Nginx版本备份 | `/etc/nginx/branding-backups/` |

该路径独立于站点主页发布目录，站点主页继续正常服务。当前正式数据库没有接入账号和作品；真实公开样本位于静态`public-probe.json`，没有混入正式统计。

## 代码与构建

- 前端：React 18、Vite 6、Recharts、Lucide。
- 后端：Python标准库HTTP服务、SQLite，服务端有任务调度框架。
- 采集验证：Node.js、Crawlee、Cheerio、Playwright；当前PoC调用macOS系统Chrome，跨机器运行时需配置浏览器路径。

```sh
npm ci
npm --prefix collector ci
npm test
npm run build
```

目前为33项自动测试。平台采集实测是单独的验证活动，不随单元测试自动运行。验证码后停止的账号不应通过重复运行PoC来盲目重试。

## 更新与回滚

`deploy/install-remote.sh`面向已经配置好的现有站点。它依赖现有Nginx站点及目录规则，不是任意服务器的一键安装器。

更新前需确认测试、构建及配置；发布包仅包含`dist/`、`server/`与`deploy/`。生产环境文件已存在时继续使用，不能把私有环境文件提交到Git或混入公开压缩包。

发布脚本会在数据库存在时执行SQLite在线备份，检查Nginx配置、切换API并检查健康，然后切换前端链接。版本链接与数据目录分离。新环境初始化所需环境文件应在私有运维流程中提供。

本次上线前的回退位置：

- API：`/opt/branding-database/releases/20261022-v2`
- 前端：`/var/www/branding-database/releases/20261022-v4`

如需回滚，确认路径仍存在，分别切回对应`current`链接并重启API/重载Nginx；不要把旧数据库覆盖当前业务库。上线后核对健康、访问保护、主页、资源版本和公开快照；正式空间的验收凭据通过私有渠道取得。

## 公开交付边界

已检查现有源码和提交历史，生产环境文件及本地证据不在Git中。`.local/`、数据库、依赖目录和构建产物被忽略；原始页面可能包含登录或追踪材料，只保留在私有本地目录。公开JSON仅保留经过筛选的账号信息和内容观察字段。

公开仓库的可见性不等于另行授予开源许可证；项目未在此次交接中新增许可授权。参考项目的说明和使用边界见README。
