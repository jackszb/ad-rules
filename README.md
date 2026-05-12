# AdBlock Rules

## 订阅链接

```
https://raw.githubusercontent.com/emanresubuh/ad-rules/main/rule_srs/adblock_rules.srs
```

## 最新构建报告

## 📦 AdBlock Rules — 2026-05-12 21:52 CST

### 📊 本次统计

| 项目 | 数量 |
|---|---|
| 订阅源数量 | 5 个 |
| 订阅解析原始域名 | 290290 个 |
| 自定义屏蔽追加 | 1 个 |
| 白名单移除 | 1 个 |
| 子域名去冗余前 | 290289 个 |
| **最终规则数量** | **282828 个** |
| SRS 文件大小 | 2259.5 KB |

### 📈 变化对比

🔻 较上次减少 **31597** 条

### 📥 订阅源明细

  - `https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.apple.txt` → 解析出 **65** 个域名
  - `https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.plus.txt` → 解析出 **209367** 个域名
  - `https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/AWAvenue-Ads-Rule.txt` → 解析出 **804** 个域名
  - `https://anti-ad.net/adguard.txt` → 解析出 **97055** 个域名
  - `https://raw.githubusercontent.com/AdguardTeam/HostlistsRegistry/main/filters/general/filter_1_DnsFilter/filter.txt` → 解析出 **146035** 个域名

### 🚀 使用方式

在 sing-box 配置中引用：

```json
{
  "type": "remote",
  "tag": "adblock",
  "url": "https://raw.githubusercontent.com/emanresubuh/ad-rules/main/rule_srs/adblock_rules.srs",
  "update_interval": "24h"
}
```