import { useState } from "react";
import { ChevronDown, Wrench } from "lucide-react";

// ---------------------------------------------------------------------------
// JSON syntax tokeniser
// ---------------------------------------------------------------------------

type TokenKind = "key" | "string" | "number" | "literal" | "punct" | "space";

interface Token {
  kind: TokenKind;
  text: string;
}

// Each alternative is a capture group; order matters.
// Group 1 – object key  (quoted string immediately followed by colon)
// Group 2 – string value
// Group 3 – boolean / null literal
// Group 4 – number
// Group 5 – structural punctuation
// Group 6 – everything else (whitespace, newlines, …)
const TOKEN_RE =
  /("(?:[^"\\]|\\.)*"\s*:)|("(?:[^"\\]|\\.)*")|(true|false|null)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|([{}[\],])|(\s+|.)/g;

function tokenize(json: string): Token[] {
  const tokens: Token[] = [];
  TOKEN_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TOKEN_RE.exec(json)) !== null) {
    if      (m[1]) tokens.push({ kind: "key",     text: m[1] });
    else if (m[2]) tokens.push({ kind: "string",  text: m[2] });
    else if (m[3]) tokens.push({ kind: "literal", text: m[3] });
    else if (m[4]) tokens.push({ kind: "number",  text: m[4] });
    else if (m[5]) tokens.push({ kind: "punct",   text: m[5] });
    else           tokens.push({ kind: "space",   text: m[6] });
  }
  return tokens;
}

const TOKEN_COLOR: Record<TokenKind, string> = {
  key:     "text-sky-400",
  string:  "text-emerald-400",
  number:  "text-orange-400",
  literal: "text-violet-400",
  punct:   "text-zinc-500",
  space:   "",
};

// ---------------------------------------------------------------------------
// Sub-component: highlighted <pre> block
// ---------------------------------------------------------------------------

function HighlightedJSON({ value }: { value: Record<string, unknown> }) {
  const json = JSON.stringify(value, null, 2);
  const tokens = tokenize(json);
  return (
    <pre className="m-0 overflow-x-auto whitespace-pre text-xs leading-relaxed">
      {tokens.map((tok, i) => (
        <span key={i} className={TOKEN_COLOR[tok.kind]}>
          {tok.text}
        </span>
      ))}
    </pre>
  );
}

// ---------------------------------------------------------------------------
// ToolBadge
// ---------------------------------------------------------------------------

export interface ToolBadgeProps {
  toolName: string;
  params: Record<string, unknown>;
}

function compact(text: string, limit = 180): string {
  const value = text.replace(/\s+/g, " ").trim();
  return value.length <= limit ? value : `${value.slice(0, limit - 3).trim()}...`;
}

function paramText(params: Record<string, unknown>, key: string): string {
  const value = params[key];
  return typeof value === "string" ? value : "";
}

function formatToolSummary(toolName: string, params: Record<string, unknown>): string {
  if (toolName === "execute_terminal_command") {
    return `Running: ${compact(paramText(params, "command"), 260)}`;
  }
  if (toolName === "execute_background_service") {
    return `Starting service: ${compact(paramText(params, "command"), 260)}`;
  }
  if (toolName === "write_text_file" || toolName === "write_file") {
    return `Writing ${paramText(params, "path") || paramText(params, "file_path") || "file"}`;
  }
  if (toolName === "edit_file") {
    return `Editing ${paramText(params, "path") || paramText(params, "file_path") || "file"}`;
  }
  if (toolName === "web_search") {
    return `Searching: ${compact(paramText(params, "query"), 160)}`;
  }
  if (toolName === "web_fetch") {
    return `Fetching ${compact(paramText(params, "url"), 200)}`;
  }
  if (toolName === "wait_for_port") {
    return `Waiting for port ${String(params.port ?? "?")}`;
  }
  if (toolName === "expose_local_http_service") {
    return `Exposing port ${String(params.port ?? "?")}`;
  }
  if (toolName.startsWith("browser_")) {
    const action = toolName.slice("browser_".length).replaceAll("_", " ");
    const target = paramText(params, "url") || paramText(params, "selector");
    return target ? `Browser ${action}: ${compact(target, 120)}` : `Browser ${action}`;
  }
  return toolName.replaceAll("_", " ");
}

export function ToolBadge({ toolName, params }: ToolBadgeProps) {
  const [open, setOpen] = useState(false);
  const summary = formatToolSummary(toolName, params);

  return (
    <div className="w-full overflow-hidden rounded-lg border border-zinc-700 font-mono shadow-lg">
      {/* Header */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full cursor-pointer items-center gap-2 bg-zinc-800 px-3 py-2 text-left transition-colors hover:bg-zinc-750"
        aria-expanded={open}
      >
        <Wrench size={14} className="shrink-0 text-zinc-400" />
        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-zinc-200">
          {summary}
        </span>
        <span className="hidden shrink-0 rounded border border-zinc-700 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-500 sm:inline">
          {toolName}
        </span>
        <ChevronDown
          size={14}
          className={`shrink-0 text-zinc-400 transition-transform duration-200 ${
            open ? "rotate-180" : "rotate-0"
          }`}
        />
      </button>

      {/* Collapsible body — grid trick for smooth height animation */}
      <div
        className={`grid transition-all duration-200 ease-in-out ${
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        }`}
      >
        <div className="overflow-hidden">
          <div className="bg-zinc-900 px-4 py-3 text-zinc-300">
            <HighlightedJSON value={params} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default ToolBadge;
