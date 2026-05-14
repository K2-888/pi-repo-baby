#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_TS_PACK_AVAILABLE = False
try:
    from tree_sitter import Language, Parser, Node
    from tree_sitter_language_pack import get_language
    _TS_PACK_AVAILABLE = True
except ImportError:
    pass

_EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sc": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".lua": "lua",
    ".tf": "hcl",
    ".tfvars": "hcl",
    ".hcl": "hcl",
}

_PARSERS: Dict[str, Optional[Parser]] = {}

IGNORE_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "dist", "build", "target", ".terraform", ".idea", ".vscode",
    "vendor", "bin", "obj", "out", ".next", ".nuxt", ".cache",
    "coverage", "htmlcov", ".tox", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".hypothesis", ".hg", ".svn", "site-packages",
})

SUPPORTED_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".tsx",
    ".go", ".rs", ".rb", ".java",
    ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx",
    ".cs", ".php", ".kt", ".kts", ".swift",
    ".scala", ".sc", ".sh", ".bash", ".sql", ".lua",
    ".tf", ".tfvars", ".hcl",
})

SKIP_FILE_PATTERNS = [
    re.compile(r"package-lock\.json$", re.IGNORECASE),
    re.compile(r"yarn\.lock$", re.IGNORECASE),
    re.compile(r"pnpm-lock\.yaml$", re.IGNORECASE),
    re.compile(r"\.min\.(js|css)$", re.IGNORECASE),
    re.compile(r"go\.sum$"),
    re.compile(r"Gemfile\.lock$"),
    re.compile(r"poetry\.lock$"),
    re.compile(r"uv\.lock$"),
    re.compile(r"\.d\.ts$"),
]

MAX_FILE_SIZE = 500_000
MAX_FILES = 500


def git_tracked_files(repo_path: str) -> List[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [f for f in result.stdout.strip().split("\n") if f]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return []


def walk_files(repo_path: str, scope: str = ".") -> List[str]:
    files: List[str] = []
    scope_path = Path(repo_path) / scope

    if not scope_path.exists():
        return files

    for root, dirs, filenames in os.walk(scope_path):
        dirs[:] = sorted(
            d for d in dirs
            if d not in IGNORE_DIRS and not d.startswith(".")
        )

        for filename in filenames:
            if filename.startswith("."):
                continue

            full_path = Path(root) / filename
            rel_path = str(full_path.relative_to(repo_path))

            if not _should_include_file(rel_path):
                continue

            files.append(rel_path)

    return files


def discover_files(repo_path: str, scope: str = ".") -> List[str]:
    git_files = git_tracked_files(repo_path)
    if git_files:
        result = []
        for f in git_files:
            if scope != "." and not f.startswith(scope.rstrip("/") + "/") and f != scope.rstrip("/"):
                continue
            if _should_include_file(f):
                result.append(f)
        return result

    return walk_files(repo_path, scope)


def get_parser(ext: str) -> Optional[Parser]:
    if not _TS_PACK_AVAILABLE:
        return None

    if ext in _PARSERS:
        return _PARSERS[ext]

    parser: Optional[Parser] = None
    lang_name = _EXT_TO_LANG.get(ext)

    if lang_name:
        try:
            lang = get_language(lang_name)
            parser = Parser(lang)
        except Exception as e:
            print(f"[repo-baby] Could not load parser for {ext} ({lang_name}): {e}", file=sys.stderr)
            parser = None

    _PARSERS[ext] = parser
    return parser


def _walk_tree(node: "Node", ext: str) -> List[Tuple[str, str, int]]:
    symbols: List[Tuple[str, str, int]] = []
    parent_class: List[str] = []

    def visit(n: "Node", depth: int = 0):
        nonlocal parent_class
        if depth > 200 or n is None:
            return

        name_node = n.child_by_field_name("name")

        if name_node is not None:
            name = name_node.text.decode("utf-8", errors="replace")
            line = name_node.start_point[0] + 1

            ntype = n.type
            if ntype == "function_definition":
                kind = "method" if parent_class else "function"
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append((kind, full_name, line))
            elif ntype == "class_definition":
                symbols.append(("class", name, line))
                parent_class.append(name)
            elif ntype == "function_declaration":
                kind = "method" if parent_class else "function"
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append((kind, full_name, line))
            elif ntype == "class_declaration":
                symbols.append(("class", name, line))
                parent_class.append(name)
            elif ntype == "interface_declaration":
                symbols.append(("interface", name, line))
                parent_class.append(name)
            elif ntype == "method_definition":
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append(("method", full_name, line))
            elif ntype == "method_declaration":
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append(("method", full_name, line))
            elif ntype == "public_field_definition":
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append(("method", full_name, line))
            elif ntype == "type_alias_declaration":
                symbols.append(("type", name, line))
            elif ntype == "enum_declaration":
                symbols.append(("enum", name, line))
            elif ntype == "type_spec":
                has_interface = any(c.type == "interface_type" for c in n.children)
                kind = "interface" if has_interface else "struct"
                symbols.append((kind, name, line))
            elif ntype == "function_item":
                kind = "method" if parent_class else "function"
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append((kind, full_name, line))
            elif ntype == "struct_item":
                symbols.append(("struct", name, line))
            elif ntype == "trait_item":
                symbols.append(("trait", name, line))
                parent_class.append(name)
            elif ntype == "enum_item":
                symbols.append(("enum", name, line))
            elif ntype == "struct_specifier" and ext in (".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx"):
                symbols.append(("struct", name, line))
            elif ntype == "class_specifier" and ext in (".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".cs"):
                symbols.append(("class", name, line))
                parent_class.append(name)
            elif ntype == "class" and ext in (".rb"):
                symbols.append(("class", name, line))
                parent_class.append(name)
            elif ntype == "module" and ext in (".rb"):
                symbols.append(("module", name, line))
                parent_class.append(name)
            elif ntype == "method" and ext in (".rb"):
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append(("method", full_name, line))

        if n.type == "block" and ext in (".tf", ".tfvars", ".hcl"):
            children = n.children
            if len(children) >= 1:
                block_type = children[0].text.decode("utf-8", errors="replace")
                for child in children[1:]:
                    if child.type in ("string_lit", "template_string"):
                        raw = child.text.decode("utf-8", errors="replace")
                        name = raw.strip('"').strip("'")
                        line = child.start_point[0] + 1
                        kind = block_type
                        symbols.append((kind, name, line))
                        break

        if n.type == "impl_item" and ext == ".rs":
            for child in n.children:
                if child.type == "type_identifier":
                    impl_name = child.text.decode("utf-8", errors="replace")
                    line = child.start_point[0] + 1
                    symbols.append(("impl", impl_name, line))
                    parent_class.append(impl_name)
                    break

        _has_name = n.child_by_field_name("name") is not None
        entering_scope = (
            n.type in (
                "class_definition", "class_declaration", "interface_declaration",
                "impl_item", "trait_item", "class_specifier",
            )
            or (n.type == "class" and ext in (".rb",) and _has_name)
            or (n.type == "module" and ext in (".rb",) and _has_name)
        )

        for child in n.children:
            visit(child, depth + 1)

        if entering_scope and parent_class:
            parent_class.pop()

    visit(node)
    return symbols


class Symbol:
    __slots__ = ("name", "kind", "file", "line", "importance", "refs")

    def __init__(self, name: str, kind: str, file: str, line: int):
        self.name = name
        self.kind = kind
        self.file = file
        self.line = line
        self.importance: float = 0.0
        self.refs: int = 0


def _should_include_file(rel_path: str) -> bool:
    ext = Path(rel_path).suffix

    if ext not in SUPPORTED_EXTENSIONS:
        return False

    for pattern in SKIP_FILE_PATTERNS:
        if pattern.search(rel_path):
            return False

    return True


_IDENTIFIER_RE = re.compile(r"[a-zA-Z_]\w+")


def _is_dunder_base(name: str) -> bool:
    base = name.rsplit(".", 1)[-1]
    return base.startswith("__") and base.endswith("__")


def _tokenize_identifiers(content: str):
    for match in _IDENTIFIER_RE.finditer(content):
        yield match.group(0)


def extract_symbols(file_path: str, repo_path: str) -> List[Symbol]:
    ext = Path(file_path).suffix
    full_path = os.path.join(repo_path, file_path)

    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except (OSError, IOError):
        return []

    if len(content) > MAX_FILE_SIZE:
        return []
    if len(content) > 10_000 and content.count("\n") < 10:
        return []

    parser = get_parser(ext)
    if parser is None:
        return []

    raw: List[Tuple[str, str, int]] = []
    try:
        tree = parser.parse(bytes(content, "utf-8"))
        raw = _walk_tree(tree.root_node, ext)
    except Exception as e:
        print(f"[repo-baby] tree-sitter error on {file_path}: {e}", file=sys.stderr)
        return []

    rel_path = file_path
    return [
        Symbol(name, kind, rel_path, line)
        for kind, name, line in raw
        if not _is_dunder_base(name)
    ]


def build_symbol_index(all_symbols: Dict[str, List[Symbol]]) -> Dict[str, List[Symbol]]:
    index: Dict[str, List[Symbol]] = defaultdict(list)
    for symbols in all_symbols.values():
        for sym in symbols:
            index[sym.name].append(sym)
    return dict(index)


def compute_importance(all_symbols: Dict[str, List[Symbol]], repo_path: str) -> None:
    index = build_symbol_index(all_symbols)

    all_names = list(index.keys())
    if not all_names:
        return
    name_set = frozenset(all_names)

    ref_count: Dict[Tuple[str, str], int] = defaultdict(int)

    for file_path, symbols in all_symbols.items():
        full_path = os.path.join(repo_path, file_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except (OSError, IOError):
            continue

        words_in_file: Set[str] = set()
        for word in _tokenize_identifiers(content):
            if word in name_set and word not in words_in_file:
                words_in_file.add(word)
                for sym in index[word]:
                    if sym.file != file_path:
                        ref_count[(sym.file, sym.name)] += 1

    for file_path, symbols in all_symbols.items():
        is_test = "/test" in file_path or "/tests" in file_path or "/__tests__" in file_path or file_path.startswith("test_")

        for sym in symbols:
            score = float(ref_count.get((sym.file, sym.name), 0))
            sym.refs = int(score)

            if sym.kind in ("class", "interface"):
                score *= 1.5
            elif sym.kind in ("resource", "module", "data"):
                score *= 2.0
            elif sym.kind == "key":
                score = -1.0

            base_name = sym.name.rsplit(".", 1)[-1]
            if base_name in ("main", "index", "App", "Server",
                             "setup", "configure", "create_app", "handler"):
                score += 5.0

            if is_test or base_name.startswith("test_") or base_name.startswith("it("):
                score *= 0.05

            sym.importance = score


def format_map(all_symbols: Dict[str, List[Symbol]], token_budget: int) -> str:
    if not all_symbols:
        return "# No symbols found"

    lines: List[str] = []

    file_scores: List[Tuple[str, float, List[Symbol]]] = []
    for file_path, symbols in all_symbols.items():
        if not symbols:
            continue
        total = sum(s.importance for s in symbols)
        file_scores.append((file_path, total, symbols))

    file_scores.sort(key=lambda x: (-x[1], x[0].startswith("tests/") or x[0].startswith("test_"), x[0]))

    char_budget = token_budget * 4
    current_chars = 0

    for file_path, _score, symbols in file_scores:
        symbols.sort(key=lambda s: (-s.importance, s.line))

        header = f"- {file_path}:"
        if current_chars + len(header) > char_budget:
            break

        lines.append(header)
        current_chars += len(header) + 1

        seen: Set[Tuple[str, str]] = set()
        for sym in symbols[:30]:
            key = (sym.kind, sym.name)
            if key in seen:
                continue
            seen.add(key)

            line_str = f"  {sym.kind} {sym.name} (line {sym.line})"
            if sym.refs > 0:
                line_str += f"  ← {sym.refs} files"

            if current_chars + len(line_str) > char_budget:
                break

            lines.append(line_str)
            current_chars += len(line_str) + 1

        if current_chars >= char_budget:
            break

    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Repo Baby — repository map generator")
    ap.add_argument("--path", required=True, help="Path to repository root")
    ap.add_argument("--scope", default=".", help="Limit to a subdirectory (default: .)")
    ap.add_argument("--token-budget", type=int, default=800,
                    help="Approximate token budget for the output (default: 800)")
    args = ap.parse_args()

    repo_path = os.path.abspath(args.path)

    if not os.path.isdir(repo_path):
        print(f"Error: {repo_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    files = discover_files(repo_path, args.scope)
    if not files:
        print("# No source files found")
        sys.exit(0)

    files = files[:MAX_FILES]

    all_symbols: Dict[str, List[Symbol]] = {}
    for rel_path in files:
        symbols = extract_symbols(rel_path, repo_path)
        if symbols:
            all_symbols[rel_path] = symbols

    if not all_symbols:
        print("# No symbols found in source files")
        sys.exit(0)

    compute_importance(all_symbols, repo_path)

    output = format_map(all_symbols, args.token_budget)
    print(output)


if __name__ == "__main__":
    main()
