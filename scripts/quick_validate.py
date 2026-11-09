#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能结构校验器（官方 quick_validate.py，仅做最小校验）

检查 SKILL.md 是否存在、frontmatter 是否合法、name/description 是否合规。

用法:
    python3 quick_validate.py <skill_directory>

需要 PyYAML；若环境没有 yaml，脚本会退化为内置的极简解析。
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def _minimal_frontmatter_parse(text):
    """无 PyYAML 时的极简解析：只取顶层 key: value。"""
    data = {}
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def validate_skill(skill_path):
    skill_path = Path(skill_path).resolve()

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    content = skill_md.read_text(encoding="utf-8", errors="replace")
    if not content.startswith("---"):
        return False, "No YAML frontmatter found"

    match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter_text = match.group(1)

    if yaml is not None:
        try:
            frontmatter = yaml.safe_load(frontmatter_text)
            if not isinstance(frontmatter, dict):
                return False, "Frontmatter must be a YAML dictionary"
        except Exception as e:
            return False, f"Invalid YAML in frontmatter: {e}"
    else:
        frontmatter = _minimal_frontmatter_parse(frontmatter_text)

    ALLOWED_PROPERTIES = {"name", "description", "license", "allowed-tools", "metadata"}
    unexpected = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected:
        return False, (
            f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected))}. "
            f"Allowed properties are: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    if "name" not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if "description" not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if name:
        if not re.match(r"^[a-z0-9-]+$", name):
            return False, f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)"
        if name.startswith("-") or name.endswith("-") or "--" in name:
            return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
        if len(name) > 64:
            return False, f"Name is too long ({len(name)} characters). Maximum is 64 characters."

    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if description:
        if "<" in description or ">" in description:
            return False, "Description cannot contain angle brackets (< or >)"
        if len(description) > 1024:
            return False, f"Description is too long ({len(description)} characters). Maximum is 1024 characters."

    # 附加检查：目录名与 name 是否一致
    if name and skill_path.name != name:
        return False, f"Directory name '{skill_path.name}' does not match frontmatter name '{name}'"

    # 附加检查：正文行数
    body_lines = content.count("\n")
    warn = ""
    if body_lines > 500:
        warn = f" (warning: SKILL.md has {body_lines} lines, recommended under 500)"

    return True, f"Skill is valid!{warn}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
