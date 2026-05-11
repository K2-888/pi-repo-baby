<p align="center">
  <a href="https://github.com/k2-888/pi-repo-baby">
    <img alt="Repo Baby" src="https://raw.githubusercontent.com/k2-888/pi-repo-baby/main/assets/logo.svg" width="96" onerror="this.style.display='none'">
  </a>
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/pi-repo-baby"><img alt="npm" src="https://img.shields.io/npm/v/pi-repo-baby?style=flat-square" /></a>
  <a href="https://github.com/k2-888/pi-repo-baby/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/npm/l/pi-repo-baby?style=flat-square" /></a>
</p>

---

Repo Baby is a [Pi](https://pi.dev) extension that gives the agent an `explore_codebase`
tool — a Tree-sitter–powered structural map of any codebase. 19 languages, cross-file
reference ranking, zero injection, zero setup.

## Table of Contents

- [What It Does](#what-it-does)
- [When to Use (and When Not To)](#when-to-use-and-when-not-to)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Supported Languages](#supported-languages)
- [How It Works](#how-it-works)
- [Comparison](#comparison)
- [Architecture](#architecture)
- [Design Decisions](#design-decisions)
- [License](#license)

---

## What It Does

The agent calls `explore_codebase` and gets a ranked structural map:

```
- rich/console.py:
  class Console (line 581)  ← 104 files
  class ConsoleOptions (line 113)  ← 32 files
  class Group (line 450)  ← 13 files
  function group (line 483)  ← 6 files
- rich/progress.py:
  function open (line 372)  ← 36 files
  class Progress (line 1061)  ← 6 files
  class TextColumn (line 616)  ← 4 files
  class BarColumn (line 646)  ← 4 files
- rich/style.py:
  class Style (line 40)  ← 44 files
  class StyleStack (line 765)  ← 6 files
```

Symbols are ranked by cross-file reference count. The more files that reference a
symbol, the higher it appears. Entry points (`main`, `App`, `index`) get a boost.
Test files and dunder methods (`__init__`, `__str__`) are filtered out.

The agent uses this to jump straight to the right file instead of chaining `ls` →
`find` → `rg` → `read`. After making edits, it calls `explore_codebase` again to
verify the structure is intact.

## When to Use (and When Not To)

`explore_codebase` is built for **large, unfamiliar codebases.** If you're
opening a PR against an open-source project you've never seen, onboarding to a
monorepo, tracing a bug through a legacy system, or auditing a codebase for
security review — the map saves 5–15 exploration turns by telling the agent
exactly where everything lives.

| Environment | Use it? | Why |
|-------------|---------|-----|
| Open-source projects (first contribution) | ✅ | You don't know the layout. The map shows entry points, core classes, and cross-file call chains in one call. |
| Monorepos (50+ packages) | ✅ | The dependency graph spans dozens of directories. `ls` can't show you that `auth.ts` is referenced by 47 files across 6 packages. |
| Enterprise codebases | ✅ | Hundreds of files, years of accretion. The ranking surfaces the files that *actually matter* instead of the ones that happen to sort first alphabetically. |
| Legacy systems (no docs) | ✅ | No README, no architecture diagram. The map IS the documentation — ranked symbols with reference counts. |
| Code review / security audit | ✅ | "Find every file that touches authentication" — the map shows the call graph before you read a single line. |
| Refactoring (cross-cutting) | ✅ | "What breaks if I rename this class?" The ref count tells you exactly how many files reference it. |
| Your own project (you know it) | ❌ | You already know where everything is. The map adds no information. |
| 3-file scripts / utilities | ❌ | `ls` shows you everything in one command. The map is overhead. |
| Single-file edits in a known file | ❌ | You're going straight to `read` + `edit`. The map is an extra call with no payoff. |
| The agent already called it this session | ❌ | Don't re-call. The map is fresh until you make edits. Call it again *after* edits to verify. |

**To disable:** `/repo-baby off` hides the tool from the agent entirely.
`/repo-baby on` brings it back. Use `off` when you're in familiar territory
or working on a single file — no point paying the ~10s generation cost for zero benefit.

The extension loads by default. If most of your work is small projects, set it
to start disabled and toggle on for big ones:

```bash
/repo-baby off   # default off for quick work
/repo-baby on    # toggle on when you clone something big
```

---

## Quick Start

```bash
git clone https://github.com/k2-888/pi-repo-baby ~/.pi/agent/extensions/repo-baby
```

That's it. The extension auto-installs 27 Tree-sitter grammars into its own `venv/`
on first session. You'll see a toast notification during install (~30 seconds),
then it's silent forever. No `pip install`, no manual steps.

---

## Usage

| Command | Effect |
|---------|--------|
| `/repo-baby` | Show usage and current state |
| `/repo-baby on` | Enable the tool (default) |
| `/repo-baby off` | Disable — tool hidden from agent |
| `/repo-baby status` | Show enabled state + dependency health |
| `/repo-baby doctor` | Re-check Python/Tree-sitter deps |
| `/repo-baby refresh` | Reminder: `explore_codebase` gives a fresh snapshot |

The agent calls `explore_codebase` on its own — typically as its first action when
entering a codebase, and again after edits. Three mechanisms guide adoption:

1. **`promptSnippet`** — one-liner in the agent's `Available tools:` list
2. **`promptGuidelines`** — behavioral rules in the `Guidelines:` section
3. **Mid-turn steer nudge** — if the agent chains 2+ `ls`/`fd`/`find` exploration
   commands without using `explore_codebase`, a reminder message is injected

---

## Supported Languages

All 19 languages use Tree-sitter. No regex anywhere.

| Language | Extensions | Grammar |
|----------|-----------|---------|
| Python | `.py` | `tree-sitter-python` |
| JavaScript | `.js` | `tree-sitter-javascript` |
| TypeScript | `.ts`, `.tsx` | `tree-sitter-typescript` |
| Go | `.go` | `tree-sitter-go` |
| Rust | `.rs` | `tree-sitter-rust` |
| Ruby | `.rb` | `tree-sitter-ruby` |
| Java | `.java` | `tree-sitter-java` |
| C | `.c`, `.h` | `tree-sitter-c` |
| C++ | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx` | `tree-sitter-cpp` |
| C# | `.cs` | `tree-sitter-c-sharp` |
| PHP | `.php` | `tree-sitter-php` |
| Kotlin | `.kt`, `.kts` | `tree-sitter-kotlin` |
| Swift | `.swift` | `tree-sitter-swift` |
| Scala | `.scala`, `.sc` | `tree-sitter-scala` |
| Bash | `.sh`, `.bash` | `tree-sitter-bash` |
| SQL | `.sql` | `tree-sitter-sql` |
| Lua | `.lua` | `tree-sitter-lua` |
| Elixir | `.ex`, `.exs` | `tree-sitter-elixir` |
| Haskell | `.hs` | `tree-sitter-haskell` |
| Terraform / HCL | `.tf`, `.tfvars`, `.hcl` | `tree-sitter-hcl` |

---

## How It Works

### File Discovery

Prefers `git ls-files` (respects `.gitignore`). Falls back to `os.walk` with
ignore rules for `node_modules`, `.venv`, `dist`, `vendor`, etc.

### Symbol Extraction

Each file is parsed with the appropriate Tree-sitter grammar. The AST is walked
to extract function, class, method, interface, struct, trait, and impl declarations.
Class/module context is tracked so methods display as `ClassName.method()`.

Dunder methods (`__init__`, `__str__`, `__repr__`) and config files (YAML, JSON,
Markdown, HTML, CSS, TOML) are excluded — they add noise without signal.

### Ranking

Uses **in-degree reference counting**: for each symbol, counts how many other files
contain its name. A word-boundary tokenizer scans each file once (O(file_size)),
then set-intersection with symbol names produces reference counts.

Core structural types (classes, interfaces) get a 1.5× boost. Test files get a
20× demotion. JSON/YAML keys are sunk to -1.0.

### Output

Symbols are sorted by reference count (descending) then grouped by file. Output
is trimmed to the token budget. Reference counts are shown inline so the agent
can see *why* something ranks high without verifying with `rg`.

---

## Comparison

### vs Aider's Repo Map

| | Aider | Repo Baby |
|---|---|---|
| Delivery | Injected into every prompt | Agent pulls on demand via tool |
| Extraction | Tree-sitter + ctags fallback | Tree-sitter only |
| Setup | Manual dependency install | Auto-installs 27 grammars |
| Ranking | Map-reduce over symbols | Cross-file reference counting |
| Staleness | Refreshed by framework per-turn | Agent decides when to refresh |
| Guidance | Raw data in context | `promptSnippet` + `promptGuidelines` + steer nudge |

### vs RAG / Embeddings

| | RAG | Repo Baby |
|---|---|---|
| Infrastructure | Vector DB, embeddings model, chunking | Single Python script |
| Cost | API calls, storage, re-indexing | Free, deterministic, local |
| Freshness | Must re-index after changes | On-demand regeneration (~0.5s file discovery) |
| Signal | Semantic chunks, retrieval misses possible | Exact symbol map with call graph |
| Failure mode | Silent retrieval gaps | Binary — map exists or it doesn't |

---

## Architecture

```
index.ts (TypeScript) ──pi.exec()──→ repo-baby.py --path <cwd> --token-budget <N>
       │                                    │
       │  explore_codebase tool              │  git ls-files OR os.walk
       │  /repo-baby command                │  Tree-sitter parse each file
       │  session_start → ensureDeps()      │  Word-tokenizer reference counting
       │  tool_call → exploration tracker   │  In-degree ranking + formatting
       │  tool_execution_end → steer nudge  │
       │                                    ↓
       └── All paths call the same script   stdout → returned to agent
```

**`index.ts`** (~320 lines)
- `explore_codebase` tool with `promptSnippet` and `promptGuidelines`
- `/repo-baby` slash command with tab-completion
- `ensureDeps()` — one-time auto-install of 27 Tree-sitter grammars
- Exploration tracking — steer nudge after 2+ bash exploration commands

**`repo-baby.py`** (~650 lines)
- File discovery: `git ls-files` → `os.walk` fallback
- Symbol extraction: Tree-sitter AST walk with class/module context
- Ranking: single-pass word tokenizer + set-intersection reference counting
- Formatting: token-budget-aware output with inline reference counts

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Tool agency over injection** | Pi agents have tools. Pushing data into context fights the architecture. |
| **Tree-sitter only** | If the parser isn't available, skip silently. No fallback, no ambiguity. |
| **Auto-install deps** | User never sees a dep command. Extension handles its own requirements. |
| **In-degree ranking** | Simpler than PageRank, equally effective, no `networkx` dependency. |
| **Reference counts in output** | `← 104 files` tells the agent *why* something ranks high. Builds trust. |
| **No caching** | Regenerates from scratch. Always fresh. Accept the ~10s cost on large repos. |
| **Code-only discovery** | YAML, JSON, Markdown, HTML, CSS, TOML excluded — config noise dilutes signal. |
| **Test file demotion (20×)** | Production code surfaces first. Tests still appear if they have genuine cross-file importance. |
| **Dunder filter** | `__init__`, `__str__`, `__repr__` are boilerplate. Filtered at extraction time. |
| **Deduplication** | Same-name symbols in one file appear once. No `function open` × 3. |
| **Action-verb name** | `explore_codebase` sits naturally alongside `read`, `write`, `edit`, `bash`. |

---

## License

MIT
