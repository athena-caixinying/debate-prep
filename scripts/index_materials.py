#!/usr/bin/env python3
"""Build a metadata-only Markdown index for a debate-material directory."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile


SUPPORTED = {".docx", ".pdf", ".md", ".txt"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Material root directory")
    parser.add_argument("--output", required=True, help="Markdown index path")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Top-level relative folder to exclude; repeat as needed",
    )
    return parser.parse_args()


def classify(path: Path) -> str:
    text = "/".join(path.parts).lower()
    name = path.stem.lower()
    if any(k in text for k in ("tips", "小册子", "知识点", "模版", "模板")):
        return "方法论/模板"
    if any(k in name for k in ("赛评", "复盘")):
        return "赛评/复盘"
    if any(k in name for k in ("讨论", "会议", "待讨论")):
        return "讨论记录"
    if any(k in name for k in ("质询", "接质", "攻防", "战场", "防")):
        return "攻防"
    if any(k in name for k in ("数据", "例子", "举例", "实例", "标准", "红线", "资料")):
        return "证据资料"
    if any(k in name for k in ("四辩", "结辩", "总结陈词")):
        return "四辩/结辩"
    if "三辩" in name:
        return "三辩"
    if "二辩" in name:
        return "二辩"
    if any(k in name for k in ("一辩", "立论")):
        return "一辩/立论"
    if any(k in name for k in ("思路", "深度挖掘", "核心")):
        return "框架/思路"
    return "综合材料"


def version_label(path: Path) -> str:
    name = path.stem
    for token in ("终稿", "终", "初稿", "大纲", "改", "ai", "AI"):
        if token in name:
            return token.lower()
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", name)
    return match.group(1) if match else "-"


def docx_stats(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        root = ET.fromstring(xml)
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        texts = [node.text or "" for node in root.iter(namespace + "t")]
        paragraphs = sum(1 for _ in root.iter(namespace + "p"))
        return str(paragraphs), str(len("".join(texts)))
    except Exception:
        return "?", "?"


def pdf_stats(path: Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore

        return str(len(PdfReader(str(path)).pages)), "-"
    except Exception:
        return "?", "-"


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    excluded = {item.casefold() for item in args.exclude}

    if not root.is_dir():
        print(f"Material root is not a directory: {root}", file=sys.stderr)
        return 2

    rows: list[dict[str, str]] = []
    for path in sorted(root.rglob("*"), key=lambda p: str(p).casefold()):
        if not path.is_file() or path.name.startswith("~$"):
            continue
        if path.suffix.lower() not in SUPPORTED:
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0].casefold() in excluded:
            continue
        if path.resolve() == output:
            continue
        if path.suffix.lower() == ".docx":
            pages_or_paras, chars = docx_stats(path)
            metric = f"{pages_or_paras} 段/{chars} 字"
        elif path.suffix.lower() == ".pdf":
            pages, _ = pdf_stats(path)
            metric = f"{pages} 页"
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            metric = f"{len(text)} 字"
        rows.append(
            {
                "topic": rel.parts[0] if len(rel.parts) > 1 else "根目录",
                "type": classify(rel),
                "version": version_label(rel),
                "format": path.suffix.lower().lstrip("."),
                "metric": metric,
                "path": rel.as_posix(),
            }
        )

    type_counts = Counter(row["type"] for row in rows)
    format_counts = Counter(row["format"] for row in rows)
    lines = [
        "# 历史辩论材料索引",
        "",
        "> 本索引只记录用户提供材料的文件信息。具体数据、观点、作者身份和个人风格均需另行核验。",
        "",
        f"- 材料根目录：`{root}`",
        f"- 收录文件：{len(rows)}",
        "- 格式统计：" + "，".join(f"{k} {v}" for k, v in sorted(format_counts.items())),
        "- 类型统计：" + "，".join(f"{k} {v}" for k, v in sorted(type_counts.items())),
        "",
        "| 主题/目录 | 材料类型 | 版本线索 | 格式 | 规模 | 相对路径 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(escape_cell(row[key]) for key in ("topic", "type", "version", "format", "metric", "path")) + " |"
        )
    lines.extend(
        [
            "",
            "## 使用规则",
            "",
            "- 先按材料类型和赛题目录定位，再读取少量相关原文。",
            "- 终稿优先用于研究团队最终口径；讨论记录用于理解思路演化；方法论文件只作为可检验的经验。",
            "- 不把历史材料中的精确数据直接复制到新比赛，必须重新查源。",
            "- 不从未标注作者的团队文件推断用户个人风格。",
            "",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Indexed {len(rows)} files -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
