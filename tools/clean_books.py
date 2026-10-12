# -*- coding: utf-8 -*-
"""
把 Project Gutenberg 下载的原始 txt 清洗成适合阅读的干净文本。

处理内容：
  1. 剥离 Gutenberg 的头部说明与尾部 License（只保留正文）
  2. 繁体 -> 简体
  3. 统一换行、压缩连续空行
  4. 去掉行首全角空格缩进（阅读器自己做缩进排版更整齐）
  5. 输出 UTF-8 无 BOM
"""
import json
import re
import sys
from pathlib import Path

from opencc import OpenCC

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "raw_books"
OUT = ROOT / "books"

cc = OpenCC("t2s")

# Gutenberg 正文标记
START_RE = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^*]*\*\*\*", re.I)
END_RE = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^*]*\*\*\*", re.I)


def strip_gutenberg(text: str) -> str:
    m = START_RE.search(text)
    if m:
        text = text[m.end():]
    m = END_RE.search(text)
    if m:
        text = text[:m.start()]
    # 去掉残留的 Produced by / Transcriber 行
    text = re.sub(r"^\s*(Produced by|Transcriber|Credits?:)[^\n]*\n", "", text, flags=re.I | re.M)
    # 去掉残留的英文元数据行（Title: / Author: / Language: / Release date: 等）
    text = re.sub(
        r"^\s*(Title|Author|Language|Release date|Contents|Subject|Note|Original title)\s*:[^\n]*\n",
        "", text, flags=re.I | re.M,
    )
    return text


# 视为"一句话已说完"的结尾字符
SENT_END = set("。！？…!?；;")
# 结尾是引号/括号时，需要穿透它再看前一个字符
CLOSERS = set("”’』」》）】〕｝\"'")
# 正文行的缩进标记：行首 >= 4 个半角空格（原书用 4 空格或全角空格缩进正文）


def _ends_sentence(s: str) -> bool:
    """行尾是否是句末（跳过结尾的引号括号）"""
    i = len(s) - 1
    while i >= 0 and s[i] in CLOSERS:
        i -= 1
    return i >= 0 and s[i] in SENT_END


def _is_heading(content: str, indent: int, buf: str) -> bool:
    """判断这是不是一个独立标题行。

    标题特征：短、不含句末标点、且上一段已经收尾（或没有上一段）。
    正文残行的特征是「上一段还没说完」，会走续行逻辑。
    """
    if buf and not _ends_sentence(buf):
        return False          # 上一段没说完，这行更可能是正文续行
    if len(content) > 20:
        return False          # 太长，不像标题
    if any(c in content for c in "。！？…；，"):
        return False          # 含标点，是正文
    return True


def normalize(text: str) -> str:
    """清洗 + 把原书的排版硬换行重新合并成自然段落。

    原书结构：正文行带缩进，行间夹空行。
    段落边界主要由「行尾是否有句末标点」决定。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = []
    for ln in text.split("\n"):
        ln = ln.replace("\u3000", "     ").replace("\xa0", " ")
        stripped = ln.strip()
        indent = len(ln) - len(ln.lstrip(" "))
        lines.append((indent, stripped))

    merged: list[str] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf:
            merged.append(buf)
            buf = ""

    for indent, content in lines:
        if not content:
            continue

        # 标题行判定（排在正文逻辑之前）
        if _is_heading(content, indent, buf):
            flush()
            merged.append(content)
            continue

        if not buf:
            buf = content
            continue

        if _ends_sentence(buf):
            flush()
            buf = content
        else:
            buf += content

    flush()

    out = [ln for ln in merged if ln]
    text = "\n".join(out).strip()
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def title_from_filename(name: str) -> str:
    return name


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = []

    files = sorted(SRC.glob("*.txt"))
    if not files:
        print(f"[!] 在 {SRC} 没找到原始文本")
        sys.exit(1)

    for f in files:
        raw = f.read_text(encoding="utf-8", errors="ignore")
        body = strip_gutenberg(raw)
        body = cc.convert(body)
        body = normalize(body)

        if len(body) < 500:
            print(f"[skip] {f.name} 清洗后过短({len(body)}字)，可能不是正文")
            continue

        dest = OUT / f.name
        dest.write_text(body, encoding="utf-8", newline="\n")

        title = title_from_filename(f.stem)
        chars = len(re.sub(r"\s", "", body))
        index.append({
            "id": f.stem,
            "title": title,
            "file": f.name,
            "chars": chars,
        })
        print(f"[ok] {title:<8} 正文 {chars:>7} 字 -> {dest.name}")

    (OUT / "books.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n共 {len(index)} 本，索引写入 books/books.json")


if __name__ == "__main__":
    main()
