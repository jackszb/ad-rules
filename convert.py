#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert.py
针对 sing-box 1.13.x 版本优化
功能：下载 -> 解析域名 -> 全局去重 -> 子域名去冗余 -> 自定义规则 -> 生成 JSON -> 编译 SRS -> 输出统计报告
"""

import re
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests

# -------- 配置区域 --------
SOURCE_FILE     = "source.txt"
BLOCK_FILE      = "custom_block.txt"
ALLOW_FILE      = "custom_allow.txt"
JSON_OUTPUT     = "adblock_rules.json"
SRS_OUTPUT      = "adblock_rules.srs"
STATS_FILE      = "stats.json"           # 持久化上次统计数据
REPORT_FILE     = "release_notes.md"    # 供 workflow 读取的发布说明
SING_BOX_BIN    = "sing-box"
RULESET_VERSION = 2
TIMEOUT         = 60
CST             = timezone(timedelta(hours=8))
# -------------------------

HOSTS_RE   = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1|::1)\s+([a-z0-9.-]+\.[a-z]{2,})")
ADGUARD_RE = re.compile(r"^\|\|([a-z0-9.-]+\.[a-z]{2,})\^")
DOMAIN_RE  = re.compile(r"^([a-z0-9][a-z0-9-]{0,61}[a-z0-9](?:\.[a-z0-9][a-z0-9-]{0,61}[a-z0-9])+)$")

INVALID_DOMAINS = {
    "localhost", "local", "broadcasthost", "ip6-localhost",
    "ip6-loopback", "ip6-localnet", "ip6-mcastprefix",
    "ip6-allnodes", "ip6-allrouters", "ip6-allhosts"
}


def normalize_domain(domain: str) -> str:
    return domain.strip().lower().lstrip('.').rstrip('.')


def load_sources(path: str) -> list:
    p = Path(path)
    if not p.is_file():
        print(f"[-] 错误: 找不到 {path}")
        exit(1)
    sources = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith(("#", "//", ";")):
                sources.append(line)
    return sources


def load_custom(path: str) -> set:
    p = Path(path)
    if not p.is_file():
        return set()
    domains = set()
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lower()
            if line and not line.startswith(("#", "//", ";")):
                d = normalize_domain(line)
                if DOMAIN_RE.match(d) and d not in INVALID_DOMAINS:
                    domains.add(d)
    return domains


def load_last_stats() -> dict:
    p = Path(STATS_FILE)
    if not p.is_file():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_stats(data: dict):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_text(url: str) -> str:
    print(f"[+] 正在抓取: {url}")
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[!] 抓取失败 {url}: {e}")
        return ""


def parse_rules(text: str) -> set:
    domains = set()
    for line in text.splitlines():
        line = line.strip().lower()
        if not line or line.startswith(("!", "#", "@@")):
            continue

        m = ADGUARD_RE.match(line)
        if m:
            d = normalize_domain(m.group(1))
            if d not in INVALID_DOMAINS:
                domains.add(d)
            continue

        m = HOSTS_RE.match(line)
        if m:
            d = normalize_domain(m.group(1))
            if d not in INVALID_DOMAINS:
                domains.add(d)
            continue

        parts = line.split()
        if parts:
            candidate = normalize_domain(parts[0])
            if DOMAIN_RE.match(candidate) and candidate not in INVALID_DOMAINS:
                domains.add(candidate)

    return domains


def dedupe_subdomains(domains: set) -> list:
    sorted_domains = sorted(domains, key=lambda d: (d.split('.')[::-1], d))
    result = []
    for domain in sorted_domains:
        parts = domain.split('.')
        is_redundant = False
        for i in range(1, len(parts)):
            parent = '.'.join(parts[i:])
            if parent in domains:
                is_redundant = True
                break
        if not is_redundant:
            result.append(domain)
    return result


def generate_report(
    now_str: str,
    sources: list,
    source_counts: dict,
    total_raw: int,
    custom_block_count: int,
    custom_allow_count: int,
    allow_removed: int,
    before_dedup: int,
    final_count: int,
    last_stats: dict,
    srs_size_kb: float,
) -> str:
    last_count = last_stats.get("final_count", None)

    if last_count is None:
        diff_str = "_(首次生成，无历史数据对比)_"
    else:
        delta = final_count - last_count
        if delta > 0:
            diff_str = f"🔺 较上次增加 **{delta:,}** 条"
        elif delta < 0:
            diff_str = f"🔻 较上次减少 **{abs(delta):,}** 条"
        else:
            diff_str = "➡️ 与上次相比无变化"

    source_lines = "\n".join(
        f"  - `{url}` → 解析出 **{source_counts.get(url, 0):,}** 个域名"
        for url in sources
    )

    report = f"""## 📦 AdBlock Rules — {now_str}

### 📊 本次统计

| 项目 | 数量 |
|---|---|
| 订阅源数量 | {len(sources)} 个 |
| 订阅解析原始域名 | {total_raw:,} 个 |
| 自定义屏蔽追加 | {custom_block_count:,} 个 |
| 白名单移除 | {allow_removed:,} 个 |
| 子域名去冗余前 | {before_dedup:,} 个 |
| **最终规则数量** | **{final_count:,} 个** |
| SRS 文件大小 | {srs_size_kb:.1f} KB |

### 📈 变化对比

{diff_str}

### 📥 订阅源明细

{source_lines}

### 🚀 使用方式

在 sing-box 配置中引用（DNS 规则和路由规则均可）：

```json
{{
  "type": "remote",
  "tag": "adblock",
  "url": "https://github.com/{{REPO}}/releases/latest/download/adblock_rules.srs",
  "update_interval": "24h"
}}