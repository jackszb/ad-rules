#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert.py
针对 sing-box 1.13.x 版本优化
功能：下载 -> 解析域名 -> 全局去重 -> 子域名去冗余 -> 自定义规则 -> 生成 JSON -> 编译 SRS
"""

import re
import json
import subprocess
from pathlib import Path
import requests

# -------- 配置区域 --------
SOURCE_FILE   = "source.txt"
BLOCK_FILE    = "custom_block.txt"
ALLOW_FILE    = "custom_allow.txt"
JSON_OUTPUT   = "adblock_rules.json"
SRS_OUTPUT    = "adblock_rules.srs"
SING_BOX_BIN  = "sing-box"
RULESET_VERSION = 2
TIMEOUT = 60
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
    """读取订阅链接列表"""
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
    """读取自定义域名文件，忽略注释和空行"""
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


def fetch_text(url: str) -> str:
    """下载订阅内容"""
    print(f"[+] 正在抓取: {url}")
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[!] 抓取失败 {url}: {e}")
        return ""


def parse_rules(text: str) -> set:
    """解析域名，支持 AdGuard / Hosts / 纯域名格式"""
    domains = set()
    for line in text.splitlines():
        line = line.strip().lower()
        if not line or line.startswith(("!", "#", "@@")):
            continue

        # 1. AdGuard 格式：||example.com^
        m = ADGUARD_RE.match(line)
        if m:
            d = normalize_domain(m.group(1))
            if d not in INVALID_DOMAINS:
                domains.add(d)
            continue

        # 2. Hosts 格式：0.0.0.0 example.com
        m = HOSTS_RE.match(line)
        if m:
            d = normalize_domain(m.group(1))
            if d not in INVALID_DOMAINS:
                domains.add(d)
            continue

        # 3. 纯域名格式
        parts = line.split()
        if parts:
            candidate = normalize_domain(parts[0])
            if DOMAIN_RE.match(candidate) and candidate not in INVALID_DOMAINS:
                domains.add(candidate)

    return domains


def dedupe_subdomains(domains: set) -> list:
    """
    去除冗余子域名：
    若 example.com 已在集合中，则 ads.example.com 是多余的
    （domain_suffix 会自动覆盖所有子域名）
    """
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


def main():
    print("[*] 启动转换流程 (sing-box v1.13.x)")

    # 1. 下载并解析订阅
    sources = load_sources(SOURCE_FILE)
    all_domains: set = set()

    for url in sources:
        text = fetch_text(url)
        if text:
            extracted = parse_rules(text)
            print(f"[+] 解析出 {len(extracted)} 个独立域名")
            all_domains |= extracted

    if not all_domains:
        print("[-] 没有抓取到任何有效域名，任务停止。")
        return

    # 2. 合并自定义屏蔽（白名单处理前合并，确保白名单优先级更高）
    custom_block = load_custom(BLOCK_FILE)
    if custom_block:
        print(f"[+] 自定义屏蔽: {len(custom_block)} 个域名")
        all_domains |= custom_block
    else:
        print(f"[*] 未找到 {BLOCK_FILE} 或文件为空，跳过自定义屏蔽")

    # 3. 应用白名单（精确移除 + 移除以该域名为父域的条目）
    custom_allow = load_custom(ALLOW_FILE)
    if custom_allow:
        before = len(all_domains)
        all_domains = {
            d for d in all_domains
            if d not in custom_allow
            and not any(d.endswith('.' + a) for a in custom_allow)
        }
        print(f"[+] 白名单放行: 移除 {before - len(all_domains)} 个域名")
    else:
        print(f"[*] 未找到 {ALLOW_FILE} 或文件为空，跳过白名单")

    # 4. 子域名去冗余
    print(f"[*] 去重前总计: {len(all_domains)} 个域名")
    deduped = dedupe_subdomains(all_domains)
    print(f"[*] 子域名去冗余后: {len(deduped)} 个域名")

    # 5. 生成 JSON
    ruleset_json = {
        "version": RULESET_VERSION,
        "rules": [
            {
                "domain_suffix": deduped
            }
        ]
    }

    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(ruleset_json, f, ensure_ascii=False, indent=2)
    print(f"[+] 已生成 JSON: {JSON_OUTPUT}")

    # 6. 编译 SRS
    print("[+] 正在调用 sing-box 编译 SRS...")
    try:
        result = subprocess.run(
            [SING_BOX_BIN, "rule-set", "compile", "--output", SRS_OUTPUT, JSON_OUTPUT],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"[#] 成功生成: {Path(SRS_OUTPUT).resolve()}")
        else:
            print(f"[!] 编译失败 (Exit Code {result.returncode}):\n{result.stderr}")
            exit(result.returncode)
    except FileNotFoundError:
        print("[-] 错误: 系统中未找到 sing-box 命令，请检查安装路径。")
        exit(1)


if __name__ == "__main__":
    main()
