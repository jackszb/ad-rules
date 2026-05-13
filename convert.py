#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert.py
针对 sing-box 1.13.x 版本优化
功能：多源下载 -> 严格解析 -> 全局去重 -> 子域名去冗余 -> 自定义规则 -> PSL保护 -> 生成 JSON -> 编译 SRS -> 统计报告 -> 更新 README
"""

import re
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Set, List, Dict
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
RULESET_VERSION  = 4
TIMEOUT          = 60
FETCH_RETRIES    = 3
RETRY_BACKOFF    = 2
CST              = timezone(timedelta(hours=8))
REPO_USER        = "emanresubuh"
REPO_NAME        = "ad-rules"
SRS_URL          = "https://raw.githubusercontent.com/" + REPO_USER + "/" + REPO_NAME + "/main/rule_srs/adblock_rules.srs"
PSL_URL          = "https://publicsuffix.org/list/public_suffix_list.dat"
# -------------------------

# AdGuard 格式：允许通配符 *，^ 后选项一律忽略
ADGUARD_RE   = re.compile(r"^\|\|([a-z0-9*.-]+\.[a-z]{2,})\^")
# Hosts 格式
HOSTS_RE     = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1|::1)\s+([a-z0-9.-]+\.[a-z]{2,})")
# dnsmasq 格式：address=/example.com/
DNSMASQ_RE   = re.compile(r"^address=/([a-z0-9.-]+\.[a-z]{2,})/")
# 纯域名格式校验
DOMAIN_RE    = re.compile(r"^([a-z0-9][a-z0-9-]{0,61}[a-z0-9](?:\.[a-z0-9][a-z0-9-]{0,61}[a-z0-9])+)$")
# cosmetic/脚本规则（整行跳过）
COSMETIC_RE  = re.compile(r"#[@$?]?#|#%#|#script:")

INVALID_DOMAINS: Set[str] = {
    "localhost", "local", "broadcasthost", "ip6-localhost", "ip6-loopback",
    "ip6-localnet", "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters", "ip6-allhosts"
}

# 只精确匹配主域本身，不放行其子域
# 原因：子域可能存在广告（如 ads.youtube.com）
WHITELIST_DOMAINS: Set[str] = {
    "youtube.com", "youtu.be", "googlevideo.com", "ytimg.com",
    "google.com", "gstatic.com", "googleapis.com",
    "apple.com", "icloud.com", "mzstatic.com", "apple-dns.net",
    "github.com", "githubusercontent.com", "raw.githubusercontent.com",
    "cloudflare.com", "fastly.net",
    "microsoft.com", "windows.com", "office.com",
}

PRIVATE_SUFFIXES: Set[str] = {
    ".local", ".internal", ".lan", ".home", ".corp", ".test", ".example"
}

PUBLIC_SUFFIXES: Set[str] = set()


def load_public_suffix_list():
    global PUBLIC_SUFFIXES
    print("[+] 正在加载 Public Suffix List...")
    try:
        resp = requests.get(PSL_URL, timeout=30)
        resp.raise_for_status()
        for line in resp.text.splitlines():
            line = line.strip().lower()
            # 跳过注释、空行、通配符条目（通配符条目不代表该域名本身是公共后缀）
            if line and not line.startswith(("//", "!", "*")):
                PUBLIC_SUFFIXES.add(line)
        print("[+] PSL 加载完成: " + str(len(PUBLIC_SUFFIXES)) + " 条公共后缀")
    except Exception as e:
        print("[!] PSL 加载失败: " + str(e))
        # 不清空集合，但外部会检查是否为空，选择终止


def is_public_suffix(domain: str) -> bool:
    """
    只做精确匹配。
    PSL 中的 *.ck 条目含义是 ck 下的二级域名都是可注册域名，
    不代表 example.ck 本身是公共后缀，因此通配符条目在加载时已跳过。
    """
    if not domain:
        return False
    return domain in PUBLIC_SUFFIXES


def normalize_domain(domain: str) -> str:
    return domain.strip().lower().lstrip('.').rstrip('.')


def should_keep_domain(d: str) -> bool:
    """域名过滤核心逻辑，只判断域名本身"""
    if not d or len(d) < 4:
        return False
    if '..' in d:
        return False
    if d in INVALID_DOMAINS:
        return False
    # 只精确匹配白名单，不放行子域
    if d in WHITELIST_DOMAINS:
        return False
    if is_public_suffix(d):
        return False
    if any(d.endswith(s) for s in PRIVATE_SUFFIXES):
        return False
    if not DOMAIN_RE.match(d):
        return False
    return True


def load_sources(path: str) -> List[str]:
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


def load_custom(path: str) -> Set[str]:
    p = Path(path)
    if not p.is_file():
        return set()
    domains: Set[str] = set()
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lower()
            if line and not line.startswith(("#", "//", ";")):
                d = normalize_domain(line)
                if DOMAIN_RE.match(d) and d not in INVALID_DOMAINS:
                    domains.add(d)
    return domains


def load_last_stats() -> Dict:
    p = Path(STATS_FILE)
    if not p.is_file():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_stats(data: Dict):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_text(url: str) -> str:
    """带重试和指数退避的抓取"""
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            print("[+] 正在抓取 (第 " + str(attempt) + " 次): " + url)
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print("[!] 抓取失败: " + str(e))
            if attempt < FETCH_RETRIES:
                wait = RETRY_BACKOFF ** attempt
                print("[*] " + str(wait) + " 秒后重试...")
                time.sleep(wait)
    print("[-] 已放弃: " + url)
    return ""


def parse_rules(text: str) -> Set[str]:
    """
    解析规则：先提取域名，再过滤。
    不对整行做内容判断（除 cosmetic 行），
    确保带选项的规则（$third-party 等）不会因选项丢失域名。
    """
    domains: Set[str] = set()

    for line in text.splitlines():
        line = line.strip().lower()

        # 空行、注释、白名单行、文件头跳过
        if not line or line.startswith(("!", "#", "@@", "[adblock", ";")):
            continue

        # cosmetic/脚本规则整行跳过
        if COSMETIC_RE.search(line):
            continue

        candidate = None

        # 1. AdGuard 格式：||example.com^ 或 ||*.example.com^$options
        m = ADGUARD_RE.match(line)
        if m:
            raw = m.group(1)
            # 通配符规则 ||*.example.com^ → 保留父域 example.com
            if raw.startswith("*."):
                raw = raw[2:]
            candidate = normalize_domain(raw)

        # 2. dnsmasq 格式：address=/example.com/
        elif DNSMASQ_RE.match(line):
            m = DNSMASQ_RE.match(line)
            candidate = normalize_domain(m.group(1))

        # 3. Hosts 格式：0.0.0.0 example.com
        elif HOSTS_RE.match(line):
            m = HOSTS_RE.match(line)
            candidate = normalize_domain(m.group(1))

        # 4. 纯域名兜底（裸域名行）
        else:
            if '/' in line or line.startswith("http"):
                continue
            parts = line.split()
            if parts:
                cand = normalize_domain(parts[0])
                if DOMAIN_RE.match(cand):
                    candidate = cand

        if candidate and should_keep_domain(candidate):
            domains.add(candidate)

    return domains


def dedupe_subdomains(domains: Set[str]) -> List[str]:
    """
    子域名去冗余：若父域已在集合中则丢弃子域。
    按域名长度升序排列，短域名（父域）优先处理。
    """
    sorted_domains = sorted(domains, key=lambda x: (len(x), x))
    result = []
    domain_set = set(domains)

    for domain in sorted_domains:
        parts = domain.split('.')
        is_redundant = False
        for i in range(1, len(parts)):
            parent = '.'.join(parts[i:])
            if parent in domain_set and parent != domain:
                is_redundant = True
                break
        if not is_redundant:
            result.append(domain)

    return result


def generate_report(
    now_str: str,
    sources: List[str],
    source_counts: Dict,
    total_raw: int,
    custom_block_count: int,
    custom_allow_count: int,
    allow_removed: int,
    before_dedup: int,
    final_count: int,
    last_stats: Dict,
    srs_size_kb: float,
) -> str:
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


def run_self_test():
    """启动前自检，验证核心解析逻辑"""
    print("[*] 运行自检...")
    errors = []

    # AdGuard 普通规则
    r = parse_rules("||ads.example.com^")
    if "ads.example.com" not in r:
        errors.append("FAIL: ||ads.example.com^ 未被提取")

    # AdGuard 带选项规则
    r = parse_rules("||ads.example.com^$third-party")
    if "ads.example.com" not in r:
        errors.append("FAIL: ||ads.example.com^$third-party 未被提取")

    # AdGuard 通配符规则
    r = parse_rules("||*.ads.example.com^")
    if "ads.example.com" not in r:
        errors.append("FAIL: ||*.ads.example.com^ 未被提取")

    # Hosts 格式
    r = parse_rules("0.0.0.0 ads.example.com")
    if "ads.example.com" not in r:
        errors.append("FAIL: hosts 格式未被提取")

    # dnsmasq 格式
    r = parse_rules("address=/ads.example.com/")
    if "ads.example.com" not in r:
        errors.append("FAIL: dnsmasq 格式未被提取")

    # cosmetic 规则不应提取
    r = parse_rules("example.com##.ads")
    if "example.com" in r:
        errors.append("FAIL: cosmetic 规则被误提取")

    # 白名单精确匹配，子域不应被保护
    r = parse_rules("||ads.youtube.com^")
    if "ads.youtube.com" not in r:
        errors.append("FAIL: ads.youtube.com 被白名单误过滤（应保留）")

    # 公共后缀本身不应进入
    r = parse_rules("||com.cn^")
    if "com.cn" in r:
        errors.append("FAIL: com.cn 公共后缀被误收录")

    # .com.cn 域名不应被误删
    r = parse_rules("||adlog.vivo.com.cn^")
    if "adlog.vivo.com.cn" not in r:
        errors.append("FAIL: adlog.vivo.com.cn 被 PSL 误删")

    # URL 行不应提取
    r = parse_rules("https://ads.example.com/banner")
    if "ads.example.com" in r:
        errors.append("FAIL: URL 行被误提取")

    if errors:
        for e in errors:
            print("  " + e)
        print("[-] 自检未通过，请检查上述问题后再运行。")
        exit(1)
    else:
        print("[+] 自检全部通过")


def main():
    print("[*] 启动转换流程 (sing-box v1.13.x)")

    # 先加载公共后缀列表，因为自检依赖它
    load_public_suffix_list()
    if not PUBLIC_SUFFIXES:
        print("[-] 无法加载 Public Suffix List，任务终止。")
        exit(1)

    run_self_test()

    now = datetime.now(CST)
    now_str = now.strftime("%Y-%m-%d %H:%M CST")

    # 1. 下载并解析订阅
    sources = load_sources(SOURCE_FILE)
    all_domains: Set[str] = set()
    source_counts: Dict = {}

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
        print("[+] 自定义屏蔽追加: " + str(len(custom_block)) + " 个")
        all_domains |= custom_block
    else:
        print("[*] 未找到 " + BLOCK_FILE + " 或文件为空，跳过")

    # 3. 应用白名单（只向下保护子域，不向上保护父域）
    custom_allow = load_custom(ALLOW_FILE)
    allow_removed = 0
    if custom_allow:
        before = len(all_domains)
        all_domains = {
            d for d in all_domains
            if not any(d == a or d.endswith('.' + a) for a in custom_allow)
        }
        allow_removed = before - len(all_domains)
        print("[+] 白名单放行: 移除 " + str(allow_removed) + " 个域名")
    else:
        print("[*] 未找到 " + ALLOW_FILE + " 或文件为空，跳过")

    # 4. 子域名去冗余
    before_dedup = len(all_domains)
    print("[*] 去重前总计: " + str(before_dedup) + " 个域名")
    deduped = dedupe_subdomains(all_domains)
    final_count = len(deduped)
    print("[*] 子域名去冗余后: " + str(final_count) + " 个域名")

    # 5. 生成 JSON
    ruleset_json = {
        "version": RULESET_VERSION,
        "rules": [{"domain_suffix": sorted(set(deduped))}]
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
        print("[-] 错误: 系统中未找到 sing-box 命令")
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

    # 8. 持久化统计
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
