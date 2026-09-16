# Distill control panel

React and TypeScript interface for the Distill gateway. It includes streaming
chat, task graphs, approvals, schedules, memory, skills, logs, and settings.

## Run locally

Use Node.js 20.19+ on the 20.x line, or 22.12+ on newer lines, as specified in
`package.json`. From this directory:

```sh
npm ci
npm run dev
```

Start the Python gateway separately using the repository's installer or
[local setup instructions](../README.md). The panel currently connects to
`http://127.0.0.1:8000` and its WebSocket endpoint. Open the Vite URL shown in
the terminal, normally `http://localhost:5173`.

In **Settings → Gateway API token**, enter the `AGENT_API_TOKEN` from your
gateway environment file and save. The panel reloads to apply the token to
HTTP requests and chat connections. The token and chat history are stored in
this browser's local storage. The gateway requires a token by default;
provider authentication is configured separately.

## Checks

```sh
npm run lint
npm run build
```

Both checks run in CI on Linux and Windows. Build output goes to `dist/`.
`npm run preview` serves that output for local inspection.

Browser regressions live in
[`tests/control-panel-browser-checks.js`](../tests/control-panel-browser-checks.js).
They mock the gateway and WebSocket, so they need no model keys or running
backend. They cover connection recovery, partial responses, navigation during
a turn, history, token setup, skill exports, approvals, input composition,
and unavailable browser storage.

From the repository root, with Playwright CLI and its browser installed:

```sh
npm --prefix control-panel run dev -- --host 127.0.0.1 --port 5174
# In another terminal:
playwright-cli -s=control-panel-checks open about:blank
playwright-cli -s=control-panel-checks run-code --filename tests/control-panel-browser-checks.js
playwright-cli -s=control-panel-checks close
```

These browser checks are run separately from the lint/build CI job.
