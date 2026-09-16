const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const root = path.resolve(__dirname, "..");
const bin = path.join(root, "bin", "distill.js");

function run(args, input = "") {
  return spawnSync(process.execPath, [bin, ...args], {
    cwd: root,
    input,
    encoding: "utf8",
    env: {
      ...process.env,
      NO_COLOR: "1"
    }
  });
}

function runWithEnv(args, env, input = "") {
  return spawnSync(process.execPath, [bin, ...args], {
    cwd: root,
    input,
    encoding: "utf8",
    env: {
      ...process.env,
      ...env,
      NO_COLOR: "1"
    }
  });
}

function tempInstallDir(name) {
  return path.join(fs.mkdtempSync(path.join(os.tmpdir(), "distill-cli-")), name);
}

function assertIncludes(text, expected) {
  assert(
    text.includes(expected),
    `Expected output to include ${JSON.stringify(expected)}.\nActual output:\n${text}`
  );
}

{
  const { __testing, defaultProviderSettings } = require(path.join(root, "lib", "distill-cli.js"));
  const installDir = fs.mkdtempSync(path.join(os.tmpdir(), "distill-env-update-"));
  const envPath = path.join(installDir, "an-api.env");
  const original = 'CUSTOM_SETTING=keep\n export AGENT_MODEL = "old-model"\nAGENT_PLANNING_MAX_TOKENS=1\nAGENT_ARTIFACT_MAX_TOKENS=2\nexport AGENT_API_TOKEN = "" # unset\n';
  fs.writeFileSync(envPath, original);
  const config = {
    installDir, sandbox: "on", messaging: "none", memory: "lite",
    providerSettings: defaultProviderSettings("ollama"), messagingSettings: {}
  };
  __testing.writeEnvFile(config);
  const content = fs.readFileSync(envPath, "utf8");
  assertIncludes(content, "CUSTOM_SETTING=keep");
  assert(!content.includes("old-model"));
  assert.strictEqual((content.match(/^AGENT_PLANNING_MAX_TOKENS=/gm) || []).length, 1);
  assert.strictEqual((content.match(/^AGENT_ARTIFACT_MAX_TOKENS=/gm) || []).length, 1);
  const backup = fs.readdirSync(installDir).find((name) => name.startsWith("an-api.env.bak."));
  assert.strictEqual(fs.readFileSync(path.join(installDir, backup), "utf8"), original);
  const token = content.match(/^AGENT_API_TOKEN=([a-f0-9]{64})$/m)?.[1];
  assert(token, "installation must generate a gateway token when the existing value is blank");
  __testing.writeEnvFile(config);
  assertIncludes(fs.readFileSync(envPath, "utf8"), `AGENT_API_TOKEN=${token}\n`);
  const customToken = "export AGENT_API_TOKEN = 'existing-$literal-token'";
  fs.writeFileSync(envPath, `${customToken}\n`);
  __testing.writeEnvFile(config);
  const preservedToken = fs.readFileSync(envPath, "utf8");
  assertIncludes(preservedToken, customToken);
  assert(!/^AGENT_API_TOKEN=/m.test(preservedToken), "existing nonempty tokens must not be replaced");
}

{
  const { __testing } = require(path.join(root, "lib", "distill-cli.js"));
  const installDir = fs.mkdtempSync(path.join(os.tmpdir(), "distill-compose-env-"));
  const envPath = path.join(installDir, ".env");
  const previous = process.env.NEO4J_PASSWORD;
  try {
    delete process.env.NEO4J_PASSWORD;
    __testing.ensureNeo4jPassword({ installDir, dryRun: true });
    assert(!fs.existsSync(envPath), "dry runs must not create configuration files");
    __testing.ensureNeo4jPassword({ installDir });
    const generated = fs.readFileSync(envPath, "utf8");
    assert.match(generated, /^NEO4J_PASSWORD=[a-f0-9]{48}\n$/);
    __testing.ensureNeo4jPassword({ installDir });
    assert.strictEqual(fs.readFileSync(envPath, "utf8"), generated, "restarts must preserve passwords");
    for (const value of ["", '""', "'' # unset", "# unset"]) {
      fs.writeFileSync(envPath, `OTHER_SETTING=keep\nNEO4J_PASSWORD=${value}`);
      __testing.ensureNeo4jPassword({ installDir });
      const replaced = fs.readFileSync(envPath, "utf8");
      assertIncludes(replaced, "OTHER_SETTING=keep\n");
      assert.match(replaced, /^NEO4J_PASSWORD=[a-f0-9]{48}$/m);
      assert.strictEqual((replaced.match(/^NEO4J_PASSWORD=/gm) || []).length, 1);
    }
    const custom = 'OTHER_SETTING=keep\nexport NEO4J_PASSWORD = "existing-password"\n';
    fs.writeFileSync(envPath, custom);
    __testing.ensureNeo4jPassword({ installDir });
    assert.strictEqual(fs.readFileSync(envPath, "utf8"), custom);
    fs.unlinkSync(envPath);
    process.env.NEO4J_PASSWORD = "external-password";
    __testing.ensureNeo4jPassword({ installDir });
    assert(!fs.existsSync(envPath), "an inherited password must not be replaced");
  } finally {
    if (previous === undefined) delete process.env.NEO4J_PASSWORD;
    else process.env.NEO4J_PASSWORD = previous;
  }
}

// Run the pipe regression in a subprocess with a timeout so the original
// deadlock fails the test instead of hanging the entire test suite.
{
  const modulePath = path.join(root, "lib", "distill-cli.js");
  const childCode = `
    const assert = require('assert');
    const { __testing } = require(${JSON.stringify(modulePath)});
    (async () => {
      await __testing.run(process.execPath, ['-e', "process.stdout.write('x'.repeat(2 * 1024 * 1024)); process.stderr.write('y'.repeat(2 * 1024 * 1024));"], { stdio: 'pipe' });
      await assert.rejects(
        __testing.run(process.execPath, ['-e', "process.stderr.write('dependency failure detail'); process.exitCode = 7;"], { stdio: 'pipe' }),
        /code 7[\\s\\S]*dependency failure detail/
      );
      const settings = await __testing.collectMessagingSettings({ question: async () => 'allowed-value' }, 'all');
      for (const key of ['telegramAllowed', 'discordAllowed', 'slackAllowed', 'emailAllowed']) {
        assert.strictEqual(settings[key], 'allowed-value');
      }
    })().catch((error) => { console.error(error); process.exitCode = 1; });
  `;
  const result = spawnSync(process.execPath, ["-e", childCode], { cwd: root, encoding: "utf8", timeout: 15000 });
  assert.strictEqual(result.status, 0, result.error ? result.error.message : result.stderr);
}

{
  const installDir = tempInstallDir("quickstart");
  const result = run([
    "install",
    "--dry-run",
    "--yes",
    "--no-start",
    "--install-dir",
    installDir,
    "--provider",
    "openai",
    "--sandbox",
    "on",
    "--messaging",
    "none"
  ]);
  assert.strictEqual(result.status, 0, result.stderr);
  assertIncludes(result.stdout, "DISTILL");
  assertIncludes(result.stdout, "Security Notice");
  assertIncludes(result.stdout, "[dry-run] git clone --depth 1 --single-branch --branch master https://github.com/Aspct3434/Distill-Agent.git");
  assertIncludes(result.stdout, 'AGENT_MODEL="gpt-4o"');
  assertIncludes(result.stdout, 'AGENT_MAX_TOKENS="2048"');
  assertIncludes(result.stdout, 'AGENT_PLANNING_MAX_TOKENS="1024"');
  assertIncludes(result.stdout, 'AGENT_ARTIFACT_MAX_TOKENS="20000"');
  assertIncludes(result.stdout, 'AGENT_FINAL_MAX_TOKENS="1536"');
  assertIncludes(result.stdout, 'AGENT_SANDBOX_HOST_FALLBACK="false"');
  assertIncludes(result.stdout, 'AGENT_USE_HYBRID_MEMORY="false"');
  assertIncludes(result.stdout, "Start later with: npx @aspct/distill-agent start");
  assertIncludes(result.stdout, "Installation Summary");
  assertIncludes(result.stdout, "missing");
  assertIncludes(result.stdout, "Copy AGENT_API_TOKEN");
  assert(!fs.existsSync(path.join(installDir, "an-api.env")), "dry runs must not persist a gateway token");
}

{
  const installDir = tempInstallDir("manual");
  const result = run([
    "install",
    "--dry-run",
    "--yes",
    "--mode",
    "manual",
    "--no-start",
    "--install-dir",
    installDir,
    "--provider",
    "vllm",
    "--sandbox",
    "off",
    "--messaging",
    "all"
  ]);
  assert.strictEqual(result.status, 0, result.stderr);
  assertIncludes(result.stdout, 'OPENAI_API_BASE="http://localhost:8001/v1"');
  assertIncludes(result.stdout, 'AGENT_SANDBOX_HOST_FALLBACK="true"');
  assertIncludes(result.stdout, "TELEGRAM_BOT_TOKEN=");
  assertIncludes(result.stdout, "DISCORD_BOT_TOKEN=");
  assertIncludes(result.stdout, "SLACK_BOT_TOKEN=");
  assertIncludes(result.stdout, "EMAIL_ADDRESS=");
}

{
  const installDir = tempInstallDir("no-env-secret-import");
  const result = runWithEnv([
    "install",
    "--dry-run",
    "--yes",
    "--no-start",
    "--install-dir",
    installDir,
    "--provider",
    "openai",
    "--sandbox",
    "on",
    "--messaging",
    "none"
  ], { OPENAI_API_KEY: "sk-should-not-be-imported" });
  assert.strictEqual(result.status, 0, result.stderr);
  assertIncludes(result.stdout, "OPENAI_API_KEY=");
  assert(!result.stdout.includes("sk-should-not-be-imported"));
}

{
  const installDir = tempInstallDir("cancelled");
  const result = run(["install", "--dry-run", "--no-start", "--install-dir", installDir], "n\n");
  assert.notStrictEqual(result.status, 0);
  assertIncludes(result.stderr, "Installation cancelled.");
}

{
  const installDir = tempInstallDir("hybrid-memory");
  const result = run([
    "install",
    "--dry-run",
    "--yes",
    "--no-start",
    "--install-dir",
    installDir,
    "--provider",
    "openai",
    "--sandbox",
    "on",
    "--messaging",
    "none",
    "--memory",
    "hybrid"
  ]);
  assert.strictEqual(result.status, 0, result.stderr);
  assertIncludes(result.stdout, 'AGENT_USE_HYBRID_MEMORY="true"');
}

{
  const installDir = tempInstallDir("deepseek");
  const result = run([
    "install",
    "--dry-run",
    "--yes",
    "--no-start",
    "--install-dir",
    installDir,
    "--provider",
    "deepseek",
    "--sandbox",
    "on",
    "--messaging",
    "none"
  ]);
  assert.strictEqual(result.status, 0, result.stderr);
  assertIncludes(result.stdout, 'AGENT_MODEL="deepseek/deepseek-chat"');
  assertIncludes(result.stdout, "DEEPSEEK_API_KEY=");
}

{
  const installDir = tempInstallDir("xai");
  const result = run([
    "install",
    "--dry-run",
    "--yes",
    "--no-start",
    "--install-dir",
    installDir,
    "--provider",
    "xai",
    "--sandbox",
    "on",
    "--messaging",
    "none"
  ]);
  assert.strictEqual(result.status, 0, result.stderr);
  assertIncludes(result.stdout, 'AGENT_MODEL="xai/grok-4"');
  assertIncludes(result.stdout, "XAI_API_KEY=");
}

{
  const result = run(["help"]);
  assert.strictEqual(result.status, 0, result.stderr);
  assertIncludes(result.stdout, "distill install");
  assertIncludes(result.stdout, "--memory lite|hybrid");
  assertIncludes(result.stdout, "distill                         Launch the interactive Terminal UI");
  assertIncludes(result.stdout, "npx @aspct/distill-agent install");
  assertIncludes(result.stdout, "npx @aspct/distill-agent doctor");
}

{
  const { parseArgs } = require(path.join(root, "lib", "distill-cli.js"));
  assert.strictEqual(parseArgs([]).command, "tui");
  const parsed = parseArgs(["--url", "ws://localhost:9000/ws/stream", "--theme", "ocean"]);
  assert.strictEqual(parsed.command, "tui");
  assert.strictEqual(parsed.options.url, "ws://localhost:9000/ws/stream");
  assert.strictEqual(parsed.options.theme, "ocean");
}

{
  const { __testing } = require(path.join(root, "lib", "distill-cli.js"));
  const fakeDir = fs.mkdtempSync(path.join(os.tmpdir(), "distill-fake-python-"));
  const workingPython = path.join(fakeDir, "working-python.js");
  const brokenPython = path.join(fakeDir, "broken-python.js");
  fs.writeFileSync(
    workingPython,
    [
      "const fs = require('fs');",
      "const args = process.argv.slice(2);",
      "if (args[0] === '-m' && args[1] === 'venv') { fs.mkdirSync(args[2], { recursive: true }); process.exit(0); }",
      "process.exit(0);"
    ].join("\n"),
    "utf8"
  );
  fs.writeFileSync(
    brokenPython,
    [
      "const args = process.argv.slice(2);",
      "if (args[0] === '-m' && args[1] === 'venv') process.exit(1);",
      "process.exit(0);"
    ].join("\n"),
    "utf8"
  );

  assert.strictEqual(__testing.pythonHasVenv(process.execPath, [workingPython]), true);
  assert.strictEqual(__testing.pythonHasVenv(process.execPath, [brokenPython]), false);
}

{
  const { __testing } = require(path.join(root, "lib", "distill-cli.js"));
  assert.strictEqual(__testing.nodeMeetsHostLocalUiMinimum("v18.19.1"), false);
  assert.strictEqual(__testing.nodeMeetsHostLocalUiMinimum("v20.18.0"), false);
  assert.strictEqual(__testing.nodeMeetsHostLocalUiMinimum("v20.19.0"), true);
  assert.strictEqual(__testing.nodeMeetsHostLocalUiMinimum("v22.11.0"), false);
  assert.strictEqual(__testing.nodeMeetsHostLocalUiMinimum("v22.12.0"), true);
  assert.strictEqual(__testing.nodeMeetsHostLocalUiMinimum("v24.0.0"), true);
}

// Secret prompts echo one "*" per character on an interactive terminal so the
// user gets visible feedback without revealing the token.
{
  const { EventEmitter } = require("events");
  const { Prompter } = require(path.join(root, "lib", "distill-cli.js"));

  const input = new EventEmitter();
  input.isTTY = true;
  input.isRaw = false;
  input.setRawMode = (v) => { input.isRaw = v; };
  input.resume = () => {};
  input.pause = () => {};
  input.setEncoding = () => {};

  let out = "";
  const output = { write: (t) => { out += t; } };

  const prompter = new Prompter({ input, output });
  const promise = prompter.secretQuestion("Token: ");
  input.emit("data", "abc");                          // 3 chars → "***"
  input.emit("data", String.fromCharCode(127));       // backspace → erase one
  input.emit("data", "Xy");                            // 2 chars → "**"
  input.emit("data", "\r");                            // Enter → submit

  promise.then((value) => {
    const stars = (out.match(/\*/g) || []).length;
    assert.strictEqual(value, "abXy", "secret value should reflect typed input minus backspace");
    assert.strictEqual(stars, 5, "should echo one '*' per typed character");
    assert(out.includes("\b \b"), "backspace should erase a masked character");
    assert.strictEqual(input.isRaw, false, "raw mode must be restored after input");
    console.log("installer CLI tests passed");
  }).catch((err) => {
    console.error(err);
    process.exit(1);
  });
}

// Local-mode start must refuse to launch when a port is already held, instead
// of spawning a second instance that fails to bind (the EADDRINUSE collision).
{
  const net = require("net");
  const { __testing } = require(path.join(root, "lib", "distill-cli.js"));
  const PORT = 53999;

  (async () => {
    try {
      // Free port → reported bindable quickly.
      assert.strictEqual(await __testing.waitForPortFree(PORT, 1000), true,
        "an unused port should be reported free");

      const server = net.createServer();
      await new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(PORT, "0.0.0.0", resolve);
      });

      // Held port → reported busy (no infinite wait).
      assert.strictEqual(await __testing.waitForPortFree(PORT, 300), false,
        "a held port should be reported busy");

      // dry-run skips the check entirely.
      await __testing.assertPortsAvailableForLocal({ dryRun: true });

      server.close();
      console.log("port-guard tests passed");
    } catch (err) {
      console.error(err);
      process.exit(1);
    }
  })();
}
