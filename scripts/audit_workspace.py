#!/usr/bin/env python3
"""Audit a five-file debate workspace for mechanical consistency risks."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile


REQUIRED_PREFIXES = ("01-", "02-", "03-", "04-", "05-")
PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}|_待填写_|【待填写】")
DECLARED_ID_RE = re.compile(r"(?:^|\s)(?:ID|T-ID)\s*[：:]\s*([DCAOEBT]-\d+)\b", re.I)
NUMBER_CLAIM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|亿元|万元|万人|人|项|倍|年|个月)")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", help="Workspace directory")
    parser.add_argument("--cpm", type=int, default=320, help="Estimated spoken units per minute")
    parser.add_argument("--strict", action="store_true", help="Return nonzero when warnings exist")
    return parser.parse_args()


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(namespace + "p"):
        paragraphs.append("".join(node.text or "" for node in paragraph.iter(namespace + "t")))
    return "\n".join(paragraphs)


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return read_docx(path)
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_paragraph(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


def spoken_units(text: str) -> int:
    return len(CJK_RE.findall(text)) + len(WORD_RE.findall(text))


def timed_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    results: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(#{1,6})\s+(.+)$", lines[index])
        if not match or "限时" not in match.group(2):
            index += 1
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        body: list[str] = []
        index += 1
        while index < len(lines):
            next_heading = re.match(r"^(#{1,6})\s+", lines[index])
            if next_heading and len(next_heading.group(1)) <= level:
                break
            body.append(lines[index])
            index += 1
        results.append((title, "\n".join(body)))
    return results


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        print(f"Workspace is not a directory: {workspace}", file=sys.stderr)
        return 2

    files = sorted(
        [p for p in workspace.iterdir() if p.is_file() and p.suffix.lower() in {".md", ".txt", ".docx"}],
        key=lambda p: p.name,
    )
    errors: list[str] = []
    warnings: list[str] = []
    texts: dict[Path, str] = {}

    for prefix in REQUIRED_PREFIXES:
        if not any(path.name.startswith(prefix) for path in files):
            errors.append(f"缺少以 {prefix} 开头的工作文件")

    declarations: dict[str, list[str]] = defaultdict(list)
    paragraphs: dict[str, list[str]] = defaultdict(list)
    placeholders: dict[str, list[int]] = defaultdict(list)
    number_claims: dict[str, list[int]] = defaultdict(list)
    timing: list[str] = []

    for path in files:
        try:
            text = read_text(path)
        except Exception as exc:
            errors.append(f"无法读取 {path.name}: {exc}")
            continue
        texts[path] = text
        for line_no, line in enumerate(text.splitlines(), 1):
            if PLACEHOLDER_RE.search(line):
                placeholders[path.name].append(line_no)
            if NUMBER_CLAIM_RE.search(line) and "待核验" not in line and "http://" not in line and "https://" not in line:
                number_claims[path.name].append(line_no)
            for match in DECLARED_ID_RE.finditer(line):
                declarations[match.group(1).upper()].append(f"{path.name}:{line_no}")
        for raw in re.split(r"\n\s*\n", text):
            if "辩题：" in raw and "持方：" in raw and "建档日期：" in raw:
                continue
            normalized = normalize_paragraph(raw)
            if len(normalized) >= 35 and not PLACEHOLDER_RE.search(raw):
                paragraphs[normalized].append(path.name)
        for title, body in timed_sections(text):
            units = spoken_units(body)
            minutes = units / max(args.cpm, 1)
            timing.append(f"{path.name} / {title}: {units} 单位，约 {minutes:.2f} 分钟（{args.cpm}/分钟）")

    for item_id, locations in sorted(declarations.items()):
        if len(locations) > 1:
            errors.append(f"战术 ID {item_id} 被重复声明：{', '.join(locations)}")
    for name, line_numbers in sorted(placeholders.items()):
        preview = "、".join(str(number) for number in line_numbers[:6])
        suffix = "等" if len(line_numbers) > 6 else ""
        warnings.append(f"{name} 有 {len(line_numbers)} 处待填写项（行 {preview}{suffix}）")
    for name, line_numbers in sorted(number_claims.items()):
        preview = "、".join(str(number) for number in line_numbers[:6])
        suffix = "等" if len(line_numbers) > 6 else ""
        warnings.append(f"{name} 有 {len(line_numbers)} 处数字主张可能缺少来源或【待核验】标记（行 {preview}{suffix}）")
    for _, names in paragraphs.items():
        unique_names = sorted(set(names))
        if len(unique_names) > 1:
            warnings.append(f"跨文件存在较长重复段落：{', '.join(unique_names)}")

    print("# 工作区机械检查")
    print(f"目录：{workspace}")
    print(f"文件：{len(files)}")
    print("\n## 限时段落估算")
    if timing:
        for item in timing:
            print(f"- {item}")
    else:
        print("- 未发现标题含“限时”的段落")
    print("\n## 错误")
    if errors:
        for item in errors:
            print(f"- {item}")
    else:
        print("- 无")
    print("\n## 提醒")
    if warnings:
        for item in warnings:
            print(f"- {item}")
    else:
        print("- 无")
    print("\n注：字数、重复和数字检查是机械提示，必须结合赛制与语境复核。")

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
