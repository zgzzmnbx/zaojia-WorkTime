# 麒麟 A 内网部署

版本：0.7.0；部署日期：2026-11-09。规则版本保持 0.1.0（simulation）。

## 使用入口与边界

| 用途 | 地址 |
| --- | --- |
| 真实台账（初始为空） | http://10.54.9.47:8791/ |
| 模拟样例（12 人、6 项目、34 申报） | http://10.54.9.47:8791/?demo=1 |
| 健康检查 | http://10.54.9.47:8791/api/health |

入口仅绑定公司有线内网 IP，并在 Caddy 与 firewalld 两层限制来源 `10.54.9.0/24`。未新增公网/FRP/Tailscale 映射。其他办公网段尚未开放。获准网段内用户免登录，共享同一真实台账；“操作人”仍为手工留痕，不是账号认证。规则仍用于模拟筛查，未启用正式规则或签字审批。

本机 `data/`、历史资料和原始字体包未上传；服务器从程序首次启动创建空白真实库及独立模拟库。前端包含现有页面自托管字体。用户浏览器只访问服务器，不向外部模型发送数据。

## 运行结构

| 项目 | 位置或参数 |
| --- | --- |
| 发布目录 | `/opt/expert-hours/releases/0.7.0-kylin-20261109-142343-lanfix` |
| 当前程序软链接 | `/opt/expert-hours/current` |
| 独立基础 Python | `/opt/expert-hours/runtime/bin/python3.12`（3.12.14） |
| 独立 Caddy | `/opt/expert-hours/caddy` |
| 后端 | `expert-hours.service`，仅监听 `127.0.0.1:18791` |
| 内网入口 | `expert-hours-proxy.service`，监听 `10.54.9.47:8791` |
| 低权限账号 | `expert-hours`，无交互 shell |
| 网关配置 | `/etc/expert-hours/Caddyfile` |
| 持久化目录 | `/var/lib/expert-hours/data`（系统 NVMe） |
| 真实库 / 模拟库 | `ledger.sqlite3` / `demo.sqlite3` |
| 首装基线与回滚 | `/var/backups/expert-hours/20261109-141904-first-install` |
| 首装发布包 SHA256 | `d4e9b2ee87bfc627484799ac98b92204a4c5c1790bc64b0df556f978f51f2401` |
| 最终发布包 SHA256 | `8b6c9535edd5815b10cf411d63ab35e9dee6e876a8685c881ca61f1072f122be` |
| 验收后数据库快照 | `/var/backups/expert-hours/20261109-141904-first-install/accepted-data` |

两项服务启用开机启动和异常退出自动重启。运行账号只能写 `/var/lib/expert-hours`，程序和配置由 root 持有。Python 从已有基础运行时复制，不引用公文 release 或其虚拟环境；Caddy 也使用独立副本，无需更改原应用配置或重启原服务。Vite 仅用于本机构建，不部署开发服务器。

## 运维

```bash
systemctl status expert-hours expert-hours-proxy --no-pager
journalctl -u expert-hours -u expert-hours-proxy -n 100 --no-pager
curl http://127.0.0.1:18791/api/health
systemctl restart expert-hours expert-hours-proxy
```

完整冷备份需暂停本工具后端，保留整个数据目录；不要直接复制正在写入的 SQLite 主文件而遗漏 WAL。示例：

```bash
backup_dir=/var/backups/expert-hours/$(date +%Y%m%d-%H%M%S)-data
install -d -m 700 "$backup_dir"
systemctl stop expert-hours
trap 'systemctl start expert-hours' EXIT
cp -a /var/lib/expert-hours/data "$backup_dir/"
systemctl start expert-hours
trap - EXIT
```

JSON 导出适合当前台账迁移，完整历史灾备使用数据库备份。本次未配置定时备份。

首次部署撤回命令如下，仅停止并禁用本工具服务、撤销本次新增防火墙规则；程序、配置、数据库、审计与备份全部保留：

```bash
bash /var/backups/expert-hours/20261109-141904-first-install/rollback.sh
```

首装脚本为 `tools/deploy-kylin.sh`，校验发布包哈希、ARM64、目标 IP 和空闲端口，并拒绝覆盖已有部署及数据。后续升级应先备份数据与当前软链接，再部署新 release，切换 `current` 后只重启本工具；不使用首装脚本覆盖重装。界面版本和规则版本由健康接口的 `app_version` / `rule_version` 分别返回，兼容旧 `version` 字段。

## 验收

本机构建、48 项后端及 32 项前端逻辑测试通过，麒麟 ARM64 Python 3.12 上的 48 项后端测试通过。

- 真实内网浏览器在1366×768显示泳道、风险联动和亮暗主题；无页面异常。测试发现并修复普通 HTTP 不提供 `crypto.randomUUID()` 导致新增失败的问题；记录ID在内网HTTP使用 `crypto.getRandomValues()` 生成UUID v4，保留安全上下文原生路径，并新增2项回归。
- 模拟库实际编辑18为12，整期累计58变52；新增1工日后为53；刷新及第二个独立浏览器上下文读取均为53。陈旧版本写入返回409，跨站写入返回403，历史初始数量仍为18，CSV带UTF-8 BOM。
- 测试后通过恢复接口将模拟库恢复为12人、6项目、34申报和原始58工日，验收历史保留。真实库始终为r0、空人员/项目/申报，未写入测试数据。
- 执行首装回滚脚本后两端口均关闭，重新启用两项服务和规则后健康检查通过；两库正文哈希、版本、历史条数保持一致，SQLite完整性均为 `ok`。已核验active/enabled，未重启整机。
- 后端仅监听127.0.0.1:18791，网关仅监听10.54.9.47:8791；非获准来源经网关返回403，运行时与永久防火墙规则均限制10.54.9.0/24。
- 公文后端/网关、EQIS及其代理、模型API网关部署前后PID和状态一致。公文首页及WebUI健康HTTP200，EQIS首页HTTP302（登录重定向）；未执行模型推理或业务内容测试。

临时证据位于项目 `Codex-Temp/lan-acceptance.js`、`kylin-final-check.txt` 和 `kylin-hours-light-1366.png` / `kylin-hours-dark-1366.png`；服务端保留 `tests-final.log`、原服务PID对照、防火墙原值和数据库快照。

真实业务资料对照、正式业务规则批准、跨办公网段、账号权限、大规模并发和整机重启后的验收不包含在本次结果中。
