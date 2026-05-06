# ONVIF 分布式网段扫描

本文说明 VIDEO 模块中 **ONVIF 搜索任务、密码库、跳过名单、独立扫描进程** 的设计与使用方式。适用于自研平台无法像海康/大华 OpenAPI 那样用 appid/appkey 拉全量设备、需按网段主动发现并撞库注册摄像头的场景。

## 能力概览

- 为指定 **CIDR 网段** 创建多个 **扫描任务实例**；任务可关联不同 **密码库**（用户名/密码对列表）做撞库。
- 扫描分两步：**快速 TCP 端口探测**（默认可配 80、554，短超时）→ 对存活地址做 **WS-Discovery（UDP 3702 单播）** 与 **HTTP ONVIF 端点探测**；认证成功后 **自动注册** 或按 MAC **同步已存在设备**（IP/端口/RTSP 源等变更）。
- 若端口存活但无法识别为 ONVIF 服务，可写入 **跳过名单**；后续轮次默认跳过，除非在接口中 **放行**。
- **多机分布式**：多台机器运行独立 **扫描 Worker 进程**，共用同一数据库；通过任务上的 `assigned_worker_id` 或租约 `claim_worker_id` / `claim_lease_until` 协调抢占。

## 架构与代码位置

| 组件 | 说明 |
|------|------|
| 数据表 | `models.py`：`OnvifPasswordLibrary`、`OnvifScanTask`、`OnvifScanSkipEntry` |
| 业务逻辑 | `app/services/onvif_scan_service.py` |
| HTTP API | `app/blueprints/onvif_scan.py`，应用内前缀 `/video/onvif-scan`（在 `run.py` 注册） |
| 独立进程 | `services/onvif_scanner_service/run.py` |
| 注册与同步 | `app/services/camera_service.py`：`register_camera_by_onvif_with_credentials`、`probe_onvif_http_endpoint`、同 MAC 同步逻辑 |

## 环境变量

**主服务（Flask `run.py`）** 需配置 `DATABASE_URL` 等现有变量；无额外强制项。

**扫描 Worker（`onvif_scanner_service/run.py`）** 常用项：

| 变量 | 含义 |
|------|------|
| `DATABASE_URL` | 与主 VIDEO 服务相同的 PostgreSQL 连接串 |
| `ONVIF_SCANNER_WORKER_ID` | 本机 Worker 唯一 ID；不设置时默认 `主机名-进程号` |
| `ONVIF_SCANNER_IDLE_SEC` | 无任务可执行时的休眠秒数，默认 `10` |
| `ONVIF_SCANNER_ACTIVE_PAUSE_SEC` | 执行完一轮后的最小间隔，与任务 `scan_interval_sec` 取较大者，默认 `1.5` |

**联调 HTTP 触发单轮扫描（可选）**  

- `POST /video/onvif-scan/worker/tick`：可设环境变量 `ONVIF_SCAN_INTERNAL_KEY`，请求头带 `X-Internal-Key` 与 `X-Worker-Id`（或依赖环境变量中的 Worker ID）。

## HTTP API 一览

基路径（直连 VIDEO 服务）为 **`/video/onvif-scan`**。

### 密码库

- `GET /password-library/list`：分页列表（`pageNo`、`pageSize`）
- `GET /password-library/<id>`：详情；`with_secrets=1` 时返回凭据
- `POST /password-library`：创建（`name`、`lib_code`、`credentials` 数组等）
- `PUT /password-library/<id>`：更新
- `DELETE /password-library/<id>`：删除（若仍被任务引用会失败）

`credentials` 项格式：`{"username":"...","password":"..."}`。

### 扫描任务

- `GET /task/list`、`GET /task/<id>`：列表与详情（含 `last_stats`、游标等）
- `POST /task`：创建（`task_name`、`cidrs` 字符串数组、可选 `password_library_id`、`is_enabled`、`auto_register`、`assigned_worker_id`、各超时与 `max_hosts_per_cycle` 等）
- `PUT /task/<id>`、`DELETE /task/<id>`

### 跳过名单

- `GET /task/<task_id>/skip/list`：分页；`include_released=1` 含已放行记录
- `POST /skip/<entry_id>/release`：放行，使该 IP 在任务下可再次参与深度探测

### 全局 IP 黑名单（加速扫描）

- `GET /ip-blacklist/list`：分页列出黑名单
- `POST /ip-blacklist/batch`：批量加入，JSON 可为 `{ "ips": ["1.1.1.1"], "note": "" }` 或 `{ "raw": "文本多行或逗号分隔", "note": "" }`
- `DELETE /ip-blacklist/<id>`：移出黑名单

黑名单 IP 在扫描轮次开始即被剔除（不占端口探测线程）；亦阻止 ONVIF 注册与按 MAC 同步更新。

### 服务器候选列表（仅管理端）

- `GET /server-candidates/list`：返回当前库中设备 **去重 IP**，且 **不在黑名单** 中的记录（便于勾选加入黑名单）。已在黑名单的 IP 不会出现。

### 响应约定

与项目内其他 Blueprint 一致：JSON 含 `code`、`msg`，列表多带 `total` 与 `data`。

## 经网关访问（iot-gateway）

网关中已配置 **VIDEO 服务** 路由，例如 `Path=/admin-api/video/**` 且 `StripPrefix=1` 后，下游路径为 `/video/...`。

ONVIF 扫描 API 的对外形式为：

```text
/admin-api/video/onvif-scan/...
```

示例：`GET /admin-api/video/onvif-scan/task/list`（具体前缀以部署的网关与全局 `context-path` 为准）。

## 独立 Worker 启动示例

在已安装依赖、能连上同一数据库的环境中：

```bash
cd VIDEO
set DATABASE_URL=postgresql://user:pass@host:5432/iot_video
set ONVIF_SCANNER_WORKER_ID=scanner-node-01
python services/onvif_scanner_service/run.py
```

Linux：

```bash
export DATABASE_URL=...
export ONVIF_SCANNER_WORKER_ID=scanner-node-01
python3 services/onvif_scanner_service/run.py
```

在管理端 **启用** 对应 `OnvifScanTask` 后，各 Worker 会按租约抢占任务并执行 `run_scan_cycle`；`last_stats` 中可查看 `registered`（新注册）、`updated`（同 MAC 同步）、`auth_ok` 等字段。

## 同设备再次发现（同步）

当撞库成功且设备 **MAC 与库中一致** 时，会更新 IP、ONVIF/RTSP 相关字段与元数据，**不新建** `device.id`；若该设备在库中为主动 **RTMP 源**（`source` 以 `rtmp://` 开头），为不覆盖直播地址，**不自动改写源**，并记为内部 `duplicate_rtmp_skip` 类结果。

## 注意事项

- 大网段请通过任务的 `max_total_hosts`、`max_hosts_per_cycle` 控制单轮规模，避免线程与数据库压力过大。
- WS-Discovery 与防火墙、NAT、仅域名 XAddr 等设备行为有关，极端情况下需依赖 HTTP ONVIF 探测与密码库。
- 撞库与高频扫描可能触发设备侧安全策略，生产环境请合法合规使用并控制并发与频率。
