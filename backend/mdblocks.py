"""Shared markdown → block tokenizer (used by the document builders in tools.py and the Drive exporters in integrations.py)."""
import re


def md_blocks(md: str):
    for raw in md.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            yield ("blank", "")
        elif line.startswith("```"):
            yield ("fence", "")
        elif re.match(r"^#{1,3}\s", line):
            yield ("h%d" % len(re.match(r"^#+", line).group()), re.sub(r"^#+\s", "", line))
        elif re.match(r"^\s*[-*]\s", line):
            yield ("li", re.sub(r"^\s*[-*]\s", "", line))
        elif re.match(r"^\s*\d+\.\s", line):
            yield ("li", re.sub(r"^\s*", "", line))
        elif re.match(r"^\s*\|.*\|\s*$", line):
            if not re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
                yield ("row", [c.strip() for c in line.strip()[1:-1].split("|")])
        else:
            yield ("p", line)

