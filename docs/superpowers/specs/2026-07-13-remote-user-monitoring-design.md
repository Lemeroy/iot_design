# 卒中卫士远程用户监控平台设计

## 1. 目标

在现有 ESP32-S3 直连 MQTT、FastAPI、InfluxDB 和云端大模型链路上，增加可从公网访问的用户平台。管理员创建用户，用户登录后绑定并监控自己的健康镜。浏览器和 PC 客户端均通过 VPS 访问，不要求与 S3 位于同一局域网，也不依赖 USB。

本阶段不改变医学融合公式、危险单项否决规则或隐私边界。平台是风险监控和就医提醒工具，不是诊断系统。

## 2. 已确认决策

- 使用 SQLite + FastAPI 一体化平台，不增加独立认证服务。
- 管理员创建账号，不开放用户自助注册。
- 一个用户可绑定多台设备；一台设备最多归属一个用户。
- 用户使用六位一次性绑定码绑定 S3，绑定码 10 分钟失效且只能使用一次。
- ST7789 驱动完成前，由管理员后台显示或生成绑定码；驱动完成后由镜面显示。
- 浏览器和 PC 客户端使用 HTTPS REST + WebSocket。
- WebSocket 断开后自动降级为 5 秒轮询，恢复连接后停止轮询。
- 历史趋势提供 1 小时、24 小时、7 天三个固定范围，每次最多返回 500 个聚合点。
- 未接入模态明确显示“未接入”，不得使用模拟分数代替真机数据。

## 3. 系统架构

```text
ESP32-S3
  | MQTT/MQTTS: numeric scores only
  v
EMQX -> FastAPI MQTT bridge -> InfluxDB
                |                    |
                | SQLite             | time-series query
                | users/devices      |
                v                    v
           FastAPI REST + WebSocket
                |                 |
             Web dashboard      PC client
```

FastAPI 是唯一公网业务入口。浏览器和 PC 客户端不得直接访问 EMQX、InfluxDB 或 SQLite。S3 不接受来自用户平台的复杂控制指令，继续只接收受限建议文本。

## 4. 数据模型

SQLite 使用迁移版本表管理结构升级。核心表如下：

### users

- `id`: 整数主键
- `username`: 唯一、规范化后的登录名
- `password_hash`: 强密码哈希
- `role`: `admin` 或 `user`
- `is_active`: 是否允许登录
- `created_at`、`updated_at`

### devices

- `id`: 整数主键
- `device_id`: MQTT 契约中的唯一设备 ID
- `owner_user_id`: 可空外键；一台设备只允许一个所有者
- `last_seen_at`: 最近合法 uplink 时间
- `created_at`、`updated_at`

### pairing_codes

- `id`: 整数主键
- `device_id`: 目标设备
- `code_hash`: 六位绑定码的带密钥哈希，不保存明文
- `expires_at`: 创建后 10 分钟
- `used_at`: 使用后写入，禁止复用
- `created_by`: 管理员 ID

### sessions

- `id_hash`: 会话 Token 哈希
- `user_id`: 用户外键
- `expires_at`、`revoked_at`
- `created_at`、`last_seen_at`

SQLite 不保存原始音视频、MFCC、关键点、ROI、Wi-Fi/MQTT 密码或大模型 API Key。评分和建议历史继续保存在 InfluxDB。

## 5. 身份认证与授权

- 管理员账号由部署命令首次创建，后续管理员在后台创建普通用户。
- 密码使用内存困难型强哈希；哈希参数可升级，成功登录时按需重哈希。
- 浏览器使用随机会话 Cookie，属性为 `HttpOnly`、`Secure`、`SameSite=Strict`。
- PC 客户端使用短期访问 Token；Token 只保存在操作系统凭据库，不写入 YAML 或日志。
- 登录失败统一返回相同提示，不暴露账号是否存在。
- 登录接口按 IP 和用户名限速；连续失败产生安全审计记录。
- 所有设备 REST 查询和 WebSocket 订阅都在服务端检查设备归属。
- 普通用户只能读取自己的设备；管理员可以查看所有设备、创建或停用用户、生成绑定码和解除绑定。
- 解绑仅允许管理员执行，普通用户不能转移设备归属。

## 6. 设备发现与绑定

1. S3 使用现有 MQTT uplink 上报合法数值消息。
2. MQTT bridge 以 `device_id` 在 SQLite 中幂等登记设备，并刷新 `last_seen_at`。
3. 管理员为未绑定设备生成六位绑定码。生成新码时使该设备的旧未使用码失效。
4. 用户登录后提交绑定码。
5. 服务端在单个 SQLite 事务中检查码哈希、有效期、使用状态和设备归属。
6. 成功后写入 `owner_user_id` 与 `used_at`；并发提交只能有一个成功。
7. 过期、已使用、错误或已绑定的码返回统一失败结果。

绑定码不通过 MQTT 日志或普通设备列表返回。ST7789 可用前，只有管理员页面可以查看刚生成的明文码。

## 7. API 与 WebSocket

### 认证

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

### 用户与设备

- `GET /api/devices`
- `GET /api/devices/{device_id}/latest`
- `GET /api/devices/{device_id}/history?range=1h|24h|7d`
- `POST /api/devices/pair`
- `POST /api/admin/users`
- `PATCH /api/admin/users/{user_id}`
- `POST /api/admin/devices/{device_id}/pairing-code`
- `DELETE /api/admin/devices/{device_id}/owner`

### 实时通道

- `GET /ws/devices`

WebSocket 建立时验证会话。普通用户只收到自己设备的结构化更新；管理员可订阅全部设备。每条更新包含设备 ID、最新评分、融合等级、原因、最近上报时间和建议元数据，不包含原始媒体。

客户端检测到 WebSocket 断开后，每 5 秒请求设备列表和当前详情。WebSocket 恢复后停止轮询并以服务端最新快照覆盖本地状态。

## 8. 用户界面

### 用户端

- 登录页：账号、密码、统一错误提示和医学安全声明。
- 设备总览：设备卡片显示在线状态、风险等级、融合分数和最近上报时间。
- 设备绑定：六位码输入、过期或失败提示。
- 设备详情：F/S/T/E/CSI、融合分数、风险灯、触发原因、模型建议和历史趋势。
- 未提供的 F/S/T/E 显示“未接入”；不得显示模拟值或将 CSI 当作最终融合分数。

### 管理端

- 用户创建、停用和角色查看。
- 全部设备的在线状态、归属和最近上报。
- 未绑定设备的绑定码生成与管理员解绑。
- FastAPI、MQTT、InfluxDB 和 LLM 健康摘要，不显示凭据或内部异常正文。

界面采用克制的医疗监控风格，优先保证扫描效率和风险信息层级。危险状态固定显示立即拨打 120；大模型建议不能降低或覆盖镜端风险等级。

## 9. 在线状态与历史查询

- 最近 30 秒收到合法 uplink：在线。
- 超过 30 秒未上报：离线。
- 历史查询仅允许 `1h`、`24h`、`7d`。
- InfluxDB 查询按时间范围自动聚合，最终最多返回 500 点。
- 查询结果只包含评分、等级和时间，不返回建议全文列表或用户敏感档案。
- 服务端拒绝任意 Flux、任意时间范围和未授权设备 ID。

## 10. PC 客户端

- 新增“远程监控”数据源，使用与网页相同的 REST 和 WebSocket 契约。
- 登录凭据不进入项目 YAML；短期 Token 保存到 Windows 凭据库。
- PC 客户端保留现有局域网 YAML 配置能力，该能力仍直接连接 S3 管理 API。
- 远程监控模式只读，不允许通过 VPS 修改 Wi-Fi、MQTT 凭据、融合权重、危险阈值或否决规则。
- USB-CDC 继续作为开发调试数据源，不再是独立运行的必要条件。

## 11. 故障处理

- WebSocket 中断：客户端自动切换 5 秒轮询。
- MQTT 中断：页面保留最后快照并显示设备离线，不伪造新数据。
- InfluxDB 不可用：实时快照仍可显示，历史趋势返回明确的暂不可用状态。
- LLM 不可用：展示固定安全建议，风险等级保持镜端结果。
- SQLite 锁冲突：绑定事务短时重试，仍失败则返回可重试错误。
- 用户被停用或会话撤销：REST 与 WebSocket 同时失效。

## 12. 部署

- FastAPI 继续由现有原生部署脚本管理。
- SQLite 文件位于 VPS 持久化状态目录，不进入发布包或 Git。
- 管理员初始用户名、密码和会话签名密钥只从 VPS `.env` 或交互式初始化命令读取。
- 正式公网使用 HTTPS/WSS；MQTT 从联调 1883 迁移到设备级账号、ACL 和 MQTTS 8883。
- InfluxDB 继续只监听 `127.0.0.1`。

## 13. 验收标准

1. 管理员可创建和停用用户，普通用户不能访问管理 API。
2. 两个用户绑定不同设备后，REST、WebSocket 和历史查询互相不可见。
3. 同一绑定码并发提交时只有一次成功；过期码和已使用码均失败。
4. S3 真机 uplink 后，WebSocket 页面更新目标为 2 秒内，具体结果标记待实测。
5. 断开 WebSocket 后 5 秒轮询接管；恢复后不重复轮询。
6. 1h、24h、7d 查询均不超过 500 点。
7. `sg-0001` 显示真实 CSI；F/S/T/E 未接入时显示“未接入”。
8. 未认证访问、越权设备 ID、原始媒体字段和任意 Flux 查询均被拒绝。
9. 浏览器和 PC 客户端均可从公网登录并监控用户所属设备。
10. VPS、浏览器、PC 和 S3 日志均不出现密码、Token、API Key 或原始音视频。

## 14. 非目标

- 本阶段不实现用户自行注册、短信验证码、密码找回或第三方登录。
- 不允许用户远程修改医疗融合参数或网络凭据。
- 不在网页或 PC 客户端播放或存储原始音视频。
- 不把 CSI 80、模拟数据或缺失模态包装成真实五模态结果。
- 本设计不替代 GC2145、INMP441、ST7789 真机驱动和端侧 F/S/T/E 模型工作。
