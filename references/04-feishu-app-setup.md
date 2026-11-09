# 04 · 飞书自建应用九步法

> 目标：从零拿到可用的 `app_id` / `app_secret`，并让这个应用**真的有权限**写你的多维表格。

---

## 目录

1. [先确认租户类型](#1-先确认租户类型)
2. [九步操作](#2-九步操作)
3. [权限清单](#3-权限清单)
4. [第 8 步为什么最容易漏](#4-第-8-步为什么最容易漏)
5. [验证与自检](#5-验证与自检)
6. [常见失败对照](#6-常见失败对照)

---

## 1. 先确认租户类型

| 类型 | 自建应用 | Base API | 说明 |
|---|---|---|---|
| 企业租户（有管理员） | ✅ 可建 | ✅ 完整 | 推荐路线 |
| 个人版 | ⚠️ 受限 | ⚠️ 部分接口不可用 | 先试，不行就降级为「脚本生成 CSV + 手工导入」 |
| 教育/团队版 | ✅ | ✅ | 同企业租户 |

判断方法：打开飞书 → 头像 → 「管理后台」能进就是有租户管理员；进不去说明是个人版或没有管理权。

---

## 2. 九步操作

### 第 1 步：进入开发者后台

打开 <https://open.feishu.cn/app>，用**要在哪个租户建表**的账号登录。

> 别开错租户。多租户账号很常见，建到别的公司去就白忙。

### 第 2 步：创建企业自建应用

「创建企业自建应用」→ 填：

| 项 | 建议值 | 注意 |
|---|---|---|
| 应用名称 | `微信归档机器人` | **后面加协作者时要靠这个名字搜**，起个好认的 |
| 应用描述 | 微信聊天记录导入多维表格 | — |
| 图标 | 随便传一个 | 可跳过 |

创建完进入应用详情页。

### 第 3 步：拿凭证

左侧「凭证与基础信息」：

```
App ID:     cli_xxxxxxxxxxxxxxxx
App Secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**App Secret 只完整显示一次**，复制走。丢了只能重置。

### 第 4 步：开通权限

左侧「权限管理」→ 搜索并开通下列 scope（详见 §3）。

一次开全，别分批——每次改权限都要重新发版审核。

### 第 5 步：创建版本并发布

左侧「版本管理与发布」→「创建版本」：

| 项 | 填什么 |
|---|---|
| 版本号 | `1.0.0` |
| 更新说明 | 初始版本 |
| 可用范围 | **全员可用**（或至少包含你自己） |

提交后状态变为「审核中」。

### 第 6 步：等审核

- 企业内应用通常几分钟到几小时
- 需要**租户管理员**在「管理后台 → 应用管理」里通过
- 没有管理员权限就只能等，或找管理员

状态变成「已发布」才算完。**没发布 = 权限不生效**，这是新手最常卡的地方。

### 第 7 步：验证凭证

```bash
curl -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
  -H "Content-Type: application/json" \
  -d '{"app_id":"cli_xxx","app_secret":"xxx"}'
```

成功返回：

```json
{
  "code": 0,
  "msg": "ok",
  "tenant_access_token": "t-xxxxxxxx",
  "expire": 7200
}
```

`expire: 7200` 就是 2 小时有效期，脚本必须做缓存和提前续期。

失败见 §6。

### 第 8 步：把应用加为文档协作者 ⚠️

**这一步不做，后面全白跑。**

Base 建出来后：

```
打开 Base → 右上角 ... → 添加文档协作者
→ 搜索框输入【应用名称】（不是 App ID！）
→ 选中应用 → 权限选「可编辑」
→ 确认
```

如果 Base 建在某个文件夹里，**文件夹也要给应用授权**，否则新建表会失败。

### 第 9 步：配置环境变量

在工作目录建 `.env`（不要放进技能目录）：

```bash
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx
```

并确保 `.gitignore` 包含：

```
.env
*.env
```

Windows 上临时设置（当前终端有效）：

```powershell
$env:FEISHU_APP_ID="cli_xxx"
$env:FEISHU_APP_SECRET="xxx"
```

---

## 3. 权限清单

在「权限管理」里按关键词搜，勾选以下权限：

| Scope | 中文名 | 用途 | 必需 |
|---|---|---|---|
| `bitable:app` | 查看、评论、编辑和管理多维表格 | 建表、建字段、读写记录 | ✅ |
| `drive:drive` | 查看、评论、编辑和管理云空间中所有文件 | 云盘上传、附件 | ✅ |
| `drive:file` | 上传、下载文件到云空间 | 附件上传（部分版本需要） | ✅ |
| `docx:document` | 创建及编辑新版文档 | 可选：生成阅读版文档 | ⬜ |
| `wiki:wiki` | 知识库节点读写 | 可选：归档到知识库 | ⬜ |

> 权限名称会随平台版本调整，以控制台实际显示为准。搜不到就搜关键词 `多维表格`、`云空间`。

---

## 4. 第 8 步为什么最容易漏

飞书的权限模型是**两层**：

```
第一层：应用权限（scope）   ← 第 4 步开的
         ↓
第二层：文档权限（collaborator）  ← 第 8 步开的
```

只开第一层，应用知道「我有权操作多维表格」；但具体到某一张表，它还是「外人」。

所以你会看到：

```json
{ "code": 91403, "msg": "Forbidden" }
```

**这不是 token 错了，也不是 scope 没开，是没加协作者。**

---

## 5. 验证与自检

发版后跑一遍完整自检：

```bash
# 1. 拿 token
curl -s -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
  -H "Content-Type: application/json" \
  -d '{"app_id":"'$FEISHU_APP_ID'","app_secret":"'$FEISHU_APP_SECRET'"}'
```

```bash
# 2. 用 token 调一个只读接口（列出云空间根目录）
curl -s "https://open.feishu.cn/open-apis/drive/v1/files?page_size=1" \
  -H "Authorization: Bearer <tenant_access_token>"
```

```bash
# 3. 读一次目标 Base 的元信息（验证协作者是否生效）
curl -s "https://open.feishu.cn/open-apis/bitable/v1/apps/<base_token>" \
  -H "Authorization: Bearer <tenant_access_token>"
```

三步全 `code: 0`，才算环境就绪。

---

## 6. 常见失败对照

| 现象 | 原因 | 处理 |
|---|---|---|
| `code: 10014` app not found | App ID 抄错 / 用了别的租户 | 重新复制，确认登录的租户 |
| `code: 10003` invalid param | JSON 格式错，或 secret 带空格 | 检查请求体 |
| `code: 99991663` tenant token 无效 | token 过期或带了 `Bearer` 前缀重复 | 重新获取；请求头只带一次 |
| `code: 91403` Forbidden | 没加文档协作者 / 没发布 | 做第 8 步；确认版本已发布 |
| `code: 99991672` 无权限访问 | scope 没开或没通过审核 | 回第 4 步，重新发版 |
| 建表时报 `permission denied` | 目标文件夹没授权给应用 | 文件夹也加协作者 |
| 发布一直「审核中」 | 没有租户管理员处理 | 找管理员，或在管理后台自行通过 |

> 遇到 403/91403 **不要循环重试**。重试一万次也不会自己变有权限，只会把日志刷满。
