"""从 CHANGELOG.md 生成 GitHub Release 正文 (沿用既有发布模板)。

用法: python scripts/gen_release_notes.py <tag>
输出: ./release-notes.md

模板要点 (与 v0.0.4-beta-I 发布说明一致):
  - H1 标题 + 版本类型/版本号
  - [!提示] 引用块: 取该版本小节的「已知说明」条目
  - 更新日志扁平列表: 每条加类型标签 [ <Emoji> **<Type / 中文>** ]
  - 完整更新日志 compare 链接 + 反馈提示行

类型判定: 先按小节 (修复 -> Fix), 再按关键词 (安全 -> Sec, 重构 -> Refactor,
文档 -> Docs, 杂项关键词 -> Chore), 新增节默认 Feat, 改进节默认 Chore。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TAG_TYPE_PATTERNS = [
    (r"安全|白名单|SSRF|漏洞", ("🛡️", "Sec / 安全")),
    (r"重构", ("♻️", "Refactor / 重构")),
    (r"文档|CHANGELOG", ("📝", "Docs / 文档")),
    (r"更新检查|一键更新", ("✨", "Feat / 新增")),
    (r"版本号|对齐|依赖|下载源列表|杂项|构建|发布流程", ("⚙️", "Chore / 杂项")),
]

SECTION_DEFAULTS = {
    "新增": ("✨", "Feat / 新增"),
    "改进": ("⚙️", "Chore / 杂项"),
    "修复": ("🛠", "Fix / 修复"),
}

# 不参与更新日志列表的小节
SKIPPED_SECTIONS = {"已知说明"}

HEADER_TEST = "# HugoAura-Install {tag} 已发布 / 安装器测试版本发布"
HEADER_STABLE = "# HugoAura-Install {tag} 已发布 / 安装器正式版本发布"
FOOTER_FEEDBACK = (
    "### **如果您使用此版本发现了问题，请输入问题至问题，并附上图片或复现步骤**"
)


def classify(text: str, section: str) -> tuple[str, str]:
    if section == "新增":
        return SECTION_DEFAULTS["新增"]
    if section == "修复" or re.match(r"^修复", text):
        return SECTION_DEFAULTS["修复"]
    for pattern, tag in TAG_TYPE_PATTERNS:
        if re.search(pattern, text):
            return tag
    return SECTION_DEFAULTS["改进"]


def parse_section(changelog: str, tag: str) -> tuple[str, str, list[str]]:
    """返回 (下一个版本 tag, 正文文本, 已知说明条目)。"""
    pattern = rf"^## \[Rel\] {re.escape(tag)}\b.*?(?=^## |\Z)"
    m = re.search(pattern, changelog, re.M | re.S)
    if not m:
        raise SystemExit(f"CHANGELOG.md 中未找到版本小节: {tag}")
    block = m.group(0)

    nxt_m = re.search(r"^## \[Rel\] (\S+)", changelog[m.end():], re.M)
    prev_tag = nxt_m.group(1).rstrip(".") if nxt_m else ""

    known: list[str] = []
    km = re.search(r"### 已知说明\s*(.*?)(?=^### |\Z)", block, re.M | re.S)
    if km:
        known = [
            ln.lstrip("- ").strip()
            for ln in km.group(1).strip().splitlines()
            if ln.strip().startswith("- ")
        ]
    return prev_tag, block, known


def build_bullets(block: str) -> list[str]:
    bullets: list[str] = []
    section = ""
    for ln in block.splitlines():
        h = re.match(r"^### (\S+)", ln)
        if h:
            section = h.group(1)
            continue
        if section in SKIPPED_SECTIONS or not ln.strip().startswith("- "):
            continue
        text = ln.strip()[2:].strip()
        emoji, label = classify(text, section)
        m = re.match(r"^(.+?)：(.*)$", text, re.S)
        if m:
            name, desc = m.group(1).strip(), m.group(2).strip()
            bullets.append(f"- [ {emoji} **{label}** ] **{name}**：{desc}")
        else:
            bullets.append(f"- [ {emoji} **{label}** ] **{text}**")
    return bullets


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    if not tag:
        raise SystemExit("用法: python scripts/gen_release_notes.py <tag>")

    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    prev_tag, block, known = parse_section(changelog, tag)

    is_test = bool(re.search(r"beta|rc|alpha|pre", tag, re.I))
    header = (HEADER_TEST if is_test else HEADER_STABLE).format(tag=tag)
    version_type = "🧪 测试版" if is_test else "🚀 正式版"

    lines = [
        header,
        "",
        f"**版本类型： {version_type}**",
        f"**版本号：** `{tag}` (**{tag}**)",
        "",
    ]
    if known:
        lines.append("> [!提示]")
        for item in known:
            lines.append(f"> - {item}")
        lines.append("")
    lines += [
        "# 更新日志 / Changelog",
        "",
        f"**从** `{prev_tag or '首个版本'}` **之后**",
        "",
    ]
    lines += build_bullets(block)
    if prev_tag:
        lines += [
            "",
            f"**完整更新日志：** https://github.com/blingbling-bow/HugoAura-Install/compare/{prev_tag}...{tag}",
        ]
    lines += ["", FOOTER_FEEDBACK, ""]

    Path("release-notes.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"release-notes.md written ({len(lines)} lines)")


if __name__ == "__main__":
    main()
