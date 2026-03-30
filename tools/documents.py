import os
import glob as globlib
from datetime import datetime
import config


def _safe_path(filename):
    """Ensure the path stays within the documents directory."""
    base = os.path.realpath(config.DOCUMENTS_PATH)
    target = os.path.realpath(os.path.join(base, filename))
    if not target.startswith(base):
        raise ValueError("Access denied: path is outside the documents directory.")
    return target


def list_documents(path="", pattern="*"):
    """List documents in the documents directory."""
    base = _safe_path(path)
    if not os.path.isdir(base):
        return f"Directory not found: {path}"

    matches = globlib.glob(os.path.join(base, pattern))
    if not matches:
        return f"No files matching '{pattern}' in {path or 'documents root'}."

    results = []
    for filepath in sorted(matches):
        name = os.path.relpath(filepath, config.DOCUMENTS_PATH)
        stat = os.stat(filepath)
        size = stat.st_size
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        kind = "dir" if os.path.isdir(filepath) else "file"

        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"

        results.append(f"{'[DIR] ' if kind == 'dir' else ''}{name}  ({size_str}, modified {modified})")

    return "\n".join(results)


def read_document(filename, max_lines=100):
    """Read contents of a text document."""
    filepath = _safe_path(filename)

    if not os.path.isfile(filepath):
        return f"File not found: {filename}"

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    lines.append(f"\n... (truncated at {max_lines} lines)")
                    break
                lines.append(line)
        return "".join(lines)
    except Exception as e:
        return f"Error reading {filename}: {e}"


def search_documents(query, file_pattern="*"):
    """Search for text across documents."""
    base = config.DOCUMENTS_PATH
    if not os.path.isdir(base):
        return "Documents directory not found."

    matches = globlib.glob(os.path.join(base, "**", file_pattern), recursive=True)
    results = []

    for filepath in matches:
        if not os.path.isfile(filepath):
            continue
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, 1):
                    if query.lower() in line.lower():
                        name = os.path.relpath(filepath, base)
                        results.append(f"{name}:{line_num}: {line.strip()}")
                        if len(results) >= 50:
                            results.append("... (results truncated at 50 matches)")
                            return "\n".join(results)
        except Exception:
            continue

    if not results:
        return f"No matches found for '{query}'."
    return "\n".join(results)
