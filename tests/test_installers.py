from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import tomllib
from pathlib import Path

import pytest
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASH_INSTALLER = PROJECT_ROOT / "scripts" / "install.sh"
BASH_BOOTSTRAP = PROJECT_ROOT / "scripts" / "bootstrap.sh"
POWERSHELL_INSTALLER = PROJECT_ROOT / "scripts" / "install.ps1"
POWERSHELL_BOOTSTRAP = PROJECT_ROOT / "scripts" / "bootstrap.ps1"


def _run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=True,
    )


def _bash() -> str:
    candidates = [shutil.which("bash")]
    git = shutil.which("git")
    if os.name == "nt" and git:
        candidates.append(str(Path(git).parent.parent / "bin" / "bash.exe"))
    for bash in candidates:
        if bash and Path(bash).is_file():
            probe = subprocess.run([bash, "--version"], capture_output=True)
            if probe.returncode == 0:
                return bash
    pytest.skip("bash is not available or not usable")


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is not available")
    return shell


def _ps_args(shell: str) -> list[str]:
    args = [shell, "-NoLogo", "-NoProfile", "-NonInteractive"]
    if os.name == "nt":
        args.extend(["-ExecutionPolicy", "Bypass"])
    return args


def test_bash_scripts_parse() -> None:
    bash = _bash()
    # Relative POSIX paths so WSL bash on Windows can resolve them (cwd is PROJECT_ROOT).
    _run([bash, "-n", BASH_INSTALLER.relative_to(PROJECT_ROOT).as_posix()])
    _run([bash, "-n", BASH_BOOTSTRAP.relative_to(PROJECT_ROOT).as_posix()])


def test_bash_interactive_choices_write_selected_configuration(tmp_path: Path) -> None:
    env_file = tmp_path / "agent.env"
    result = subprocess.run(
        [_bash(), "scripts/install.sh", "--no-start", "--env-file", Path(os.path.relpath(env_file, PROJECT_ROOT)).as_posix()],
        cwd=PROJECT_ROOT,
        env={**os.environ, **{f"AGENT_INSTALL_{key}": "" for key in ("PROVIDER", "SANDBOX", "MESSAGING", "MEMORY")}},
        input=b"2\nn\n1\n1\n\n\n",
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
    config = env_file.read_text(encoding="utf-8")
    assert 'AGENT_MODEL="ollama/llama3.2"' in config
    assert 'AGENT_USE_HYBRID_MEMORY="false"' in config
    assert 'AGENT_SANDBOX_HOST_FALLBACK="true"' in config
    assert "# Messaging mode: none" in config
    assert b"Choose model provider:" in result.stderr
    assert b"Choose messaging app:" in result.stderr
    assert b"Enable local hybrid memory" in result.stderr


def test_package_versions_match() -> None:
    python_package = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    npm_package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    assert python_package["project"]["version"] == npm_package["version"]


def test_quickstart_generates_blank_secrets_and_preserves_them(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    script = scripts_dir / "quickstart.sh"
    shutil.copy(PROJECT_ROOT / "scripts" / "quickstart.sh", script)
    (tmp_path / "an-api.env.example").write_text("AGENT_API_TOKEN=\nCUSTOM_SETTING=keep\n", encoding="utf-8")
    (tmp_path / ".env").write_text("NEO4J_PASSWORD=", encoding="utf-8")
    command = [
        _bash(), "-c", 'export PATH="/usr/bin:/bin:$PATH"; docker() { return 0; }; export -f docker; "$BASH" "$1"',
        "quickstart-test", Path(os.path.relpath(script, PROJECT_ROOT)).as_posix(),
    ]
    result = _run(command)
    agent_env = dotenv_values(tmp_path / "an-api.env")
    compose_env = dotenv_values(tmp_path / ".env")
    assert len(agent_env["AGENT_API_TOKEN"]) == 64
    assert len(compose_env["NEO4J_PASSWORD"]) == 48
    assert agent_env["CUSTOM_SETTING"] == "keep"
    assert f"API token     : {agent_env['AGENT_API_TOKEN']}" in result.stdout
    _run(command)
    assert dotenv_values(tmp_path / "an-api.env") == agent_env
    assert dotenv_values(tmp_path / ".env") == compose_env


@pytest.mark.parametrize("installer", ["bash", "powershell"])
@pytest.mark.parametrize("existing_token", [None, "", "existing-$literal-token"])
def test_shell_installers_provision_api_token_and_forward_custom_env(
    tmp_path: Path, installer: str, existing_token: str | None,
) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    env_file = tmp_path / "config with spaces" / "custom.env"
    if existing_token is not None:
        env_file.parent.mkdir()
        env_file.write_text(f"export AGENT_API_TOKEN = '{existing_token}'\n", encoding="utf-8")
    captured_env_path = tmp_path / "compose-env-path.txt"
    if installer == "bash":
        script = scripts_dir / "install.sh"
        shutil.copy(BASH_INSTALLER, script)
        command = [
            _bash(), "-c",
            'export PATH="/usr/bin:/bin:$PATH"; '
            'docker() { printf "%s\\n" "$AGENT_ENV_FILE" > "$ROOT_DIR/compose-env-path.txt"; }; '
            'export -f docker; "$BASH" "$1" --provider ollama --sandbox on --messaging none --memory lite --env-file "$2"',
            "installer-test", Path(os.path.relpath(script, PROJECT_ROOT)).as_posix(),
            Path(os.path.relpath(env_file, PROJECT_ROOT)).as_posix(),
        ]
    else:
        script = scripts_dir / "install.ps1"
        shutil.copy(POWERSHELL_INSTALLER, script)
        script_literal = str(script).replace("'", "''")
        env_literal = str(env_file).replace("'", "''")
        capture_literal = str(captured_env_path).replace("'", "''")
        command = [
            *_ps_args(_powershell()), "-Command",
            "function Read-Host { return '' }; "
            f"function docker {{ Set-Content -LiteralPath '{capture_literal}' -Value $env:AGENT_ENV_FILE }}; "
            f"& '{script_literal}' -Provider ollama -Sandbox on -Messaging none -Memory lite -EnvFile '{env_literal}'",
        ]
    result = subprocess.run(command, cwd=PROJECT_ROOT, input=b"\n\n", capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    values = dotenv_values(env_file, encoding="utf-8-sig")
    token = values["AGENT_API_TOKEN"]
    if existing_token:
        assert token == existing_token
    else:
        assert token is not None and len(token) == 64
        assert all(char in "0123456789abcdef" for char in token)
    assert b"Copy AGENT_API_TOKEN" in result.stdout
    assert captured_env_path.read_text(encoding="utf-8-sig").strip().replace("\\", "/").endswith("/config with spaces/custom.env")
    second_run = subprocess.run(command, cwd=PROJECT_ROOT, input=b"\n\n", capture_output=True)
    assert second_run.returncode == 0, second_run.stderr.decode(errors="replace")
    assert dotenv_values(env_file, encoding="utf-8-sig")["AGENT_API_TOKEN"] == token


@pytest.mark.parametrize("installer", ["bash", "powershell"])
def test_local_installers_pass_custom_env_to_uvicorn(tmp_path: Path, installer: str) -> None:
    if installer == "bash" and os.name == "nt":
        pytest.skip("Bash host-local startup requires POSIX executable and path semantics")
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (tmp_path / "control-panel").mkdir()
    (tmp_path / "logs").mkdir()
    env_file = tmp_path / "config with spaces" / "custom.env"
    env_file.parent.mkdir()
    # This is dotenv data; loading it must never execute a shell substitution.
    env_file.write_text('CUSTOM_VALUE="$(touch sourced-env-marker)"\n', encoding="utf-8")
    captured_args = tmp_path / "backend-args.txt"
    if installer == "bash":
        script = scripts_dir / "install.sh"
        shutil.copy(BASH_INSTALLER, script)
        fake_bin = tmp_path / ".run-venv" / "bin"
        fake_bin.mkdir(parents=True)
        for name in ("python", "uv", "npm"):
            fake = fake_bin / name
            fake.write_text(
                '#!/usr/bin/env bash\nif [[ "$1" == "-m" && "$2" == "uvicorn" ]]; then '
                'printf "%s\\n" "$@" > "$PWD/backend-args.txt"; fi\nexit 0\n', encoding="utf-8",
            )
            fake.chmod(0o755)
        command = [
            _bash(), "-c", 'export PATH="/usr/bin:/bin:$PATH"; '
            'test_root="$(cd "$(dirname "$1")/.." && pwd)"; '
            'export AGENT_PYTHON="$test_root/.run-venv/bin/python"; '
            'export PATH="$test_root/.run-venv/bin:$PATH"; '
            '"$BASH" "$1" --provider ollama --sandbox off --messaging none --memory lite --env-file "$2"',
            "installer-test", Path(os.path.relpath(script, PROJECT_ROOT)).as_posix(),
            Path(os.path.relpath(env_file, PROJECT_ROOT)).as_posix(),
        ]
    else:
        script = scripts_dir / "install.ps1"
        shutil.copy(POWERSHELL_INSTALLER, script)
        script_literal = str(script).replace("'", "''")
        env_literal = str(env_file).replace("'", "''")
        capture_literal = str(captured_args).replace("'", "''")
        command = [
            *_ps_args(_powershell()), "-Command",
            "function Read-Host { return '' }; function py {}; function uv {}; function npm {}; "
            "function Start-Process { param($FilePath, $ArgumentList, $WorkingDirectory, "
            "$RedirectStandardOutput, $RedirectStandardError, $WindowStyle) "
            f"if ($ArgumentList -contains 'uvicorn') {{ [System.IO.File]::WriteAllLines('{capture_literal}', [string[]]$ArgumentList) }} }}; "
            f"& '{script_literal}' -Provider ollama -Sandbox off -Messaging none -Memory lite -EnvFile '{env_literal}'",
        ]
    result = subprocess.run(command, cwd=PROJECT_ROOT, input=b"\n\n", capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    deadline = time.monotonic() + 5
    while not captured_args.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    args = captured_args.read_text(encoding="utf-8-sig").splitlines()
    forwarded_env = args[args.index("--env-file") + 1].strip('"').replace("\\", "/")
    assert forwarded_env.endswith("/config with spaces/custom.env")
    assert not (tmp_path / "sourced-env-marker").exists()


def test_pywin32_requirement_is_windows_only() -> None:
    text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert 'pywin32==311; sys_platform == "win32"' in text
    assert "\npywin32==311\n" not in text


def test_powershell_scripts_parse() -> None:
    shell = _powershell()
    for path in (POWERSHELL_INSTALLER, POWERSHELL_BOOTSTRAP):
        command = f"$null = [scriptblock]::Create([System.IO.File]::ReadAllText('{path.as_posix()}'))"
        _run([*_ps_args(shell), "-Command", command])


@pytest.mark.parametrize(
    "provider,expected",
    [
        ("kimi", 'AGENT_MODEL="moonshot/kimi-k2.6"'),
        ("ollama", 'AGENT_MODEL="ollama/llama3.2"'),
        ("openrouter", 'OPENROUTER_API_KEY='),
        ("openai", 'AGENT_MODEL="gpt-4o"'),
        ("anthropic", 'ANTHROPIC_API_KEY='),
        ("gemini", 'GEMINI_API_KEY='),
        ("deepseek", 'AGENT_MODEL="deepseek/deepseek-chat"'),
        ("groq", 'AGENT_MODEL="groq/llama-3.3-70b-versatile"'),
        ("xai", 'AGENT_MODEL="xai/grok-4"'),
        ("mistral", 'AGENT_MODEL="mistral/mistral-large-latest"'),
        ("vllm", 'OPENAI_API_BASE="http://localhost:8001/v1"'),
    ],
)
def test_powershell_installer_dry_run_provider_choices(provider: str, expected: str, tmp_path: Path) -> None:
    result = _run(
        [
            *_ps_args(_powershell()),
            "-File",
            str(POWERSHELL_INSTALLER),
            "-DryRun",
            "-NoStart",
            "-Provider",
            provider,
            "-Sandbox",
            "on",
            "-Messaging",
            "none",
            "-EnvFile",
            str(tmp_path / "an-api.env"),
        ]
    )

    assert expected in result.stdout
    assert "AGENT_SANDBOX=" in result.stdout
    assert 'AGENT_SANDBOX_HOST_FALLBACK="false"' in result.stdout


def test_powershell_bootstrap_dry_run_forwards_options(tmp_path: Path) -> None:
    result = _run(
        [
            *_ps_args(_powershell()),
            "-File",
            str(POWERSHELL_BOOTSTRAP),
            "-DryRun",
            "-NoStart",
            "-RepoUrl",
            "https://github.com/example/agent-ai.git",
            "-InstallDir",
            str(tmp_path / "agent-ai"),
            "-Provider",
            "openrouter",
            "-Sandbox",
            "off",
            "-Messaging",
            "both",
        ]
    )

    assert "git clone --depth 1 --single-branch --branch master https://github.com/example/agent-ai.git" in result.stdout
    assert "scripts\\install.ps1" in result.stdout
    assert "-Provider openrouter" in result.stdout
    assert "-Sandbox off" in result.stdout
    assert "-Messaging both" in result.stdout
    assert "-NoStart" in result.stdout


def test_docker_compose_config_accepts_temp_env_file(tmp_path: Path) -> None:
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("docker is not available")
    probe = subprocess.run([docker, "compose", "version"], capture_output=True)
    if probe.returncode != 0:
        pytest.skip("docker compose is not available")

    env_file = tmp_path / "an-api.env"
    env_file.write_text(
        "AGENT_MODEL=moonshot/kimi-k2.6\nFAST_AGENT_MODEL=moonshot/kimi-k2.6\nSTRONG_AGENT_MODEL=moonshot/kimi-k2.6\n",
        encoding="utf-8",
    )
    result = _run(
        [docker, "compose", "config"],
        env={"AGENT_ENV_FILE": str(env_file), "NEO4J_PASSWORD": "test-password"},
    )

    assert "control_panel:" in result.stdout
    assert "5173" in result.stdout


def test_docker_compose_config_requires_neo4j_password(tmp_path: Path) -> None:
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("docker is not available")
    probe = subprocess.run([docker, "compose", "version"], capture_output=True)
    if probe.returncode != 0:
        pytest.skip("docker compose is not available")

    env_file = tmp_path / "an-api.env"
    env_file.write_text("AGENT_MODEL=moonshot/kimi-k2.6\n", encoding="utf-8")
    # Point --env-file at an empty file so neither the shell env nor a local
    # .env can supply NEO4J_PASSWORD.
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    merged = {k: v for k, v in os.environ.items() if k != "NEO4J_PASSWORD"}
    merged["AGENT_ENV_FILE"] = str(env_file)
    result = subprocess.run(
        [docker, "compose", "--env-file", str(empty_env), "config"],
        cwd=PROJECT_ROOT,
        env=merged,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "NEO4J_PASSWORD" in result.stderr


def test_readme_empty_pc_commands_use_bootstrap() -> None:
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "npx @aspct/distill-agent install" in text
    assert "npx --yes github:Aspct3434/Distill-Agent install" in text
    assert "npx @aspct/distill-agent doctor" in text
    assert "npm i -g @aspct/distill-agent" in text
    assert "scripts/bootstrap.ps1" in text
    assert "scripts/bootstrap.sh" in text
    assert "https://raw.githubusercontent.com/Aspct3434/Distill-Agent/master/scripts/bootstrap.ps1" in text
    assert "https://raw.githubusercontent.com/Aspct3434/Distill-Agent/master/scripts/bootstrap.sh" in text
    assert "scripts/install.ps1 | iex" not in text
    assert "scripts/install.sh | bash" not in text
