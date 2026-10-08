"""Answer boxes for homework notebooks: mark where to answer, render answers in blue.

    python answer_box.py apply NOTEBOOK       # wrap every placeholder in an answer box (in place)
    python answer_box.py check NOTEBOOK       # list unanswered spots and broken tables
    python answer_box.py strip NOTEBOOK [OUT] # remove all styling (default OUT: *_plain.ipynb)

How to answer: replace the whole <mark>...</mark> with your answer and leave the
surrounding <div>/<span> alone. In a <div> box keep the blank line after <div ...>
and before </div>, otherwise markdown and math inside will not render.
"""

import json
import re
import sys
from pathlib import Path

BLUE = "#2f6fe0"
DIV_OPEN = f'<div style="color:{BLUE}; border-left:3px solid {BLUE}; padding-left:10px">'
DIV_CLOSE = "</div>"
SPAN_OPEN = f'<span style="color:{BLUE}">'
SPAN_CLOSE = "</span>"

# `[請填寫]`, [填寫], `[圖、評估指標…]` — brackets, optionally inside backticks.
PLACEHOLDER = re.compile(r"`\[[^\]`]+\]`|\[(?:請|填寫)[^\]]*\]")
BLANK = re.compile(r"_{3,}")
# Multiple-choice cells such as 符合／部分符合／不符合 (three or more options).
CHOICE = re.compile(r"^[^|`$\[\]]+(?:／[^|`$\[\]]+){2,}$")
LABEL_LINE = re.compile(r"^(\*\*[^*]+\*\*)\s*(.+)$")
MARK = re.compile(r"<mark>(.*?)</mark>")


def mark(text):
    return f"<mark>{text.strip('`')}</mark>"


def span(inner):
    return f"{SPAN_OPEN}{inner}{SPAN_CLOSE}"


def box(inner):
    return [DIV_OPEN, "", inner, "", DIV_CLOSE]


def split_row(line):
    """Split a markdown table row into cells, ignoring escaped pipes."""
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def is_table_row(line):
    return line.lstrip().startswith("|") and line.rstrip().endswith("|")


def is_separator(line):
    return is_table_row(line) and all(re.fullmatch(r":?-+:?", c) for c in split_row(line))


# ---------------------------------------------------------------- apply

def apply_table_row(line):
    if is_separator(line) or SPAN_OPEN in line:
        return line
    cells = split_row(line)
    has_placeholder = any(PLACEHOLDER.fullmatch(c) for c in cells)
    if not has_placeholder:
        return line
    out = []
    for c in cells:
        if PLACEHOLDER.fullmatch(c):
            c = span(mark(c))
        elif c == "":
            # Empty answer columns next to a placeholder are easy to miss.
            c = span(mark("[填寫]"))
        elif CHOICE.fullmatch(c):
            c = span(mark(c))
        out.append(c)
    return "| " + " | ".join(out) + " |"


def apply_line(line):
    """Return a list of output lines for one markdown line."""
    if SPAN_OPEN in line or line.strip() == DIV_OPEN:
        return [line]
    if is_table_row(line):
        return [apply_table_row(line)]
    if line.lstrip().startswith(">") and BLANK.search(line):
        return [BLANK.sub(lambda m: span(mark(m.group())), line)]
    stripped = line.strip()
    if PLACEHOLDER.fullmatch(stripped):
        return box(mark(stripped))
    m = LABEL_LINE.match(stripped)
    if m and PLACEHOLDER.fullmatch(m.group(2).strip()):
        label, ph = m.group(1), m.group(2).strip()
        if ph.strip("`") in ("[請填寫]", "[填寫]") and "回答" not in label:
            return [f"{label} {span(mark(ph))}"]  # short answer, e.g. **領域：**
        return [label, ""] + box(mark(ph))
    return [line]


def apply_cell(src):
    lines = src.split("\n")
    out = []
    for line in lines:
        out.extend(apply_line(line))
    return "\n".join(out)


# ---------------------------------------------------------------- strip

def strip_cell(src):
    src = MARK.sub(r"\1", src)
    src = re.sub(re.escape(SPAN_OPEN) + r"(.*?)" + re.escape(SPAN_CLOSE), r"\1", src)
    lines, out, in_box = src.split("\n"), [], False
    for line in lines:
        if line.strip() == DIV_OPEN:
            in_box = True
            continue
        if in_box and line.strip() == DIV_CLOSE:
            in_box = False
            continue
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


# ---------------------------------------------------------------- check

def heading_of(src):
    for line in src.split("\n"):
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def check(nb):
    unanswered, broken = [], []
    current = ""
    for i, cell in enumerate(nb["cells"]):
        src = "".join(cell["source"])
        if cell["cell_type"] != "markdown":
            continue
        current = heading_of(src) or current
        lines = src.split("\n")
        for j, line in enumerate(lines):
            for m in MARK.finditer(line):
                unanswered.append((i, current, m.group(1)))
        # A table whose rows have a different number of cells than its header
        # usually means a stray | inside an answer (use \lvert x \rvert for |x|).
        header = None
        for j, line in enumerate(lines):
            if not is_table_row(line):
                header = None
                continue
            n = len(split_row(line))
            if header is None:
                header = n
            elif n != header:
                broken.append((i, current, j, line.strip()))
    return unanswered, broken


def short(text, n=40):
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------- main

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(nb, path):
    Path(path).write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def set_source(cell, src):
    cell["source"] = src.splitlines(True)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("apply", "check", "strip"):
        sys.exit(__doc__)
    cmd, path = sys.argv[1], sys.argv[2]
    nb = load(path)

    if cmd == "apply":
        changed = 0
        for cell in nb["cells"]:
            if cell["cell_type"] != "markdown":
                continue
            src = "".join(cell["source"])
            new = apply_cell(src)
            if new != src:
                set_source(cell, new)
                changed += 1
        save(nb, path)
        print(f"apply: {changed} cells updated in {path}")

    elif cmd == "strip":
        out = sys.argv[3] if len(sys.argv) > 3 else str(Path(path).with_name(Path(path).stem + "_plain.ipynb"))
        for cell in nb["cells"]:
            if cell["cell_type"] == "markdown":
                set_source(cell, strip_cell("".join(cell["source"])))
        save(nb, out)
        print(f"strip: wrote {out}")

    else:
        unanswered, broken = check(nb)
        by_cell = {}
        for i, sec, text in unanswered:
            by_cell.setdefault((i, sec), []).append(text)
        for (i, sec), texts in by_cell.items():
            print(f"  cell {i:3d}  {len(texts):3d} left  {short(sec, 28):<28}  {short(texts[0])}")
        for i, sec, j, line in broken:
            print(f"  ⚠ cell {i:3d} line {j}: table column count mismatch (stray | ?)  {short(line, 60)}")
        todo = sum("TODO" in "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
        print(f"\n{len(unanswered)} unanswered, {len(broken)} broken table rows, {todo} code cells still mention TODO")


if __name__ == "__main__":
    main()
