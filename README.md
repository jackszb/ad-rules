# AdBlock Rules

## 订阅链接

```
https://raw.githubusercontent.com/emanresubuh/ad-rules/main/rule_srs/adblock_rules.srs
```

## 最新构建报告

## 📦 AdBlock Rules — 2026-05-12 18:31 CST

### 📊 本次统计

| 项目 | 数量 |
|---|---|
| 订阅源数量 | 5 个 |
| 订阅解析原始域名 | 337520 个 |
| 自定义屏蔽追加 | 1 个 |
| 白名单移除 | 1 个 |
| 子域名去冗余前 | 337519 个 |
| **最终规则数量** | **329428 个** |
| SRS 文件大小 | 2647.2 KB |

### 📈 变化对比

🔺 较上次增加 **262** 条

### 📥 订阅源明细

  - `https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.apple.txt` → 解析出 **104** 个域名
  - `https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.plus.txt` → 解析出 **242705** 个域名
  - `https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/AWAvenue-Ads-Rule.txt` → 解析出 **905** 个域名
  - `https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/anti-ad-easylist.txt` → 解析出 **100111** 个域名
  - `https://raw.githubusercontent.com/AdguardTeam/HostlistsRegistry/main/filters/general/filter_1_DnsFilter/filter.txt` → 解析出 **163501** 个域名

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