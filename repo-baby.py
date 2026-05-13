#!/usr/bin/env python3
"""
Repo Baby — Repository Map Generator

Generates a compact, ranked structural map of any codebase using
Tree-sitter for parsing and in-degree ranking for importance.

Supports 26 languages via Tree-sitter.

Usage:
    python3 repo-baby.py --path /path/to/repo [--scope subdir] [--token-budget 800]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Tree-sitter availability
# ---------------------------------------------------------------------------

_TS_PACK_AVAILABLE = False
try:
    from tree_sitter import Language, Parser, Node
    from tree_sitter_language_pack import get_language
    _TS_PACK_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Language configuration
# ---------------------------------------------------------------------------

# Map of file extension → language pack name for get_language()
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

# Map of file extension → tree-sitter Language object (lazy-loaded)
_PARSERS: Dict[str, Optional[Parser]] = {}

# ---------------------------------------------------------------------------
# Ignore rules
# ---------------------------------------------------------------------------

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


# Files to always skip (generated, lockfiles, etc.)
SKIP_FILE_PATTERNS = [
    re.compile(r"package-lock\.json$", re.IGNORECASE),
    re.compile(r"yarn\.lock$", re.IGNORECASE),
    re.compile(r"pnpm-lock\.yaml$", re.IGNORECASE),
    re.compile(r"\.min\.(js|css)$", re.IGNORECASE),
    re.compile(r"go\.sum$"),
    re.compile(r"Gemfile\.lock$"),
    re.compile(r"poetry\.lock$"),
    re.compile(r"uv\.lock$"),
    re.compile(r"\.d\.ts$"),  # Generated type declarations
]

MAX_FILE_SIZE = 500_000  # Skip files larger than 500KB (probably minified)
MAX_FILES = 500          # Safety cap on number of files to parse


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def git_tracked_files(repo_path: str) -> List[str]:
    """Return files tracked by git (respects .gitignore automatically)."""
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
    """Walk directory tree with manual ignore rules (no git needed)."""
    files: List[str] = []
    scope_path = Path(repo_path) / scope

    if not scope_path.exists():
        return files

    for root, dirs, filenames in os.walk(scope_path):
        # Prune ignored directories
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
    """Discover source files, preferring git when available."""
    # Try git first
    git_files = git_tracked_files(repo_path)
    if git_files:
        result = []
        for f in git_files:
            # Apply scope filter
            if scope != "." and not f.startswith(scope.rstrip("/") + "/") and f != scope.rstrip("/"):
                continue
            if _should_include_file(f):
                result.append(f)
        return result

    # Fallback to walking
    return walk_files(repo_path, scope)


# ---------------------------------------------------------------------------
# Tree-sitter parser loading
# ---------------------------------------------------------------------------

def get_parser(ext: str) -> Optional[Parser]:
    """Get or lazily create a Tree-sitter parser for the given extension."""
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


# ---------------------------------------------------------------------------
# Symbol extraction — Tree-sitter
# ---------------------------------------------------------------------------

def _walk_tree(node: "Node", ext: str) -> List[Tuple[str, str, int]]:
    """Walk a Tree-sitter AST and extract symbol definitions."""
    symbols: List[Tuple[str, str, int]] = []

    # Track current parent class for context
    parent_class: List[str] = []

    def visit(n: "Node", depth: int = 0):
        nonlocal parent_class
        if depth > 200 or n is None:
            return

        name_node = n.child_by_field_name("name")

        if name_node is not None:
            name = name_node.text.decode("utf-8", errors="replace")
            line = name_node.start_point[0] + 1

            # Classify by node type
            ntype = n.type
            if ntype == "function_definition":
                # Python: method if inside a class
                kind = "method" if parent_class else "function"
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append((kind, full_name, line))
            elif ntype == "class_definition":
                symbols.append(("class", name, line))
                parent_class.append(name)
            elif ntype == "function_declaration":
                # JS/TS: method if inside a class
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
                # JS/TS: include class context if available
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append(("method", full_name, line))
            elif ntype == "method_declaration":
                # Go: method declarations (func (recv Type) method())
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append(("method", full_name, line))
            elif ntype == "public_field_definition":
                # JS/TS class properties that are arrow functions
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append(("method", full_name, line))
            elif ntype == "type_alias_declaration":
                symbols.append(("type", name, line))
            elif ntype == "enum_declaration":
                symbols.append(("enum", name, line))
            # --- Go ---
            elif ntype == "type_spec":
                # Check children for struct_type vs interface_type
                has_interface = any(c.type == "interface_type" for c in n.children)
                kind = "interface" if has_interface else "struct"
                symbols.append((kind, name, line))
            # --- Rust ---
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
            # --- C / C++ ---
            elif ntype == "struct_specifier" and ext in (".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx"):
                symbols.append(("struct", name, line))
            elif ntype == "class_specifier" and ext in (".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".cs"):
                symbols.append(("class", name, line))
                parent_class.append(name)
            # --- Ruby ---
            elif ntype == "class" and ext in (".rb"):
                symbols.append(("class", name, line))
                parent_class.append(name)
            elif ntype == "module" and ext in (".rb"):
                symbols.append(("module", name, line))
                parent_class.append(name)
            elif ntype == "method" and ext in (".rb"):
                full_name = f"{parent_class[-1]}.{name}" if parent_class else name
                symbols.append(("method", full_name, line))

        # Terraform / HCL blocks: type + label
        if n.type == "block" and ext in (".tf", ".tfvars", ".hcl"):
            children = n.children
            if len(children) >= 1:
                block_type = children[0].text.decode("utf-8", errors="replace")
                # Find the first string literal as the name
                for child in children[1:]:
                    if child.type in ("string_lit", "template_string"):
                        raw = child.text.decode("utf-8", errors="replace")
                        # Strip quotes
                        name = raw.strip('"').strip("'")
                        line = child.start_point[0] + 1
                        kind = block_type  # e.g. "resource", "module", "variable"
                        symbols.append((kind, name, line))
                        break

        # Rust impl_item — no name field, target type is in child type_identifier
        if n.type == "impl_item" and ext == ".rs":
            for child in n.children:
                if child.type == "type_identifier":
                    impl_name = child.text.decode("utf-8", errors="replace")
                    line = child.start_point[0] + 1
                    symbols.append(("impl", impl_name, line))
                    parent_class.append(impl_name)
                    break

        # Track exiting scope (classes, interfaces, traits, impls, modules)
        # "class" and "module" are scoped to Ruby to avoid false matches
        # with keyword tokens in other languages (e.g., TypeScript "class" keyword).
        # Also check for a name field to distinguish declaration nodes from keyword tokens.
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


# ---------------------------------------------------------------------------
# Unified symbol extraction
# ---------------------------------------------------------------------------

class Symbol:
    """A code symbol with metadata for ranking."""
    __slots__ = ("name", "kind", "file", "line", "importance", "refs")

    def __init__(self, name: str, kind: str, file: str, line: int):
        self.name = name
        self.kind = kind
        self.file = file  # relative path
        self.line = line
        self.importance: float = 0.0
        self.refs: int = 0  # raw cross-file reference count before boosts


def _should_include_file(rel_path: str) -> bool:
    """Check if a file should be included in the map."""
    ext = Path(rel_path).suffix

    if ext not in SUPPORTED_EXTENSIONS:
        return False

    for pattern in SKIP_FILE_PATTERNS:
        if pattern.search(rel_path):
            return False

    return True


# Matches code identifiers: alphanumeric + underscore, at least 2 chars
_IDENTIFIER_RE = re.compile(r"[a-zA-Z_]\w+")



def _is_dunder_base(name: str) -> bool:
    """Check if the base name (after last dot) is a dunder like __init__."""
    base = name.rsplit(".", 1)[-1]
    return base.startswith("__") and base.endswith("__")
def _tokenize_identifiers(content: str):
    """Yield all identifier-like tokens from source code content."""
    # Yield each match — re.finditer is lazy in Python 3.7+
    for match in _IDENTIFIER_RE.finditer(content):
        yield match.group(0)


def extract_symbols(file_path: str, repo_path: str) -> List[Symbol]:
    """Extract symbols from a single file."""
    ext = Path(file_path).suffix
    full_path = os.path.join(repo_path, file_path)

    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except (OSError, IOError):
        return []

    # Skip oversized / minified files
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

    # Build Symbol objects with relative paths, filtering dunder noise
    rel_path = file_path  # already relative from discover_files()
    return [
        Symbol(name, kind, rel_path, line)
        for kind, name, line in raw
        if not _is_dunder_base(name)
    ]


# ---------------------------------------------------------------------------
# Dependency graph & ranking
# ---------------------------------------------------------------------------

def build_symbol_index(all_symbols: Dict[str, List[Symbol]]) -> Dict[str, List[Symbol]]:
    """Build a name → [Symbol] index for fast lookup."""
    index: Dict[str, List[Symbol]] = defaultdict(list)
    for symbols in all_symbols.values():
        for sym in symbols:
            index[sym.name].append(sym)
    return dict(index)


def compute_importance(all_symbols: Dict[str, List[Symbol]], repo_path: str) -> None:
    """Score each symbol by counting how many other files reference its name."""
    index = build_symbol_index(all_symbols)

    # Collect all symbol names once and build a set for O(1) lookup
    all_names = list(index.keys())
    if not all_names:
        return
    name_set = frozenset(all_names)

    # Count cross-file references for each symbol name
    ref_count: Dict[Tuple[str, str], int] = defaultdict(int)

    for file_path, symbols in all_symbols.items():
        full_path = os.path.join(repo_path, file_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except (OSError, IOError):
            continue

        # Tokenize content into words and intersect with symbol names
        # This is a single pass over the file — O(file_size)
        words_in_file: Set[str] = set()
        for word in _tokenize_identifiers(content):
            if word in name_set and word not in words_in_file:
                words_in_file.add(word)
                for sym in index[word]:
                    if sym.file != file_path:
                        ref_count[(sym.file, sym.name)] += 1

    # Assign importance scores
    for file_path, symbols in all_symbols.items():
        is_test = "/test" in file_path or "/tests" in file_path or "/__tests__" in file_path or file_path.startswith("test_")

        for sym in symbols:
            score = float(ref_count.get((sym.file, sym.name), 0))
            sym.refs = int(score)  # store raw count before boosts

            # Boost for central structural types
            if sym.kind in ("class", "interface"):
                score *= 1.5
            elif sym.kind in ("resource", "module", "data"):
                score *= 2.0
            elif sym.kind == "key":
                score = -1.0  # YAML/JSON keys are noise — sink to bottom

            # Boost common entry points
            base_name = sym.name.rsplit(".", 1)[-1]  # Strip class prefix like "App."
            if base_name in ("main", "index", "App", "Server",
                             "setup", "configure", "create_app", "handler"):
                score += 5.0

            # Demote test files
            if is_test or base_name.startswith("test_") or base_name.startswith("it("):
                score *= 0.05

            sym.importance = score


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_map(all_symbols: Dict[str, List[Symbol]], token_budget: int) -> str:
    """Format the ranked repo map as a tree, respecting token budget."""
    if not all_symbols:
        return "# No symbols found"

    lines: List[str] = []

    # Sort files by total importance (descending)
    file_scores: List[Tuple[str, float, List[Symbol]]] = []
    for file_path, symbols in all_symbols.items():
        if not symbols:
            continue
        total = sum(s.importance for s in symbols)
        file_scores.append((file_path, total, symbols))

    file_scores.sort(key=lambda x: (-x[1], x[0].startswith("tests/") or x[0].startswith("test_"), x[0]))

    # Approximate token counting (rough: 1 token ≈ 4 chars)
    char_budget = token_budget * 4
    current_chars = 0

    for file_path, _score, symbols in file_scores:
        # Sort symbols within file by importance
        symbols.sort(key=lambda s: (-s.importance, s.line))

        header = f"- {file_path}:"
        if current_chars + len(header) > char_budget:
            break

        lines.append(header)
        current_chars += len(header) + 1  # +1 for newline

        # Limit symbols per file to keep map compact, deduplicate same name+kind
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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

    # 1. Discover files
    files = discover_files(repo_path, args.scope)
    if not files:
        print("# No source files found")
        sys.exit(0)

    # Cap to avoid runaway parsing
    files = files[:MAX_FILES]

    # 2. Extract symbols
    all_symbols: Dict[str, List[Symbol]] = {}
    for rel_path in files:
        symbols = extract_symbols(rel_path, repo_path)
        if symbols:
            all_symbols[rel_path] = symbols

    if not all_symbols:
        print("# No symbols found in source files")
        sys.exit(0)

    # 3. Compute importance scores
    compute_importance(all_symbols, repo_path)

    # 4. Format and output
    output = format_map(all_symbols, args.token_budget)
    print(output)


if __name__ == "__main__":
    main()
