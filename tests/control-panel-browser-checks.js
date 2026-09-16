// Browser regressions using mocked gateway responses; no model credentials needed.
// Start the UI: npm --prefix control-panel run dev -- --host 127.0.0.1 --port 5174
// Then, with Playwright CLI and its browser installed:
// playwright-cli -s=control-panel-checks open about:blank
// playwright-cli -s=control-panel-checks run-code --filename tests/control-panel-browser-checks.js
// playwright-cli -s=control-panel-checks close
async (page) => {
  const check = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const path = route.request().url().replace("http://127.0.0.1:8000", "").split("?")[0];
    if (path === "/health") return route.fulfill({ json: { status: "ok" } });
    if (path === "/api/approvals") return route.fulfill({ json: { mode: "ask", pending: [] } });
    if (path === "/api/status") {
      return route.fulfill({ json: {
        model: "test", fast_model: "test", strong_model: "test", sandbox: "local",
        channels: { telegram: false, discord: false, slack: false },
        skills: { count: 1, improved: 0 }, cron: { count: 0, enabled: 0 },
        evolution: { staged: 0, promoted: 0, rejected: 0, rolled_back: 0 },
        task_graph: { active: 0, blocked: 0, open_nodes: 0 }, active_sessions: 0,
      } });
    }
    if (path === "/api/skills") {
      return route.fulfill({ json: [{
        name: "demo", version: 1, evolution_status: "live", description: "Test skill",
        tags: [], use_count: 1, success_rate: 1, last_used: null, version_hash: "abc", rollback_count: 0,
      }] });
    }
    if (path === "/api/skills/demo/export.md") {
      if (route.request().headers().authorization !== "Bearer test-token") {
        return route.fulfill({ status: 401, json: { detail: "Missing token" } });
      }
      return route.fulfill({ status: 200, body: "# Demo skill", contentType: "text/markdown" });
    }
    if (path === "/api/config/model" || path === "/api/auth/status") {
      if (route.request().headers().authorization !== "Bearer replacement-token") {
        return route.fulfill({ status: 401, json: { detail: "Invalid gateway token" } });
      }
      return route.fulfill({ json: path === "/api/config/model"
        ? { model: "test", fast_model: "test", strong_model: "test" }
        : { method: "none", signed_in: false } });
    }
    return route.fulfill({ status: 404, json: { detail: "Unknown mock route" } });
  });
  await page.addInitScript(() => {
    const NativeWebSocket = window.WebSocket;
    window.testSockets = [];
    class MockWebSocket {
      static OPEN = 1;
      readyState = 0;
      sent = [];
      constructor(url) {
        if (!String(url).includes("/ws/stream")) return new NativeWebSocket(url);
        this.url = String(url);
        window.testSockets.push(this);
        setTimeout(() => {
          if (this.readyState === 0) {
            this.readyState = 1;
            this.onopen?.({});
          }
        }, 0);
      }
      send(data) {
        const message = JSON.parse(data);
        this.sent.push(message);
        if (message.text === "error") {
          setTimeout(() => this.emit({ type: "error", detail: "Rate limit exceeded" }), 10);
        }
        if (message.text === "disconnect") {
          setTimeout(() => {
            this.emit({ type: "token", content: "Partial response preserved" });
            this.close();
          }, 10);
        }
      }
      close() {
        this.readyState = 3;
        setTimeout(() => this.onclose?.({}), 20);
      }
      emit(event) { this.onmessage?.({ data: JSON.stringify(event) }); }
    }
    window.WebSocket = MockWebSocket;
    try {
      if (!sessionStorage.getItem("control-panel-checks-initialized")) {
        localStorage.clear();
        localStorage.setItem("agent_api_token", "test-token");
        sessionStorage.setItem("control-panel-checks-initialized", "true");
      }
    } catch { /* The final scenario intentionally blocks storage. */ }
  });
  await page.goto("http://127.0.0.1:5174");
  await page.getByRole("button", { name: "Chat", exact: true }).click();
  // StrictMode's abandoned connection closes asynchronously; allow its retry window.
  await page.waitForTimeout(1200);
  check(await page.evaluate(() => window.testSockets.filter((s) => s.readyState === 1).length) === 1,
    "StrictMode must leave exactly one live chat socket");

  const composer = page.getByRole("textbox", { name: "Message the agent..." });
  await composer.fill("error");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page.getByText("Rate limit exceeded", { exact: true }).waitFor();
  check(await composer.isEnabled(), "Gateway error must release the composer");
  check(await page.getByRole("button", { name: "Stop agent task", exact: true }).isDisabled(),
    "Gateway error must end the live turn");

  await composer.fill("disconnect");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page.getByText("Partial response preserved", { exact: true }).waitFor();
  await page.getByText("Connection lost. The response was interrupted. Reconnect to try again.", { exact: true }).waitFor();
  await composer.waitFor();
  check(await composer.isEnabled(), "Reconnect must allow the next message");

  await composer.fill("hold");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  check(await page.evaluate(() => window.testSockets.filter((s) => s.readyState === 1).length) === 1,
    "Leaving chat must keep the current connection");
  await page.evaluate(() => window.testSockets.findLast((s) => s.readyState === 1)
    .emit({ type: "text", content: "Completed while viewing overview" }));
  await page.getByRole("button", { name: "Chat", exact: true }).click();
  await page.getByText("Completed while viewing overview", { exact: true }).waitFor();
  check(await composer.isEnabled(), "Hidden chat completion must unlock input");
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("agent-control-panel.chat-history.v1")));
  check(saved.some((conversation) => conversation.turns.length === 3), "All three turns must be persisted");

  await composer.fill("composing");
  await composer.dispatchEvent("keydown", { key: "Enter", isComposing: true });
  check(await composer.inputValue() === "composing", "IME confirmation must not send a message");

  await page.getByRole("button", { name: "Skills", exact: true }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export demo", exact: true }).click();
  const download = await downloadPromise;
  check(download.suggestedFilename() === "demo.md", "Skill export filename must be preserved");
  check(!(await download.failure()), "Authenticated skill download must succeed");

  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByText("401 Invalid gateway token", { exact: true }).waitFor();
  await page.getByLabel("Gateway API token", { exact: true }).fill("replacement-token");
  const reloaded = page.waitForEvent("domcontentloaded");
  await page.getByRole("button", { name: "Save gateway token", exact: true }).click();
  await reloaded;
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("input[type=password]")?.value === "replacement-token");
  await page.getByLabel("Main", { exact: true }).waitFor();
  await page.waitForFunction(() => Array.from(document.querySelectorAll("input")).some((input) => input.value === "test"));
  check(await page.evaluate(() => localStorage.getItem("agent_api_token")) === "replacement-token",
    "Gateway token must persist across reload");
  check(await page.evaluate(() => window.testSockets.findLast((s) => s.readyState === 1).url.includes("token=replacement-token")),
    "WebSocket must reconnect with the saved gateway token");

  await page.route("http://127.0.0.1:8000/api/approvals", (route) => route.fulfill({ json: {
    mode: "ask", pending: [{ id: "approval-test", command: "echo " + "complete-command-".repeat(20), session_id: "test", created_at: 0 }],
  } }));
  await page.route("http://127.0.0.1:8000/api/approvals/approval-test", (route) =>
    route.fulfill({ status: 503, json: { detail: "Approval unavailable" } }));
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "Approval unavailable" }).waitFor();
  check(await page.getByRole("button", { name: "Approve", exact: true }).isEnabled(),
    "Failed approval must remain available to retry");

  await page.addInitScript(() => {
    for (const method of ["getItem", "setItem", "removeItem", "clear"]) {
      Storage.prototype[method] = () => { throw new DOMException("Storage blocked", "SecurityError"); };
    }
  });
  await page.reload();
  await page.getByRole("button", { name: "Chat", exact: true }).click();
  await composer.fill("hold");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page.evaluate(() => window.testSockets.findLast((s) => s.readyState === 1)
    .emit({ type: "text", content: "Works without browser storage" }));
  await page.getByText("Works without browser storage", { exact: true }).waitFor();
  check(await composer.isEnabled(), "Blocked browser storage must not crash chat");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByLabel("Gateway API token", { exact: true }).fill("cannot-save");
  await page.getByRole("button", { name: "Save gateway token", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "Browser storage is unavailable" }).waitFor();
  return "PASS: socket lifecycle, errors, reconnect, partial responses, panel navigation, history, IME, authenticated export, token save and authenticated retry, approval failure, blocked storage";
}
