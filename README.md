<p align="center">
  <a href="https://github.com/k2-888/pi-repo-baby">
    <img alt="Repo Baby" src="https://raw.githubusercontent.com/k2-888/pi-repo-baby/main/assets/logo.png" width="128">
  </a>
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/pi-repo-baby"><img alt="npm" src="https://img.shields.io/npm/v/pi-repo-baby?style=flat-square" /></a>
  <a href="https://github.com/k2-888/pi-repo-baby/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/npm/l/pi-repo-baby?style=flat-square" /></a>
</p>

---

# Repo Baby

> Structural awareness for your AI coding agent. Zero setup, zero injection, zero config.

## ✨ Highlights

- **19 languages** — Python, JavaScript, TypeScript, Go, Rust, Ruby, Java, C, C++, C#, PHP, Kotlin, Swift, Scala, Bash, SQL, Lua, HCL — all via Tree-sitter, no regex
- **Cross-file ranking** — symbols sorted by how many files reference them, so the important code surfaces first
- **One call, not five** — replaces the `ls` → `find` → `rg` → `read` chain with a single structural map
- **Auto-installs its own dependencies** — you clone it, it handles the rest
- **Fresh every time** — regenerates on demand, never stale

---

## What It Does

Repo Baby gives your [Pi](https://pi.dev) agent a `read_codebase` tool. The agent calls it and gets a ranked structural map of the codebase:

```
- rich/console.py:
  class Console (line 581)  ← 104 files
  class ConsoleOptions (line 113)  ← 32 files
  class Group (line 450)  ← 13 files
- rich/progress.py:
  function open (line 372)  ← 36 files
  class Progress (line 1061)  ← 6 files
  class BarColumn (line 646)  ← 4 files
- rich/style.py:
  class Style (line 40)  ← 44 files
```

Symbols are ranked by cross-file reference count — the more files that reference a function or class, the higher it appears. Reference counts are shown inline (`← 104 files`) so the agent can see *why* something ranks where it does. Dunder methods, config files, and test noise are filtered out.

Instead of chaining five exploration commands, the agent makes one call and knows exactly where to start.

### When It Shines

`read_codebase` is built for moments where the agent doesn't know the territory. If the codebase fits in your head, you don't need it — and that's fine. But when you're operating beyond what you can hold mentally, the map pays for itself in saved exploration turns.

**Best for:** open-source contributions to unfamiliar repos, monorepos crossing dozens of packages, legacy systems with no architecture docs, cross-cutting refactors where you need to know what breaks, security audits tracing a feature across the call graph.

**Skip it when:** you're in your own project and know the layout, you're making a single-file edit to a file you already read, or the repo is small enough that `ls` tells you everything. Toggle it off with `/repo-baby off` — it costs nothing to disable and nothing to bring back.

---

## Quick Start

```bash
git clone https://github.com/k2-888/pi-repo-baby ~/.pi/agent/extensions/repo-baby
```

That's it. The extension auto-installs `tree-sitter-language-pack` into its own `venv/` on first session. You'll see a toast notification during install, then it's silent forever. No `pip install`, no manual steps.

---

## Usage

The agent calls `read_codebase` on its own — typically as its first action when entering an unfamiliar codebase, and again after making edits to verify structure.

| Command | Effect |
|---------|--------|
| `/repo-baby` | Show usage and current state |
| `/repo-baby on` | Enable the tool (default) |
| `/repo-baby off` | Disable the tool |
| `/repo-baby status` | Show enabled state + dependency health |
| `/repo-baby doctor` | Re-check Python/Tree-sitter dependencies |

---

## Supported Languages

All 19 languages via Tree-sitter, bundled in `tree-sitter-language-pack`.

| Language | Extensions |
|----------|------------|
| Python | `.py` |
| JavaScript | `.js` |
| TypeScript | `.ts` |
| TSX | `.tsx` |
| Go | `.go` |
| Rust | `.rs` |
| Ruby | `.rb` |
| Java | `.java` |
| C | `.c`, `.h` |
| C++ | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx` |
| C# | `.cs` |
| PHP | `.php` |
| Kotlin | `.kt`, `.kts` |
| Swift | `.swift` |
| Scala | `.scala`, `.sc` |
| Bash | `.sh`, `.bash` |
| SQL | `.sql` |
| Lua | `.lua` |
| Terraform / HCL | `.tf`, `.tfvars`, `.hcl` |

---

## How It Works

**File discovery** — prefers `git ls-files` (respects `.gitignore`), falls back to `os.walk`.

**Symbol extraction** — each file is Tree-sitter parsed. Functions, classes, methods, interfaces, structs, traits, and impls are extracted with class/module context so methods display as `ClassName.method()`.

**Ranking** — in-degree reference counting: for each symbol, counts how many other files contain its name. A single-pass tokenizer scans each file once, then set-intersection with symbol names produces reference counts. Core structural types get a boost; test files are demoted.

**Output** — symbols grouped by file, sorted by reference count, trimmed to token budget. Reference counts shown inline.

---

## Architecture

```
index.ts (TypeScript) ──pi.exec()──→ repo-baby.py --path <cwd> --token-budget <N>
       │                                    │
       │  read_codebase tool                │  git ls-files OR os.walk
       │  /repo-baby command                │  Tree-sitter parse each file
       │  session_start → ensureDeps()      │  Tokenizer reference counting
       │                                    │  In-degree ranking + formatting
       │                                    ↓
       └── All paths call the same script   stdout → returned to agent
```

**`index.ts`** — tool registration with adoption mechanisms (`promptSnippet`, `promptGuidelines`, mid-turn steer nudge), slash command, and one-time dependency auto-install.

**`repo-baby.py`** — file discovery, Tree-sitter AST walking with scope tracking, single-pass word tokenizer for reference counting, and token-budget-aware formatting.

---

## Acknowledgments

Inspired by [Aider's repo-map](https://aider.chat/docs/repomap.html) feature — the idea that an AI agent benefits from a ranked, deterministic structural overview of the codebase. Repo Baby reimagines it for Pi's tool-agency architecture, where the agent pulls the map on demand rather than having it pushed into every prompt.

---

## License

MIT
