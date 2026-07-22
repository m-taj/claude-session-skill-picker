// OpenCode plugin — wires the existing skill picker into OpenCode's own
// plugin hooks. Reuses skills-launch.py verbatim for the "session start"
// side (feeding it a synthetic {"session_id": ...} stdin payload matching
// exactly what it already expects from Claude Code/Codex).
//
// Real API found by inspecting the installed @opencode-ai/plugin package
// directly (npm view + tarball extraction, 2026-07-22) rather than trusting
// the public docs alone — the docs' example plugin shape
// (`export const MyPlugin = async ({...}) => {{ ...hooks... }}`) turned out
// to be accurate for the CURRENT/default plugin API (a `Plugin =
// (input, options?) => Promise<Hooks>` function), which matches this file.
// There is also a newer, separate "v2" API (`define({id, setup(context)})`
// with a first-class `context.skill.transform()` for registering real skill
// sources) shipped in the same package under `./v2/promise` — not used here
// since the classic Hooks API is what's actually documented as the current
// plugin entry point; revisit if the v2 API becomes the primary one.
//
// Injection point: `chat.message` (appends a synthetic text Part to the
// incoming user message) — NOT `experimental.chat.system.transform`, which
// was tried first and, despite matching its documented type exactly,
// never actually fired at runtime across several real chat turns in live
// testing (2026-07-22) — no error, just never invoked. Plausible given the
// "experimental." prefix: declared in the types, not necessarily fully
// wired yet in this OpenCode version (v1.14.19). `chat.message` carries no
// such prefix and the SDK's `TextPart` type even has a dedicated
// `synthetic?: boolean` field for exactly this kind of injected content,
// so it's a better-supported mechanism, not just a fallback guess.

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const CACHE_DIR     = path.join(os.homedir(), ".claude", "cache");
const LAUNCH_SCRIPT  = path.join(os.homedir(), ".claude", "hooks", "skills-launch.py");
const CATALOG_PATH   = path.join(CACHE_DIR, "skills-catalog.json");

function readCatalog() {
  try {
    return JSON.parse(fs.readFileSync(CATALOG_PATH, "utf-8"));
  } catch {
    return [];
  }
}

/** Returns an array of skill instruction blocks for this session's picks,
 * or [] if the picker hasn't produced a pending file (yet, or at all). */
function resolvePicks(sessionID) {
  const pendingPath = path.join(CACHE_DIR, `skills-pending-${sessionID}.txt`);
  if (!fs.existsSync(pendingPath)) return [];

  let raw;
  try {
    raw = fs.readFileSync(pendingPath, "utf-8");
  } catch {
    return [];
  }
  try {
    fs.unlinkSync(pendingPath);
  } catch {
    // ignore — non-fatal, matches the other adapters' best-effort cleanup
  }

  const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) return [];

  const catalog = Object.fromEntries(readCatalog().map((e) => [e.name, e]));
  const blocks = [];
  for (const line of lines) {
    const sepIdx = line.indexOf("|");
    const name = (sepIdx === -1 ? line : line.slice(0, sepIdx)).trim();
    const arg  = (sepIdx === -1 ? "" : line.slice(sepIdx + 1)).trim();
    const entry = catalog[name];
    if (!entry) continue;

    let body = entry.description || "";
    if (entry.path && fs.existsSync(entry.path)) {
      try {
        body = fs.readFileSync(entry.path, "utf-8").trim();
      } catch {
        // fall back to description already assigned above
      }
    }
    if (!body) continue;

    const header = `### Skill: ${name}` + (arg ? ` (arg: ${arg})` : "");
    blocks.push(header + "\n\n" + body);
  }
  return blocks;
}

export const SkillPickerPlugin = async (_input) => {
  // Sessions already injected — NOT a cache of resolvePicks() results.
  // Real bug found live (2026-07-22): the very first chat.message call
  // fires ~100ms after session.created, before skills-launch.py/the picker
  // have had time to write a pending file — resolvePicks() correctly
  // returns [] for "not ready yet", but caching that empty result meant
  // the real pick (written seconds later, after the user actually
  // interacted with the picker) was never re-checked. Only mark a session
  // done AFTER a real successful injection.
  const injected = new Set();

  return {
    event: async ({ event }) => {
      if (event.type !== "session.created") return;
      const sessionID = event.properties.sessionID;
      try {
        const child = spawn("python3", [LAUNCH_SCRIPT], {
          stdio: ["pipe", "ignore", "ignore"],
          detached: true,
        });
        child.stdin.write(JSON.stringify({ session_id: sessionID }));
        child.stdin.end();
        child.unref();
      } catch {
        // best-effort — matches every other adapter's "never block/crash
        // the host on a picker-launch failure" rule
      }
    },

    "chat.message": async (input, output) => {
      const sessionID = input.sessionID;
      if (!sessionID || injected.has(sessionID)) return;

      const blocks = resolvePicks(sessionID);
      if (blocks.length === 0) return; // not ready yet (or nothing picked) — retry next turn

      const msg =
        "[STARTUP HOOK - The user selected these skills for this session. " +
        "Follow their instructions below as part of how you operate for the " +
        "rest of this session, starting now:\n\n" +
        blocks.join("\n\n---\n\n") +
        "]";

      try {
        // Part ids must start with "prt" — OpenCode's own schema validation
        // rejects anything else (confirmed via the exact SchemaError this
        // threw with our old "skillpicker-<sessionID>" id, which crashed
        // the whole message pipeline downstream, not just our hook).
        const partID = `prt_skillpicker${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
        output.parts.push({
          id: partID,
          sessionID,
          messageID: output.message.id,
          type: "text",
          text: msg,
          synthetic: true,
        });
      } catch {
        return; // don't mark as injected — retry next turn
      }

      // Inject once per session, not on every turn — matches the existing
      // Claude Code / Codex behavior (skills-inject.py / codex_inject.py).
      injected.add(sessionID);
    },
  };
};

export default SkillPickerPlugin;
