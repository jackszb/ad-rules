#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert.py
针对 sing-box 1.13.x 版本优化
功能：下载 -> 解析域名 -> 全局去重 -> 子域名去冗余 -> 自定义规则 -> 生成 JSON -> 编译 SRS -> 输出统计报告 -> 更新 README
"""

import re
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests

# -------- 配置区域 --------
SOURCE_FILE      = "source.txt"
BLOCK_FILE       = "custom_block.txt"
ALLOW_FILE       = "custom_allow.txt"
JSON_OUTPUT      = "adblock_rules.json"
SRS_OUTPUT       = "adblock_rules.srs"
STATS_FILE       = "stats.json"
REPORT_FILE      = "release_notes.md"
SING_BOX_BIN     = "sing-box"
RULESET_VERSION  = 2
TIMEOUT          = 60
CST              = timezone(timedelta(hours=8))
REPO_USER        = "emanresubuh"
REPO_NAME        = "ad-rules"
SRS_URL          = "https://raw.githubusercontent.com/" + REPO_USER + "/" + REPO_NAME + "/main/rule_srs/adblock_rules.srs"
# -------------------------

HOSTS_RE      = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1|::1)\s+([a-z0-9.-]+\.[a-z]{2,})")
ADGUARD_RE    = re.compile(r"^\|\|([a-z0-9.-]+\.[a-z]{2,})\^")
DOMAIN_RE     = re.compile(r"^([a-z0-9][a-z0-9-]{0,61}[a-z0-9](?:\.[a-z0-9][a-z0-9-]{0,61}[a-z0-9])+)$")
SKIP_LINE_RE  = re.compile(r"https?://|/")
COSMETIC_RE   = re.compile(r"#[@$?]?#|#%#|#script:")

INVALID_DOMAINS = {
    "localhost", "local", "broadcasthost", "ip6-localhost",
    "ip6-loopback", "ip6-localnet", "ip6-mcastprefix",
    "ip6-allnodes", "ip6-allrouters", "ip6-allhosts"
}

WHITELIST_DOMAINS = {
    "raw.githubusercontent.com",
    "github.com",
    "githubusercontent.com",
}


def normalize_domain(domain: str) -> str:
    return domain.strip().lower().lstrip('.').rstrip('.')


def load_sources(path: str) -> list:
    p = Path(path)
    if not p.is_file():
        print("[-] 错误: 找不到 " + path)
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
                if DOMAIN_RE.match(d) and d not in INVALID_DOMAINS and d not in WHITELIST_DOMAINS:
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
    print("[+] 正在抓取: " + url)
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print("[!] 抓取失败 " + url + ": " + str(e))
        return ""


def parse_rules(text: str) -> set:
    domains = set()
    for line in text.splitlines():
        line = line.strip().lower()
        if not line or line.startswith(("!", "#", "@@")):
            continue

        # 跳过 cosmetic/脚本规则：## #@# #$# #%# #?# #script:
        if COSMETIC_RE.search(line):
            continue

        # 跳过包含 http 或路径斜杠的行，避免误提取 URL 中的域名
        if SKIP_LINE_RE.search(line):
            continue

        # 1. AdGuard 格式：||example.com^
        m = ADGUARD_RE.match(line)
        if m:
            d = normalize_domain(m.group(1))
            if d not in INVALID_DOMAINS and d not in WHITELIST_DOMAINS:
                domains.add(d)
            continue

        # 2. Hosts 格式：0.0.0.0 example.com
        m = HOSTS_RE.match(line)
        if m:
            d = normalize_domain(m.group(1))
            if d not in INVALID_DOMAINS and d not in WHITELIST_DOMAINS:
                domains.add(d)
            continue

        # 3. 纯域名格式
        parts = line.split()
        if parts:
            candidate = normalize_domain(parts[0])
            if (DOMAIN_RE.match(candidate)
                    and candidate not in INVALID_DOMAINS
                    and candidate not in WHITELIST_DOMAINS):
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
    now_str,
    sources,
    source_counts,
    total_raw,
    custom_block_count,
    custom_allow_count,
    allow_removed,
    before_dedup,
    final_count,
    last_stats,
    srs_size_kb,
):
    last_count = last_stats.get("final_count", None)

    if last_count is None:
        diff_str = "_(首次生成，无历史数据对比)_"
    else:
        delta = final_count - last_count
        if delta > 0:
            diff_str = "🔺 较上次增加 **" + str(delta) + "** 条"
        elif delta < 0:
            diff_str = "🔻 较上次减少 **" + str(abs(delta)) + "** 条"
        else:
            diff_str = "➡️ 与上次相比无变化"

    source_lines = "\n".join(
        "  - `" + url + "` → 解析出 **" + str(source_counts.get(url, 0)) + "** 个域名"
        for url in sources
    )

    sing_box_snippet = (
        "```json\n"
        "{\n"
        '  "type": "remote",\n'
        '  "tag": "adblock",\n'
        '  "url": "' + SRS_URL + '",\n'
        '  "update_interval": "24h"\n'
        "}\n"
        "```"
    )

    lines = [
        "## 📦 AdBlock Rules — " + now_str,
        "",
        "### 📊 本次统计",
        "",
        "| 项目 | 数量 |",
        "|---|---|",
        "| 订阅源数量 | " + str(len(sources)) + " 个 |",
        "| 订阅解析原始域名 | " + str(total_raw) + " 个 |",
        "| 自定义屏蔽追加 | " + str(custom_block_count) + " 个 |",
        "| 白名单移除 | " + str(allow_removed) + " 个 |",
        "| 子域名去冗余前 | " + str(before_dedup) + " 个 |",
        "| **最终规则数量** | **" + str(final_count) + " 个** |",
        "| SRS 文件大小 | " + str(round(srs_size_kb, 1)) + " KB |",
        "",
        "### 📈 变化对比",
        "",
        diff_str,
        "",
        "### 📥 订阅源明细",
        "",
        source_lines,
        "",
        "### 🚀 使用方式",
        "",
        "在 sing-box 配置中引用（DNS 规则和路由规则均可）：",
        "",
        sing_box_snippet,
    ]

    return "\n".join(lines)


def main():
    print("[*] 启动转换流程 (sing-box v1.13.x)")
    now = datetime.now(CST)
    now_str = now.strftime("%Y-%m-%d %H:%M CST")

    # 1. 下载并解析订阅
    sources = load_sources(SOURCE_FILE)
    all_domains: set = set()
    source_counts: dict = {}

    for url in sources:
        text = fetch_text(url)
        if text:
            extracted = parse_rules(text)
            source_counts[url] = len(extracted)
            print("[+] 解析出 " + str(len(extracted)) + " 个独立域名")
            all_domains |= extracted

    if not all_domains:
        print("[-] 没有抓取到任何有效域名，任务停止。")
        return

    total_raw = len(all_domains)

    # 2. 合并自定义屏蔽
    custom_block = load_custom(BLOCK_FILE)
    if custom_block:
        print("[+] 自定义屏蔽: " + str(len(custom_block)) + " 个域名")
        all_domains |= custom_block
    else:
        print("[*] 未找到 " + BLOCK_FILE + " 或文件为空，跳过自定义屏蔽")

    # 3. 应用白名单
    custom_allow = load_custom(ALLOW_FILE)
    allow_removed = 0
    if custom_allow:
        before = len(all_domains)
        all_domains = {
            d for d in all_domains
            if d not in custom_allow
            and not any(d.endswith('.' + a) for a in custom_allow)
        }
        allow_removed = before - len(all_domains)
        print("[+] 白名单放行: 移除 " + str(allow_removed) + " 个域名")
    else:
        print("[*] 未找到 " + ALLOW_FILE + " 或文件为空，跳过白名单")

    # 4. 子域名去冗余
    before_dedup = len(all_domains)
    print("[*] 去重前总计: " + str(before_dedup) + " 个域名")
    deduped = dedupe_subdomains(all_domains)
    final_count = len(deduped)
    print("[*] 子域名去冗余后: " + str(final_count) + " 个域名")

    # 5. 生成 JSON
    ruleset_json = {
        "version": RULESET_VERSION,
        "rules": [{"domain_suffix": deduped}]
    }
    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(ruleset_json, f, ensure_ascii=False, indent=2)
    print("[+] 已生成 JSON: " + JSON_OUTPUT)

    # 6. 编译 SRS
    print("[+] 正在调用 sing-box 编译 SRS...")
    try:
        result = subprocess.run(
            [SING_BOX_BIN, "rule-set", "compile", "--output", SRS_OUTPUT, JSON_OUTPUT],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("[#] 成功生成: " + str(Path(SRS_OUTPUT).resolve()))
        else:
            print("[!] 编译失败 (Exit Code " + str(result.returncode) + "):\n" + result.stderr)
            exit(result.returncode)
    except FileNotFoundError:
        print("[-] 错误: 系统中未找到 sing-box 命令，请检查安装路径。")
        exit(1)

    srs_size_kb = Path(SRS_OUTPUT).stat().st_size / 1024

    # 7. 生成统计报告
    last_stats = load_last_stats()
    report = generate_report(
        now_str            = now_str,
        sources            = sources,
        source_counts      = source_counts,
        total_raw          = total_raw,
        custom_block_count = len(custom_block),
        custom_allow_count = len(custom_allow),
        allow_removed      = allow_removed,
        before_dedup       = before_dedup,
        final_count        = final_count,
        last_stats         = last_stats,
        srs_size_kb        = srs_size_kb,
    )

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print("[+] 已生成发布说明: " + REPORT_FILE)
    print(report)

    # 8. 持久化本次统计
    save_stats({
        "final_count": final_count,
        "updated_at":  now_str,
    })
    print("[+] 已保存统计数据: " + STATS_FILE)

    # 9. 更新 README.md
    readme_content = (
        "# AdBlock Rules\n\n"
        "## 订阅链接\n\n"
        "```\n"
        + SRS_URL + "\n"
        "```\n\n"
        "## 最新构建报告\n\n"
        + report
    )
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("[+] 已更新 README.md")


if __name__ == "__main__":
    main()
