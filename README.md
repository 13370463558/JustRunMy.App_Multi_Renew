# 🖥️ JustRunMy.App 自动续期 (单账号精简版)

> 从多账号版精简而来：删掉账号矩阵/乱序/错峰延迟，只保留**一个账号**的完整续期流程。

## 🌟 核心特色

- 📅 **每日执行**：每天定时触发，自动登录并续期。
- 🌐 **代理支持**：内置 sing-box 核心，支持 vless/vmess/tuic/hy2/anytls/socks5/http 等**明文**或**base编码**协议，已兼容 `pcs` 参数、hex 公钥、`allowInsecure` 等非标准节点。
- 📲 **Telegram 通知**（可选）：续期成功/失败推送到 TG。

## ⚡ 快速开始

1. **[Fork]** 本项目到个人仓库（或直接用本仓库）。
2. **[Secrets]** 配置账号信息：前往 `Settings` -> `Secrets and variables` -> `Actions`。
3. **[Actions]** 启用工作流：在 `Actions` 页面点击 "Run workflow" 或等待定时触发。

## 🛠️ 环境变量配置 (Secrets)

| 变量名 (Name) | 是否必填 | 示例值 (Value) | 说明 |
| :--- | :--- | :--- | :--- |
| **EML_1** | 是 | user@example.com | 账号邮箱（单账号，使用 . 结尾域名亦可） |
| **PWD_1** | 是 | your_password | 账号密码（与 EML_1 对应） |
| **PROXY_URL** | 否 | vless://uuid@host:port... | 代理链接 (支持 vless/vmess/tuic/hy2/anytls/socks5/http) |
| **TG_TOKEN** | 否 | 123456:ABC... | Telegram 机器人 Token |
| **TG_ID** | 否 | 987654321 | Telegram 用户 ID |

## 🔄 运行逻辑

1. **触发时间**：每天北京时间凌晨 06:00 (UTC 22:00) 或手动触发。
2. **登录续期**：SeleniumBase uc 模式（真实浏览器特征）+ 可选代理，自动登录 `justrunmy.app` → 进入控制面板 → 点击 Reset Timer → 完成续期。
3. **安全时限**：运行时间限制在 6 小时内，符合 GitHub Actions 限制。

## ⚠️ 调试与报错

每次运行都会在 `screenshots/` 目录下按步骤保存截图（每步 `NN_步骤名.png`，带时间戳），无论成功或失败都会上传到任务页面的 **[Artifacts]** 区域：

1. 在任务页面下载 `renew-screenshots` 压缩包。
2. 按文件名序号查看各步骤截图，定位是登录、人机验证（Turnstile）、点击按钮还是倒计时环节出了问题。
3. **常见问题**：
   - `未找到 EML_1 或 PWD_1`：请检查 Secrets 命名是否为 `EML_1` / `PWD_1`。
   - `Turnstile 验证失败`：通常是代理质量不佳或 Cloudflare 策略更新，建议更换 PROXY_URL。

## 🌟 特别鸣谢

在此感谢 [mangguo88/JustRunMy-Renew](https://github.com/mangguo88/JustRunMy-Renew) 项目提供的物理模拟算法支持与proxy代理想法。