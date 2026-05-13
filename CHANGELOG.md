# Changelog

All notable changes to Repo Baby follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) formatting.

## [2.3.0] — 2026-05-13

### Changed
- **Single-package migration** — replaced 27 individual `tree-sitter-*` grammar
  packages with `tree-sitter-language-pack==0.13.0`. 5 pip packages instead of 27.
  Zero compilation on target — single prebuilt wheel (~20 MB).
- **`install-deps` no longer destroys venv** — removed `--clear` flag. Only creates
  venv if it doesn't exist. Pip verify-skips already-installed packages.
- **`ensureDeps` skip-probe optimization** — if `venv/bin/python3` exists from a
  previous install, skips the `pi.exec` import probe entirely (cached).
- **TSX fix** — `.tsx` now maps to `"tsx"` (separate TSX binding) instead of
  sharing the TypeScript grammar.

### Added
- **Termux/Android support** — `install-deps` pre-installs `tree-sitter-c-sharp`
  before the language pack, working around the `parser.h` build failure on Termux.
  Confirmed on Android 11/aarch64, Python 3.12.

### Fixed
- **`/repo-baby off` toggle guard** — `explore_codebase` now properly throws when
  the toggle is off (was previously missing from `execute()`).
- **Doctor catch** — now reports `err.message` instead of swallowing root cause
  with a generic "not found or broken" message.
- **11 dead parser mappings** removed (YAML, JSON, HTML, CSS, TOML, Elixir,
  Haskell, Markdown) — already excluded from file discovery but left in
  `TS_LANGUAGE_MODULES`.
- **YAML/JSON `_walk_tree` handlers** removed — dead code since those formats
  aren't discovered.
- **`_tokenize_identifiers` return type** — removed bogus `"re.Iterator[str]"`.
- **`__init__` from boost list** — removed. Already caught by dunder filter,
  making the boost unreachable.

## [2.2.0] — 2026-05-11

### Added
- **`promptSnippet`** — one-line tool description in the agent's `Available tools:` list
- **`promptGuidelines`** — three behavioral rules in the `Guidelines:` section telling
  the agent when and why to call `explore_codebase`
- **Mid-turn steer nudge** — after the agent chains 2+ `ls`/`fd`/`find`/`rg` exploration
  commands without using `explore_codebase`, a reminder message is injected via
  `pi.sendMessage()`. Tracks via `tool_call` + `tool_execution_end` hooks.
- **Reference counts in output** — symbols now show `← 104 files` inline so the
  agent can see *why* something ranks high
- **Dunder filter** — `__init__`, `__str__`, `__repr__`, and other dunder methods
  are excluded from output
- **Same-file deduplication** — symbols with identical kind + name in the same file
  appear once (first occurrence by line number)

### Changed
- **Tool renamed:** `get_repo_map` → `explore_codebase`
- **Tool `description` rewritten** — directive language ("Call this FIRST") replaces
  passive suggestions
- **Test demotion:** 0.3× → 0.05× — test files now rank below production code
- **Symbols per file:** 20 → 30 to compensate for dunder filtering reducing density
- **README.md** rewritten to professional standard
- **Version bumped** 1.1.0 → 2.2.0

### Removed
- **6 non-code formats** from file discovery: `.yml`, `.yaml`, `.json`, `.md`,
  `.html`, `.htm`, `.css`, `.toml` — config noise was flooding output

### Fixed
- **O(N²) ranking performance** — `compute_importance()` replaced per-symbol regex
  scans (millions of passes) with a single-pass word tokenizer + set intersection.
  Ranking on 13,957 symbols went from timeout (>30s) → 1.35s.
- **Tool timeout** increased from 30s → 60s for headroom on large repos
- **Sort tiebreaker** — non-test files now sort before test files when importance
  scores are equal

## [2.1.0] — 2026-05-11

### Changed
- **Tree-sitter only** — regex fallback removed. `_REGEX_PATTERNS` (~230 lines)
  and `extract_symbols_regex()` deleted. Auto-install ensures Tree-sitter is
  always present.
- **Auto-install replaces manual deps** — `checkDeps()` replaced with `ensureDeps()`
  which probes, auto-installs 27 grammars, and only warns if install fails.

### Fixed
- `get_repo_map` tool now respects `/repo-baby off` toggle
- `package.json` description updated from stale injection language
- `.json` files now discovered (was missing from `SUPPORTED_EXTENSIONS`)
- `ref_count` type annotation fixed: `Dict[str, int]` → `Dict[Tuple[str, str], int]`

### Removed
- `IGNORE_EXTENSIONS` frozenset (dead code)
- Dead `impl_item` handler inside `name_node` block
- Redundant `_should_include_file` check in `extract_symbols()`
- Stale "regex fallback" strings from command messages

## [2.0.0] — 2026-05-11

### Removed
- **System prompt injection** — entire `before_agent_start` handler removed.
  The agent pulls the map on demand via the tool, not pushed into context.
- Map cache (`state.mapCache`, `state.isInjected`, `state.lastGitHash`)
- Cache invalidation (`tool_execution_end` handler after `write`/`edit`)
- Per-model token budget selection
- REPO MAP acknowledgment directives (forced agent recitation)

### Changed
- **Architecture: tool-only.** Agent calls `get_repo_map` when it wants context.
- State interface trimmed to `enabled`, `depsChecked`, `depsOk`
- File size: 393 → 246 lines (37% reduction)

## [1.1.0] — 2026-05-10

### Added
- 20 new languages with Tree-sitter support
- HCL/Terraform via `tree-sitter-hcl`
- Startup dependency health check
- `/repo-baby doctor` command
- New AST node handlers for Go, Rust, C/C++, Ruby

### Fixed
- Interface scope leak in TypeScript
- Keyword token false matches in Ruby/TypeScript
- Go `type_declaration` name extraction
- Rust `impl_item` handler

## [1.0.0] — 2026-05-09

- Initial release
- 6-language Tree-sitter extraction
- System prompt injection (removed in v2.0)
- Cross-file reference ranking
- `/repo-baby` slash command
- Git-based file discovery
