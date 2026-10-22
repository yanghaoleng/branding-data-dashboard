# 品牌自媒体传播数据工作台

线上路径：<https://mikeywa.site/brandingdatabse/>（按用户指定拼写保留）。

首期仅包含自媒体矩阵：抖音、小红书、微信视频号。达人平台数据、媒体发稿、销售归因、日新增传播趋势与AI语义分析不属于本期。

## 已实现

- React 桌面/移动端工作台：统一发布时间、平台、账号多选、内容类型筛选；平台/账号下钻并返回；账号搜索、排序与平台分组；TOP 内容与分页显示；原始指标证据、来源时间、人工议题；CSV导出。
- 定量分析：累计传播规模、平台对比、账号贡献、已知播放集中度、主题分布、观看/互动散点。定性部分是透明的标题规则和人工标注，不宣称AI情感识别或因果分析。
- Python标准库 + SQLite：稳定身份去重，按北京时间每日快照upsert，选最新有效快照汇总。缺失保留null，不适用字段独立存储；拒绝负数、非精确数字、账号串数、未来日期、曝光冒充播放。
- 正式空间访问保护，管理员与采集器使用不同密钥；账号每日任务、6/12/24小时配置、手动同步、暂停恢复、有限网络重试、租约互斥、任务失败保留有效数据。
- 后台导出 CSV / TSV / JSON 导入及本地独立浏览器可见页面采集器框架。

## 真实接入进度（2026-10-22）

**看板和云端链路已实现；完整作品级采集尚未通过验收。2026-10-22已完成三个指定账号的公开页面PoC，取得真实账号信息与小红书首屏预览，详见 docs/public-crawl-validation-2026-10-22.md。**

正式数据库初始为空。公开演示明确标记合成数据，不能用于品牌传播结论。

通过用户分享链接，已核实抖音“叫叫阅读官方账号”和两个小红书账号“叫叫阅读官方账号”“叫你摸会儿鱼”的稳定主页ID，保存在 `server/candidates.json`。公开快照独立展示，不计入品牌总量；视频号仍待验证。

通用后台采集器仍是可配置的DOM适配框架；另已实现匿名公开响应解析PoC。公开采集不要求品牌后台权限，可能需要普通浏览账号登录，必须分别验证字段与分页。`config.example.json` 中的 REPLACE 字段刻意不填猜测值。目前不能宣称开箱即用、三平台全量可采或多日稳定。公开视频一般缺少观看量，需自有账号授权后台/允许的导出补充。

## 本地开发

```sh
npm ci
npm --prefix collector ci
npm run dev
# 另开终端，用本机测试密钥启动后端；实际密钥不提交源码
BRANDING_ADMIN_TOKEN=your-admin-token-at-least-24-characters \
BRANDING_COLLECTOR_TOKEN=your-worker-token-at-least-24-characters \
BRANDING_DB="$PWD/.local/dev.sqlite" python3 server/app.py
npm test
npm run build
```

预览：<http://127.0.0.1:5178/brandingdatabse/>。

正式管理员访问说明放在 `.local/正式空间访问说明.txt`，600权限，Git忽略；服务端环境文件位于 `/etc/branding-database.env`。不要把密钥放进网址或聊天记录。浏览器只在当前会话保存管理员密钥，退出即清理。

## 导入真实数据

1. 正式空间添加账号，填写平台真实稳定ID，核实是否品牌自有。
2. 仅`verified=true`账号进入品牌汇总，其他账号可配置监控但不混入品牌统计。
3. 下载模板 `public/import-template.csv`，映射平台允许导出的真实字段。
4. 时间含时区，例 `2026-10-22T10:00:00+08:00`。缺失留空，适用性用 `na`（`|`分隔）。
5. views有值时提供viewMetric：`play_count`/`view_count`/`read_count`；不接受`impressions`。
6. 普通CSV导入不能证明列表全覆盖，因此默认标记部分数据。

JSON批次结构：

```json
{
  "accountKey": "douyin:YOUR_STABLE_ACCOUNT_ID",
  "collectedAt": "2026-10-22T10:00:00+08:00",
  "source": "official_export",
  "coverage": {"complete": false},
  "contents": [{
    "platform": "douyin", "accountId": "YOUR_STABLE_ACCOUNT_ID", "id": "CONTENT_ID",
    "title": "真实作品标题", "publishedAt": "2026-10-21T10:00:00+08:00",
    "type": "video", "url": "https://www.douyin.com/video/CONTENT_ID",
    "views": null, "likes": 10, "comments": null, "saves": null, "shares": null,
    "viewMetric": "play_count", "na": []
  }]
}
```

“完整”要求：可信列表范围、明确 `scope=all_since_join`、`expectedCount`与本批去重作品数一致、人工/平台核对依据。公开页面一律不标全量覆盖。该声明仍需要操作人实地核验，程序不能凭发现的作品数证明平台全部作品。

## 本地采集器

```sh
cd collector
npm ci
# 使用系统Google Chrome；不读取用户日常Profile
# 复制配置到项目 .local/collector.json 后编辑
BRANDING_COLLECTOR_CONFIG=/absolute/project/.local/collector.json \
BRANDING_COLLECTOR_TOKEN='从私有环境文件读取，勿打印' \
node worker.mjs --login douyin:YOUR_STABLE_ACCOUNT_ID
# 登录完成后保持本机在线运行
node worker.mjs
```

- 一账号一Profile，稳定平台ID与页面可见身份双校验，账号混淆拒绝写入。
- 必须配置身份选择器、访问受限选择器、作品卡片、ID属性、标题、发布时间及指标字段。样例以抖音创作者中心入口说明，其他平台适配需分别完成实号PoC。
- 可见页登录验证由用户本人完成；不绕验证码、不伪造签名、不调用页面外隐藏接口、不发布不评论。
- 页面只显示“1.2万”等四舍五入值时保留null，不推成12000精确值。
- 分页读取、重复页检测、最多200页/任务、有限任务租约、成功/失败回传。自动同步以本地采集器在线为前提。
- 云端只接受作品与指标，永不接受Cookie/密码。请勿在选择器中匹配或导出用户隐私字段。

## API

前缀 `/brandingdatabse/api`。

| API | 权限 | 用途 |
| --- | --- | --- |
| GET /health | 公开 | 服务健康 |
| GET /public/config | 公开 | 已公开账号检索线索 |
| GET /dataset | 管理员 | 账号、最新有效作品快照、日志 |
| POST /accounts、/accounts/update、/accounts/remove | 管理员 | 账号配置 |
| POST /sync | 管理员 | 同步入队，不能伪报完成 |
| POST /import | 管理员 | 先校验再导入 |
| POST /contents/annotate | 管理员 | 人工议题 |
| POST /worker/claim、/worker/result、/worker/fail | 采集器 | 领取与回传任务 |

## 部署与回滚

独立Nginx路径与独立服务，不修改主页源码/快照定时发布目录。

- 前端 `/var/www/branding-database/current` → 带版本release。
- API `/opt/branding-database/current`，systemd `branding-database.service`。
- 数据 `/var/lib/branding-database/branding.sqlite`，与版本分离。
- 每次版本升级前在线SQLite备份；Nginx配置检查及API健康成功后原子切换静态版本。
- 回滚：分别把两条 `current` 链接切回 `.local/release.json` 中previous路径，重启API。Nginx配置有带版本备份。不在未核实情况下覆盖业务数据库。

## 参考与许可

仅参考公开功能描述，未复制候选仓库业务代码：

- <https://github.com/orangexie05/creator-platform-data>：独立Profile、统一作品快照、多账号隔离；未确认代码复用许可。
- <https://github.com/3441293738/creatorhub>：多平台本地浏览器与账号管理；未确认代码复用许可。
- <https://github.com/hanliang97/MatrixMedia>：本机统计能力参考，GPL-2.0。
- <https://github.com/Kuhakucai/douyin-mcp>：数据新鲜度/缺失字段/账号校验参考，AGPL-3.0。

开源许可不替代平台数据访问权。跨平台贡献仅是管理合计，不能替代统一平台统计口径。

## 公开采集实测

访问 `?view=public`，查看真实公开快照。当前为单次实测，未承诺持续自动更新。官方小红书复测可读；摸鱼账号复测遇验证码后停止；抖音仅账号级信息成功。所有缺少稳定作品ID的预览均排除正式传播汇总。
