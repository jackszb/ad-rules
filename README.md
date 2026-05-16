# AdBlock Rules

## 订阅链接

```
https://raw.githubusercontent.com/emanresubuh/ad-rules/main/rule_srs/adblock_rules.srs
```

## 最新构建报告

## 📦 AdBlock Rules — 2026-05-16 13:20 CST

### 📊 本次统计

| 项目 | 数量 |
|---|---|
| 订阅源数量 | 5 个 |
| 订阅解析原始域名 | 681779 个 |
| 自定义屏蔽追加 | 1 个 |
| 白名单移除 | 1 个 |
| 子域名去冗余前 | 681778 个 |
| **最终规则数量** | **669658 个** |
| SRS 文件大小 | 5208.2 KB |

### 📈 变化对比

🔺 较上次增加 **85195** 条

### 📥 订阅源明细

  - `https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.apple.txt` → 解析出 **104** 个域名
  - `https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt` → 解析出 **195005** 个域名
  - `https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/AWAvenue-Ads-Rule.txt` → 解析出 **905** 个域名
  - `https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt` → 解析出 **164451** 个域名
  - `https://raw.githubusercontent.com/sjhgvr/oisd/main/oisd_big.txt` → 解析出 **494779** 个域名

### 🚀 使用方式

在 sing-box 配置中引用（DNS 规则和路由规则均可）：

```json
{
  "type": "remote",
  "tag": "adblock",
  "url": "https://raw.githubusercontent.com/emanresubuh/ad-rules/main/rule_srs/adblock_rules.srs",
  "update_interval": "24h"
}
```