# HIS 系统详细技术文档

## 1. 文档说明

本文档基于 `his` 目录下的现有代码生成，主要描述 HIS 主系统的技术实现。仓库中还存在 `hospital_back`、`hospital_front` 等机器人/监控相关模块，本文档仅在必要处说明其存在，不作为 HIS 主链路展开。

适用读者：

- 项目答辩、验收和交付人员
- 后续维护 HIS 前后端代码的开发人员
- 需要理解处方流转、药品追溯码和审计链实现的技术人员

## 2. 系统概述

HIS 系统是一套面向医院处方、药品、患者和扫码核验场景的 Web 系统。系统围绕“医生开方、药师审方、药品追溯码绑定、扫码识别/出库/确认、可信审计”构建。

核心能力包括：

- 用户登录与角色权限控制
- 患者档案管理
- 药品基础信息管理
- 药品货位坐标管理
- 药品追溯码生成、录入、查询和扫码状态流转
- 医生处方开具
- 药师处方审核和发药确认
- 移动端扫码核验页面
- 关键业务事件审计链记录与校验
- 服务完整性校验与截止日期保护

## 3. 技术栈

### 3.1 前端技术栈

前端位于 `his/client`。

| 类型 | 技术 | 说明 |
| --- | --- | --- |
| UI 框架 | React 18 | 构建页面和组件 |
| 构建工具 | Vite 5 | 本地开发、代理、打包 |
| 类型系统 | TypeScript | 前端类型定义和接口约束 |
| 路由 | react-router-dom 6 | 页面路由和权限跳转 |
| HTTP 客户端 | axios | API 请求封装、token 注入、错误拦截 |
| 动画 | framer-motion | 页面和交互动画 |
| 图表 | echarts | 仪表盘/统计类模块预留或使用 |
| 扫码 | html5-qrcode | 移动端摄像头扫码 |
| 样式 | CSS | 全局样式文件 `src/styles/global.css` |

### 3.2 后端技术栈

后端位于 `his/server`。

| 类型 | 技术 | 说明 |
| --- | --- | --- |
| 运行时 | Node.js | 后端运行环境 |
| Web 框架 | Express 4 | REST API 服务 |
| 类型系统 | TypeScript | 后端类型约束 |
| 开发运行 | tsx watch | 本地热更新运行 TypeScript |
| 数据库驱动 | mysql2/promise | Promise 风格 MySQL 连接池 |
| 认证 | jsonwebtoken | JWT 登录态 |
| 密码校验 | bcryptjs | 用户密码哈希比对 |
| 跨域 | cors | 后端 CORS 支持 |
| 加密/哈希 | Node crypto | 文件完整性、审计链哈希 |

### 3.3 数据库

数据库为 MySQL 8，默认连接配置位于 `his/server/src/db.ts`：

- host：`MYSQL_HOST`，默认 `192.168.51.133`
- port：`MYSQL_PORT`，默认 `3306`
- user：`MYSQL_USER`，默认 `ros`
- password：`MYSQL_PASS`，默认 `123456`
- database：`MYSQL_DB`，默认 `test`
- charset：`utf8mb4`
- connectionLimit：`10`

基础建表和示例数据可参考 `his/server/db/test.sql`，后续迁移脚本位于 `his/server/db/migration_*.sql`。

## 4. 项目结构

```text
his/
  client/                  前端 React/Vite 项目
    src/
      App.tsx              前端路由与权限壳
      services/api.ts      API 封装
      hooks/useAuth.ts     登录态读取和维护
      pages/               页面
      components/          通用组件
      types/index.ts       前端业务类型
      styles/global.css    全局样式
    vite.config.ts         Vite 配置和 /api 代理

  server/                  后端 Express/TypeScript 项目
    src/
      index.ts             服务入口和路由挂载
      db.ts                MySQL 连接池和数据库访问保护
      config.ts            系统截止日期配置
      guard.ts             截止日期多层保护
      verify.ts            文件完整性校验
      middleware/auth.ts   JWT 认证和角色鉴权
      routes/              REST API 路由
      services/auditChain.ts 可信审计链服务
    db/                    SQL 初始化和迁移脚本

  scripts/
    generate-checksums.js  生成服务完整性校验清单

  start-his.sh             一键启动前后端脚本
```

## 5. 系统架构

系统采用前后端分离架构：

```text
浏览器 / 移动端扫码页
        |
        | HTTPS, Vite dev server, /api proxy
        v
React 前端 his/client
        |
        | REST JSON API, Bearer JWT
        v
Express 后端 his/server
        |
        | mysql2 connection pool
        v
MySQL 数据库 test
```

前端开发服务默认监听 `3002`，后端默认监听 `3001`。Vite 将 `/api` 代理到后端，因此前端代码中 axios 的 `baseURL` 设置为 `/api`。

一键启动脚本 `his/start-his.sh` 会完成：

1. 检查并生成本地 HTTPS 证书。
2. 检查前后端 `node_modules`，缺失时执行 `npm ci`。
3. 自动选择可用后端端口，优先 `3001`。
4. 自动选择可用前端端口，优先 `3002`。
5. 将 `VITE_API_TARGET` 指向后端地址。
6. 同时启动后端 `npm run dev` 和前端 `npm run dev`。

## 6. 用户与权限模型

系统用户表为 `users`，角色分为：

- `doctor`：医生，可创建处方，默认只能查看自己创建的处方。
- `pharmacist`：药师，可审核处方和执行发药相关操作。
- `admin`：管理员，可访问医生和药师相关功能。

认证流程：

1. 用户在登录页提交用户名和密码。
2. 后端 `POST /api/auth/login` 根据用户名查询 `users`。
3. 使用 `bcrypt.compareSync` 校验密码。
4. 校验通过后生成 JWT，载荷包含 `id`、`username`、`real_name`、`role`。
5. 前端将 `token` 和 `user` 保存到 `localStorage`。
6. axios 请求拦截器自动添加 `Authorization: Bearer <token>`。
7. 后端 `authMiddleware` 校验 token，并将用户信息写入 `req.user`。
8. 需要角色限制的接口通过 `requireRole(...)` 控制访问。

前端路由也有角色控制，例如：

- `/prescriptions/new`：仅 `doctor`、`admin`
- `/review`：仅 `pharmacist`、`admin`
- `/scan`：登录后可访问，不使用普通布局，适配移动端扫码

## 7. 主要数据模型

### 7.1 users

用户表，保存登录账号、密码哈希、真实姓名和角色。

关键字段：

- `username`
- `password`
- `real_name`
- `role`: `doctor`、`pharmacist`、`admin`

### 7.2 patients

患者表，保存患者基本信息。

关键字段：

- `name`
- `gender`
- `age`
- `phone`
- `id_card`
- `address`

患者详情接口会关联查询该患者的历史处方。

### 7.3 medicines

药品基础信息表。

关键字段：

- `name`
- `generic_name`
- `specification`
- `drug_form`
- `manufacturer`
- `unit`
- `price`
- `stock`
- `category`
- `is_narcotic`
- `image_url`

药品列表会左连接 `medicine_trace_prefixes` 返回追溯码前缀。

### 7.4 medicine_trace_prefixes

药品追溯码前缀表。每种药品可配置一个 7 位数字前缀。

用途：

- 生成药品追溯码时保留药品前缀特征。
- 扫到系统未登记的追溯码时，根据前 7 位前缀判断药品。
- 如前缀不存在，系统可创建“其他”药品并绑定该前缀。

### 7.5 medicine_trace_codes

药品追溯码表，是药品流转核验的核心表。

关键字段：

- `medicine_id`：关联药品
- `prescription_id`：关联处方
- `trace_code`：追溯码，唯一
- `status`：扫码状态
- `scan1_time`、`scan2_time`、`scan3_time`
- `scan1_user_id`、`scan2_user_id`、`scan3_user_id`

追溯码状态机：

```text
pending
  -> scanned_identify
  -> scanned_outbound
  -> scanned_confirm
```

含义：

- `pending`：待扫码/待识别
- `scanned_identify`：已识别药品
- `scanned_outbound`：已出库
- `scanned_confirm`：最终确认完成

### 7.6 prescriptions

处方主表。

关键字段：

- `patient_id`
- `doctor_id`
- `prescription_code`
- `prescription_type`
- `payment_type`
- `medical_record_no`
- `department`
- `bed_no`
- `diagnosis`
- `status`
- `pharmacist_review_id`
- `pharmacist_dispense_id`
- `total_amount`
- `reviewed_at`
- `dispensed_at`

处方状态：

```text
pending -> approved -> dispensed
pending -> rejected
```

### 7.7 prescription_items

处方明细表，一张处方最多允许 5 种药品。

关键字段：

- `prescription_id`
- `medicine_id`
- `drug_form`
- `dosage`
- `usage_method`
- `frequency`
- `days`
- `quantity`
- `note`

### 7.8 prescription_trace_codes

处方与追溯码的关联表，由后端在创建处方时确保存在。

用途：

- 将处方明细、药品和追溯码建立强绑定。
- 限制同一追溯码只能关联一张处方。
- 处方详情查询时通过该表返回每个明细对应的追溯码和扫码状态。

### 7.9 medicine_locations

药品货位表，记录药品在药柜或货架中的坐标。

关键字段：

- `medicine_id`
- `medicine_name`
- `x`
- `y`
- `z`

接口返回时会补充药品规格、厂家和追溯码前缀信息。

### 7.10 audit_chain_records

可信审计链记录表，由 `services/auditChain.ts` 自动创建。

关键字段：

- `event_type`
- `entity_type`
- `entity_id`
- `trace_code_hash`
- `prescription_hash`
- `operator_hash`
- `flow_status`
- `event_time`
- `payload_hash`
- `previous_hash`
- `current_hash`

该表不直接存储追溯码、处方号、操作者 ID 的明文，而是存储加盐 SHA-256 哈希。

## 8. 核心业务流程

### 8.1 登录流程

```text
用户输入账号密码
  -> POST /api/auth/login
  -> 查询 users
  -> bcrypt 校验密码
  -> 生成 JWT
  -> 前端保存 token/user
  -> 后续请求自动携带 Bearer token
```

关键实现：

- 后端：`routes/auth.ts`
- 鉴权中间件：`middleware/auth.ts`
- 前端登录态：`hooks/useAuth.ts`
- axios 拦截器：`services/api.ts`

### 8.2 患者管理流程

患者管理提供列表、搜索、新增、编辑、删除和详情查询。

列表查询：

```text
GET /api/patients?page=1&pageSize=10&keyword=张
  -> 按 name 或 phone 模糊搜索
  -> 返回 total/page/pageSize/list
```

详情查询：

```text
GET /api/patients/:id
  -> 查询 patients
  -> 查询 prescriptions 历史处方
  -> 返回患者信息 + prescriptions
```

删除患者时，后端使用事务先删除相关处方明细，再删除处方，最后删除患者。

### 8.3 药品管理流程

药品管理支持：

- 药品分页列表和搜索
- 新增药品
- 编辑药品
- 删除药品
- 设置/删除 7 位追溯码前缀

药品新增或编辑时，如果 `trace_code_prefix` 是 7 位数字，则写入 `medicine_trace_prefixes`；如果编辑时传入空字符串，则删除原前缀。

### 8.4 药品追溯码生成流程

系统支持三种追溯码来源：

1. 手动录入单个追溯码。
2. 根据库存数量自动补齐追溯码。
3. 扫码时遇到未知追溯码，自动建档入库。

单个录入接口：

```text
POST /api/medicine-trace-codes
```

流程：

```text
接收 medicine_id + trace_code
  -> 锁定对应 medicines 行
  -> 查询该药品库存 stock
  -> 查询已有追溯码数量
  -> 插入用户提供的 trace_code
  -> 如果 stock > existingCount + 1，则自动生成剩余追溯码
  -> 写入 DRUG_INBOUND 审计记录
  -> 提交事务
```

追溯码生成规则：

- 有药品前缀：`7 位前缀 + 13 位随机数字 = 20 位追溯码`
- 无药品前缀：生成 20 位随机数字

批量生成：

- `POST /api/medicine-trace-codes/generate-all`：为所有库存大于 0 的药品补齐缺失追溯码。
- `POST /api/medicine-trace-codes/regenerate-all`：清空追溯码并按库存重新生成，适合测试阶段重建数据。

### 8.5 医生开具处方流程

前端页面：`pages/PrescriptionNewPage.tsx`

后端接口：

```text
POST /api/prescriptions
```

角色要求：

- `doctor`
- `admin`

前端操作流程：

```text
选择处方类型/费别/病历号/科别/床位号
  -> 搜索并选择患者
  -> 填写诊断
  -> 搜索药品或输入追溯码
  -> 通过 lookup 校验追溯码
  -> 填写用量、用法、频次、天数、数量
  -> 最多添加 5 种药品
  -> 确认提交
```

后端校验逻辑：

- 必须有患者、诊断和药品明细。
- 药品明细不能为空。
- 每张处方最多 5 种药品。
- 每个明细必须有 `medicine_id`、`dosage`、`trace_code`。
- 同一张处方内药品不能重复。
- 同一张处方内追溯码不能重复。
- 追溯码必须存在。
- 追溯码必须属于所选药品。
- 追溯码不能已关联其他处方。
- 追溯码必须仍处于 `pending`，且三个扫码时间均为空。

事务内处理：

```text
锁定追溯码行 FOR UPDATE
  -> 计算总金额 total_amount
  -> 生成 prescription_code
  -> 插入 prescriptions
  -> 插入 prescription_items
  -> 更新 medicine_trace_codes.prescription_id
  -> 插入 prescription_trace_codes
  -> 追加 PRESCRIPTION_CREATED 审计记录
  -> commit
```

处方编号生成规则：

```text
处方类型编码 2 位 + 日期 8 位 + 当日流水 3 位 + 校验码 2 位
```

示例结构：

```text
01 20260707 001 18
```

其中校验码为前 13 位数字求和后 `mod 97`，补齐 2 位。

### 8.6 药师审方流程

前端页面：`pages/ReviewPage.tsx`

接口：

```text
GET /api/prescriptions?status=pending
PUT /api/prescriptions/:id/review
```

角色要求：

- `pharmacist`
- `admin`

流程：

```text
药师打开审方页
  -> 查询 pending 处方
  -> 查看处方详情
  -> 选择通过或驳回
  -> 后端校验处方仍为 pending
  -> 更新 status、pharmacist_review_id、reviewed_at
```

状态变化：

- 通过：`pending -> approved`
- 驳回：`pending -> rejected`

### 8.7 发药流程

接口：

```text
PUT /api/prescriptions/:id/dispense
```

角色要求：

- `pharmacist`
- `admin`

流程：

```text
根据处方 ID 查询状态
  -> 仅 approved 可发药
  -> 更新 status = dispensed
  -> 写入 pharmacist_dispense_id
  -> 写入 dispensed_at
```

状态变化：

```text
approved -> dispensed
```

### 8.8 移动端扫码核验流程

前端页面：`pages/ScanPage.tsx`

核心依赖：

- `html5-qrcode`
- 浏览器摄像头权限
- 本地 HTTPS，因为多数移动浏览器要求 HTTPS 才允许摄像头访问

接口：

```text
POST /api/medicine-trace-codes/scan-by-code
PUT /api/medicine-trace-codes/:id/scan
PUT /api/medicine-trace-codes/:id/unscan
GET /api/medicine-trace-codes/lookup
```

扫码输入兼容处理：

系统不仅支持纯追溯码，还支持从 URL 或混合字符串中提取追溯码：

- 原始字符串
- URL decode 后的字符串
- URL query 中的 `trace_code`、`traceCode`、`code`、`c`
- 去除空格和横线后的连续数字
- 文本中匹配到的 20 位以上数字

扫码状态推进：

```text
pending
  -> 第一次扫码：scanned_identify，记录 scan1_time / scan1_user_id
scanned_identify
  -> 第二次扫码：scanned_outbound，记录 scan2_time / scan2_user_id，写 DRUG_OUTBOUND 审计
scanned_outbound
  -> 第三次扫码：scanned_confirm，记录 scan3_time / scan3_user_id，写 NURSE_RECEIVED 审计
scanned_confirm
  -> 再次扫码返回已完成
```

扫码时如果追溯码不存在：

```text
提取规范追溯码
  -> 校验至少包含 7 位数字
  -> 取前 7 位作为药品前缀
  -> 查询 medicine_trace_prefixes
  -> 找到药品则创建追溯码，并增加库存
  -> 找不到则创建“其他”药品并绑定此前缀
  -> 写 DRUG_INBOUND 审计记录
  -> 返回 action = 录入
```

### 8.9 药品位置管理流程

接口：

```text
GET /api/medicine-locations
POST /api/medicine-locations
PUT /api/medicine-locations/:id
DELETE /api/medicine-locations/:id
```

特点：

- 列表以 `medicines` 为主表左连接货位信息。
- 如果某药品没有货位记录，默认返回 `x=1`、`y=1`、`z=1`。
- 新增时如果该药品已有货位，接口会更新第一条货位记录，而不是重复插入。
- 返回结果补充药品规格、厂家和追溯码前缀。

## 9. 后端 API 总览

### 9.1 认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录 |
| GET | `/api/auth/me` | 获取当前用户 |

### 9.2 患者

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/patients` | 分页列表，可按姓名/电话搜索 |
| POST | `/api/patients` | 新增患者 |
| GET | `/api/patients/:id` | 患者详情和历史处方 |
| PUT | `/api/patients/:id` | 更新患者 |
| DELETE | `/api/patients/:id` | 删除患者及相关处方 |

### 9.3 药品

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/medicines` | 分页列表，可按药品名/厂家搜索 |
| POST | `/api/medicines` | 新增药品 |
| PUT | `/api/medicines/:id` | 更新药品 |
| DELETE | `/api/medicines/:id` | 删除药品 |
| PUT | `/api/medicines/:id/prefix` | 设置追溯码前缀 |
| DELETE | `/api/medicines/:id/prefix` | 删除追溯码前缀 |

### 9.4 处方

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/prescriptions` | 分页列表，医生只看自己的处方 |
| POST | `/api/prescriptions` | 创建处方 |
| GET | `/api/prescriptions/:id` | 处方详情和明细 |
| PUT | `/api/prescriptions/:id/review` | 审核处方 |
| PUT | `/api/prescriptions/:id/dispense` | 发药 |
| DELETE | `/api/prescriptions/:id` | 删除处方和关联追溯码 |
| DELETE | `/api/prescriptions/all` | 删除全部处方和关联追溯码 |

### 9.5 追溯码

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/medicine-trace-codes` | 追溯码分页列表，可按药品过滤 |
| POST | `/api/medicine-trace-codes` | 新增追溯码并按库存补齐 |
| PUT | `/api/medicine-trace-codes/:id` | 修改追溯码 |
| DELETE | `/api/medicine-trace-codes/:id` | 删除未关联处方的追溯码 |
| GET | `/api/medicine-trace-codes/lookup` | 查询追溯码，不推进状态 |
| POST | `/api/medicine-trace-codes/scan-by-code` | 按追溯码扫码并推进状态 |
| PUT | `/api/medicine-trace-codes/:id/scan` | 按 ID 推进扫码状态 |
| PUT | `/api/medicine-trace-codes/:id/unscan` | 回退一个扫码状态 |
| POST | `/api/medicine-trace-codes/generate-all` | 批量补齐追溯码 |
| POST | `/api/medicine-trace-codes/regenerate-all` | 清空并重新生成追溯码 |

### 9.6 药品位置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/medicine-locations` | 药品位置列表 |
| GET | `/api/medicine-locations/:id` | 单条位置 |
| POST | `/api/medicine-locations` | 新增或更新药品位置 |
| PUT | `/api/medicine-locations/:id` | 更新位置 |
| DELETE | `/api/medicine-locations/:id` | 删除位置 |

### 9.7 审计链

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/audit-chain` | 分页查询审计记录 |
| GET | `/api/audit-chain/verify` | 校验审计链完整性 |

### 9.8 健康检查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 返回服务状态和服务器时间 |

## 10. 特别技术点

### 10.1 追溯码与处方强绑定

系统不是简单把药品加入处方，而是要求处方明细必须携带追溯码。创建处方时后端会用事务锁定追溯码行，并校验：

- 追溯码存在。
- 追溯码属于当前药品。
- 追溯码未关联其他处方。
- 追溯码尚未发生任何扫码流转。
- 同处方中追溯码不重复。
- 同处方中药品不重复。

这保证了药品从处方创建起就有唯一可追踪实体，避免后续发药时出现“处方药品”和“实际药盒”脱节。

### 10.2 事务与行锁保护并发一致性

处方创建、追溯码录入、扫码状态推进等关键流程都使用数据库事务。涉及追溯码归属和状态变更时，代码使用 `FOR UPDATE` 锁定记录。

这样可以避免并发情况下出现：

- 两个处方同时绑定同一个追溯码。
- 同一个追溯码被重复扫码推进。
- 库存补齐和手动录入产生数量不一致。

### 10.3 追溯码输入归一化

扫码场景中，实际扫描结果可能不是纯数字，可能是平台 URL、带参数链接、包含空格或横线的文本。系统在前后端都实现了候选追溯码提取逻辑，从多个来源中提取有效数字串。

支持模式：

- 原始输入
- URL decode
- URL query 参数
- 去除空格/横线
- 正则提取连续数字

这提升了扫码兼容性，降低现场硬件或码制差异带来的失败率。

### 10.4 三段式扫码状态机

药品追溯码采用固定状态机：

```text
待处理 -> 已识别 -> 已出库 -> 已确认
```

每次扫码只推进一步，并记录对应操作人和时间。该设计使扫码动作既能表达当前业务进度，又能形成可审计的操作轨迹。

系统还提供 `unscan` 回退接口，便于在误扫时回退一个状态。

### 10.5 可信审计链

审计链位于 `services/auditChain.ts`。它将关键业务事件写入 `audit_chain_records`，每条记录都包含：

- 规范化后的 payload
- payload 哈希
- 上一条记录哈希
- 当前记录哈希

当前哈希计算包含：

```text
chainVersion + payloadHash + previousHash
```

校验时从第一条记录开始顺序重算：

1. 重算 payloadHash。
2. 校验当前记录的 previous_hash 是否等于上一条 current_hash。
3. 重算 current_hash。
4. 任一不一致则返回断点记录 ID。

系统写入的审计事件包括：

- `DRUG_INBOUND`：药品/追溯码入库
- `PRESCRIPTION_CREATED`：处方创建
- `DRUG_OUTBOUND`：药品出库
- `NURSE_RECEIVED`：最终确认接收

隐私保护方面，审计链不直接写入追溯码、处方和操作员明文，而是通过 `AUDIT_HASH_SALT` 加盐哈希后保存。

### 10.6 文件完整性保护

后端启动时会执行 `verifyIntegrity()`：

```text
读取 server/.integrity
  -> AES-256-CBC 解密校验清单
  -> 对受保护文件逐个计算 SHA-256
  -> 任一文件缺失或哈希不匹配则拒绝启动
```

服务运行后会每 60 秒再次校验一次。如果发现文件被篡改，会触发关闭回调并退出服务。

合法修改受保护文件后，需要运行：

```bash
node scripts/generate-checksums.js <密码>
```

重新生成校验清单。

### 10.7 多层截止日期保护

系统中存在多层截止日期判断，截止日期为 `2026-12-31`：

- 前端路由层：超过日期后直接显示停止服务提示。
- 登录接口：超过日期后拒绝登录。
- 全局后端中间件：除登录外的 API 请求会被拦截。
- JWT 生成层：超过日期后生成极短有效期 token。
- 数据库查询层：包装 `pool.query`，超过日期后拒绝 SQL 查询。

该设计通过多处调用降低单点绕过风险。

### 10.8 本地 HTTPS 支持移动端扫码

移动端浏览器通常要求 HTTPS 才能调用摄像头。启动脚本会在 `his/client` 下生成 `key.pem` 和 `cert.pem`，Vite 配置检测到证书后会启用 HTTPS。

首次访问自签名证书地址时，需要浏览器手动信任证书。

### 10.9 前端移动端访问控制

`App.tsx` 中的 `MobileOnly` 会根据 User-Agent 判断移动端。如果是移动设备，除 `/scan` 和 `/login` 外，会自动跳转到 `/scan`。

这样可以让手机端聚焦扫码核验，桌面端承担完整管理和审方功能。

### 10.10 前端请求统一处理

`services/api.ts` 封装 axios 实例：

- 所有请求默认走 `/api`。
- 请求拦截器自动添加 JWT。
- 响应拦截器遇到 `401` 或 `503` 时清理登录态并跳转登录页。
- 将患者、药品、处方、追溯码、审计链 API 统一封装为对象方法。

## 11. 前端页面说明

| 页面 | 路径 | 说明 |
| --- | --- | --- |
| LoginPage | `/login` | 登录 |
| DashboardPage | `/dashboard` | 系统首页/模块入口 |
| PatientListPage | `/patients` | 患者列表 |
| PatientDetailPage | `/patients/:id` | 患者详情和历史处方 |
| PatientNewPage | 组件存在 | 患者新增页 |
| PrescriptionListPage | `/prescriptions` | 处方列表 |
| PrescriptionNewPage | `/prescriptions/new` | 医生开方 |
| PrescriptionDetailPage | `/prescriptions/:id` | 处方详情 |
| ReviewPage | `/review` | 药师审方 |
| MedicinePage | `/medicines`、`/medicine-info` | 药品管理 |
| MedicineLocationsPage | `/medicine-locations` | 药品位置管理 |
| ScanPage | `/scan` | 移动端扫码核验 |
| BasicModulePage | 多个模块路径 | 报表、库存、补药、下架等基础模块入口 |

## 12. 部署与运行

### 12.1 安装依赖

后端：

```bash
cd his/server
npm ci
```

前端：

```bash
cd his/client
npm ci
```

### 12.2 开发启动

推荐使用一键脚本：

```bash
cd his
bash ./start-his.sh
```

也可以分别启动：

```bash
cd his/server
npm run dev
```

```bash
cd his/client
npm run dev
```

### 12.3 构建

后端：

```bash
cd his/server
npm run build
```

前端：

```bash
cd his/client
npm run build
```

## 13. 验证建议

### 13.1 基础验证

1. 使用 `doctor1 / 123456` 登录。
2. 搜索患者并开具处方。
3. 输入未使用且属于所选药品的追溯码。
4. 提交后确认处方状态为 `pending`。
5. 使用 `pharmacist1 / 123456` 登录。
6. 在审方页通过处方。
7. 打开扫码页，扫码或手动输入追溯码。
8. 连续扫码三次，观察状态依次变为已识别、已出库、已完成。
9. 查看审计链列表和 `/api/audit-chain/verify` 校验结果。

### 13.2 构建验证

```bash
cd his/server
npm run build
```

```bash
cd his/client
npm run build
```

### 13.3 接口验证

登录后带 token 请求：

```bash
curl -H "Authorization: Bearer <token>" http://localhost:3001/api/health
```

审计链校验：

```bash
curl -H "Authorization: Bearer <token>" http://localhost:3001/api/audit-chain/verify
```

## 14. 当前实现边界与注意事项

- JWT 密钥当前写在代码中，正式生产环境应改为环境变量。
- 数据库默认连接信息写在代码中，生产环境应使用环境变量覆盖。
- 部分中文源文件在当前终端显示为乱码，通常与文件编码或终端编码有关，不影响本文档按代码结构描述功能。
- `DELETE /api/prescriptions/all` 和追溯码重建接口适合测试或演示环境，生产环境应增加更严格的角色限制和二次确认。
- 审计链能发现链路记录被篡改，但不替代数据库权限控制和备份策略。
- 文件完整性校验依赖 `.integrity` 清单，代码合法修改后必须重新生成清单，否则后端会拒绝启动。

