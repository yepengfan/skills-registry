#!/usr/bin/env python3
"""Parse YAML frontmatter from markdown files and output JSON."""
import sys
import json
import re


def parse_frontmatter(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return None

    fm_text = match.group(1)

    try:
        import yaml

        return yaml.safe_load(fm_text)
    except ImportError:
        return _simple_parse(fm_text)


def _simple_parse(text):
    """Parse simple YAML frontmatter without PyYAML.

    Handles: scalar values, inline lists [a, b], and block lists (- item).
    """
    result = {}
    current_key = None
    current_list = None

    for line in text.split("\n"):
        line = line.rstrip()
        if not line:
            continue

        # List item (indented "- value")
        list_match = re.match(r"^\s+-\s+(.+)$", line)
        if list_match and current_key:
            if current_list is None:
                current_list = []
                result[current_key] = current_list
            current_list.append(list_match.group(1).strip())
            continue

        # Key: value pair
        kv_match = re.match(r"^(\w[\w-]*):\s*(.*)?$", line)
        if kv_match:
            current_key = kv_match.group(1)
            value = (kv_match.group(2) or "").strip()
            current_list = None

            if not value:
                continue

            # Inline list: [item1, item2]
            inline_list = re.match(r"^\[(.+)\]$", value)
            if inline_list:
                items = [
                    i.strip().strip("\"'") for i in inline_list.group(1).split(",")
                ]
                result[current_key] = items
            else:
                result[current_key] = value.strip("\"'")

    return result


REQUIRED_FIELDS = ["name", "description", "version", "author"]


def validate(data):
    if data is None:
        print("Error: No frontmatter found", file=sys.stderr)
        sys.exit(1)
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        print(f"Error: Missing required fields: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print("Usage: parse_frontmatter.py <file.md>", file=sys.stderr)
        sys.exit(1)

    data = parse_frontmatter(sys.argv[1])
    validate(data)
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
