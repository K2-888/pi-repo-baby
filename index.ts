/**
 * Repo Baby — Repository Map for Pi
 *
 * Gives Pi structural awareness of any codebase via a `explore_codebase` tool
 * that the agent calls on demand. Uses Tree-sitter (via a companion Python
 * script) for multi-language symbol extraction with in-degree ranking.
 *
 * Usage:
 *   /repo-baby on       — Enable the tool (default)
 *   /repo-baby off      — Disable the tool
 *   /repo-baby status   — Show enabled state + dep health
 *   /repo-baby doctor   — Re-check Python dependencies
 *   /repo-baby refresh  — Reminder to call explore_codebase
 *
 * Requirements:
 *   - Python 3 with tree-sitter + language grammars installed
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

interface RepoBabyState {
	enabled: boolean;
	depsChecked: boolean;
	depsOk: boolean;
}

const state: RepoBabyState = {
	enabled: true,
	depsChecked: false,
	depsOk: false,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Resolve the directory this extension file lives in */
function extensionDir(): string {
	try {
		return dirname(fileURLToPath(import.meta.url));
	} catch {
		// Fallback for environments where import.meta.url is unavailable
		return process.env.HOME
			? join(process.env.HOME, ".pi", "agent", "extensions")
			: ".";
	}
}

/** Path to the companion Python script (same directory as this file) */
function pythonScriptPath(): string {
	return join(extensionDir(), "repo-baby.py");
}

/** Path to the venv Python interpreter (bundled inside this extension directory) */
function pythonBin(): string {
	return join(extensionDir(), "venv", "bin", "python3");
}

/** Use venv python if available, else fall back to system python3 */
function pythonCommand(): string {
	return existsSync(pythonBin()) ? pythonBin() : "python3";
}

/** Ensure Python tree-sitter deps are installed. Auto-installs if missing. */
async function ensureDeps(
	pi: ExtensionAPI,
	ctx?: { ui: { notify: (msg: string, type: string) => void } },
): Promise<{ ok: boolean; detail: string }> {
	const script = pythonScriptPath();
	if (!existsSync(script)) {
		return { ok: false, detail: "repo-baby.py not found — extension may be corrupted" };
	}

	// If venv exists from a previous successful install, skip the probe entirely.
	// The venv is self-contained — if it exists on disk, it works.
	if (existsSync(pythonBin())) {
		return { ok: true, detail: "tree-sitter-language-pack ready (cached)" };
	}

	// No venv yet — probe system python in case deps are globally installed
	const python = pythonCommand();
	const probe = "import tree_sitter_language_pack; print('OK')";

	try {
		const { stdout, code } = await pi.exec(python, ["-c", probe], { timeout: 10_000 });
		if (code === 0 && stdout.trim() === "OK") {
			return { ok: true, detail: "tree-sitter-language-pack available (system)" };
		}
	} catch {
		// probe failed — proceed to install
	}

	// Deps missing — auto-install
	if (ctx) ctx.ui.notify("Repo Baby: installing dependencies (this may take a minute)…", "info");

	const extDir = extensionDir();
	try {
		const { code: installCode, stderr } = await pi.exec("npm", ["run", "install-deps"], {
			cwd: extDir,
			timeout: 120_000,
		});

			if (installCode === 0) {
			// Verify packages are importable (not just venv existed)
			const python2 = pythonCommand();
			const { stdout: out2, code: code2 } = await pi.exec(python2, ["-c", probe], { timeout: 10_000 });
			if (code2 === 0 && out2.trim() === "OK") {
				if (ctx) ctx.ui.notify("✅ Repo Baby: dependencies installed — Tree-sitter active", "success");
				return { ok: true, detail: "tree-sitter-language-pack ready" };
			}
		}

		const errorDetail = (installCode === 0)
			? "Install completed but import verification failed — dependencies may not be usable"
			: `Exit ${installCode}: ${stderr?.trim() || "no output"}`;
		if (ctx) ctx.ui.notify(`⚠ Repo Baby: ${errorDetail}`, "warning");
		return { ok: false, detail: errorDetail };
	} catch (err: any) {
		if (ctx) ctx.ui.notify(`⚠ Repo Baby: install failed — ${err.message}`, "warning");
		return { ok: false, detail: err.message };
	}
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export default function repoBabyExtension(pi: ExtensionAPI) {
	// ---- Tool: explore_codebase ------------------------------------------------

	pi.registerTool({
		name: "explore_codebase",
		label: "Get Repo Map",
		description:
			"Return a high-level structural map of the codebase: functions, classes, " +
			"methods, interfaces, structs, and more — ranked by cross-file reference " +
			"importance so the most significant code appears first. Call this FIRST " +
			"when entering an unfamiliar codebase or when the user asks you to explore, " +
			"understand, or modify code. It tells you exactly which files matter and " +
			"which symbols are entry points, replacing multiple ls/find/rg/read calls " +
			"with a single structured overview. After making edits, call it again to " +
			"verify the structure is intact — it returns a fresh snapshot.",
		promptSnippet:
			"Ranked structural overview of the codebase — functions, classes, methods " +
			"sorted by cross-file reference importance. Call FIRST when exploring any repo.",
		promptGuidelines: [
			"Use explore_codebase as your FIRST action when starting work in any codebase — " +
			"it shows the most important symbols (ranked by how many files reference them) " +
			"so you know exactly which files to read and which symbols are entry points.",
			"Use explore_codebase after making edits to verify the codebase structure is intact " +
			"— it returns a fresh snapshot showing your changes landed correctly and no " +
			"symbols were orphaned.",
			"Use explore_codebase instead of chaining ls + find + rg + read for initial " +
			"codebase exploration — one call replaces multiple exploration commands and " +
			"shows cross-file relationships that grep cannot reveal.",
		],
		parameters: Type.Object({
			scope: Type.Optional(
				Type.String({ description: "Limit to a subdirectory (e.g. 'src/')" }),
			),
			token_budget: Type.Optional(
				Type.Number({ description: "Max tokens for the map (default 800)", default: 800 }),
			),
		}),

		async execute(_id, params, _signal, _onUpdate, ctx) {
			if (!state.enabled) {
				throw new Error("Repo Baby is disabled. Use /repo-baby on to enable.");
			}

			const script = pythonScriptPath();
			if (!existsSync(script)) {
				throw new Error(`repo-baby.py not found at ${script}`);
			}

			const cwd = ctx.cwd;
			const budget = params.token_budget || 800;

			// Build argument list — include --scope if provided
			const args = [script, "--path", cwd, "--token-budget", String(budget)];
			if (params.scope) {
				args.push("--scope", params.scope);
			}

			const python = pythonCommand();
			const { stdout, code, stderr } = await pi.exec(python, args, {
				cwd,
				timeout: 60_000,
			});

			if (code !== 0) {
				throw new Error(`repo-baby.py failed: ${stderr?.trim() || `exit ${code}`}`);
			}

			return {
				content: [{ type: "text", text: stdout.trim() }],
			};
		},
	});

	// ---- Command: /repo-baby -----------------------------------------------

	pi.registerCommand("repo-baby", {
		description: "Toggle repository map on/off",
		getArgumentCompletions(prefix: string) {
			const opts = ["on", "off", "status", "refresh", "doctor"];
			const filtered = opts.filter((o) => o.startsWith(prefix));
			return filtered.length > 0 ? filtered.map((o) => ({ value: o, label: o })) : null;
		},

		async handler(args, ctx) {
			const cmd = args.trim().toLowerCase();

			if (cmd === "on") {
				state.enabled = true;
				ctx.ui.notify("Repo Baby: ON — use \`explore_codebase\` tool to see repository structure", "success");
				return;
			}

			if (cmd === "off") {
				state.enabled = false;
				ctx.ui.notify("Repo Baby: OFF — use \`/repo-baby on\` to re-enable", "info");
				return;
			}

			if (cmd === "refresh") {
				ctx.ui.notify("Repo Baby: use the \`explore_codebase\` tool for a fresh snapshot", "info");
				return;
			}

			if (cmd === "doctor") {
				ctx.ui.notify("Repo Baby: checking dependencies…", "info");
				try {
					const result = await ensureDeps(pi, ctx);
					state.depsChecked = true;
					state.depsOk = result.ok;
					if (result.ok) {
						ctx.ui.notify(`✅ Repo Baby: ${result.detail}`, "success");
					} else {
						ctx.ui.notify(`⚠ Repo Baby: ${result.detail}`, "warning");
					}
				} catch (err: any) {
					ctx.ui.notify(`⚠ Repo Baby: probe failed — ${err?.message || "unknown error"}`, "warning");
					state.depsChecked = true;
					state.depsOk = false;
				}
				return;
			}

			if (cmd === "status") {
				const s = state.enabled ? "enabled" : "disabled";
				const deps = state.depsChecked
					? state.depsOk
						? "Tree-sitter OK"
						: "not installed"
					: "not checked";
				ctx.ui.notify(`Repo Baby: ${s}, deps: ${deps}`, "info");
				return;
			}

			ctx.ui.notify(
				`Usage: /repo-baby on|off|status|refresh|doctor (currently ${state.enabled ? "on" : "off"})`,
				"info",
			);
		},
	});

	// ---- Event: reset state on new sessions --------------------------------

	pi.on("session_start", async (_event, ctx) => {
		// Reset exploration tracking for fresh session
		explorationStreak = 0;
		nudgeDeliveredThisTurn = false;

		// One-time dependency check + auto-install
		if (!state.depsChecked) {
			state.depsChecked = true;
			const result = await ensureDeps(pi, ctx);
			state.depsOk = result.ok;
			if (!result.ok) {
				state.enabled = false;
				if (ctx) ctx.ui.notify(
					"Repo Baby disabled — use /repo-baby doctor to retry after fixing dependencies",
					"warning",
				);
			}
		}
	});

	// ---- Exploration tracking: nudge when agent chains bash exploration ----

	let explorationStreak = 0;
	let nudgeDeliveredThisTurn = false;

	pi.on("tool_call", async (event) => {
		if (!state.enabled || nudgeDeliveredThisTurn) return;
		if (event.toolName !== "bash") return;

		const input = event.input as { command?: string } | undefined;
		const cmd = input?.command ?? "";

		// Detect exploration commands: ls, find, fd, tree, rg, grep
		if (/\b(ls|find|fd|tree|rg|grep)\b/i.test(cmd)) {
			explorationStreak++;
		}
	});

	pi.on("tool_execution_end", async (event) => {
		if (!state.enabled || nudgeDeliveredThisTurn) return;

		// Reset streak when agent uses explore_codebase — it remembered
		if (event.toolName === "explore_codebase") {
			explorationStreak = 0;
			return;
		}

		// After 2 exploration commands without using explore_codebase, nudge
		if (explorationStreak >= 2) {
			pi.sendMessage(
				{
					customType: "repo-baby-nudge",
					content:
						"You've used multiple ls/find/fd/rg exploration commands. " +
						"Use explore_codebase instead — it returns a ranked structural " +
						"map of the entire codebase (functions, classes, methods sorted " +
						"by cross-file reference importance) in a single call.",
					display: true,
				},
				{ deliverAs: "steer" },
			);
			explorationStreak = 0;
			nudgeDeliveredThisTurn = true;
		}
	});

	// Reset tracking each turn so the agent gets a fresh chance
	pi.on("turn_start", async () => {
		explorationStreak = 0;
		nudgeDeliveredThisTurn = false;
	});
}
