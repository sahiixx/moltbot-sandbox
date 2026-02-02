# Kimi CLI — Install & Audit

This document provides a reproducible, safe installation path for `uv` and `kimi-cli`, and includes a short audit of commands I ran in this Codespace.

## Quick summary

- `uv` (installer) v0.9.28
- `kimi-cli` v1.5 (installed via `uv tool install`)
- `kimi` binary is available at `$HOME/.local/bin/kimi`

## Safe installation (reproducible)

1. Download & verify `uv` release for your platform:

```bash
# example (x86_64 Linux)
curl -LO https://github.com/astral-sh/uv/releases/download/0.9.28/uv-x86_64-unknown-linux-gnu.tar.gz
curl -LO https://github.com/astral-sh/uv/releases/download/0.9.28/uv-x86_64-unknown-linux-gnu.tar.gz.sha256
sha256sum -c uv-x86_64-unknown-linux-gnu.tar.gz.sha256
```

2. Extract and install user-local binaries (no sudo):

```bash
tar -xzf uv-x86_64-unknown-linux-gnu.tar.gz
mkdir -p "$HOME/.local/bin"
cp uv uvx "$HOME/.local/bin/"
chmod +x "$HOME/.local/bin/uv" "$HOME/.local/bin/uvx"
# Add uv to your PATH for the current session
export PATH="$HOME/.local/bin:$PATH"
```

3. Install Kimi via `uv`:

```bash
uv tool install --python 3.13 kimi-cli
source "$HOME/.local/bin/env"
echo 'test -f "$HOME/.local/bin/env" && source "$HOME/.local/bin/env"' >> ~/.profile
```

4. Verify:

```bash
kimi --version    # e.g., "kimi, version 1.5"
kimi --help
```

## Quick test

```bash
kimi --print --final-message-only --prompt "Summarize this repo and suggest 3 next steps for development"
```

Notes:
- Avoid piping unknown remote scripts directly to `sh` (e.g., `curl | sh`). Prefer verifying checksums or running in disposable containers.
- `kimi` may need API keys (Anthropic/OpenAI/AI Gateway). For Wrangler deployment, use `npx wrangler secret put ANTHROPIC_API_KEY`.

## Audit (what I ran)

I performed the actions below in a Codespace while validating behavior:

- Downloaded and inspected `https://code.kimi.com/install.sh` (it delegates to `uv` installer).
- Fetched `https://astral.sh/uv/install.sh` and inspected key parts (a small base64-decoded helper binary is used by the installer).
- Verified `uv` release checksums via GitHub releases (v0.9.28) and installed the `uv` binary to `$HOME/.local/bin`.
- Ran `uv tool install --python 3.13 kimi-cli` which installed `kimi-cli==1.5` and added two executables: `kimi` and `kimi-cli`.

Important command outputs captured during the run:

- `kimi --version` => `kimi, version 1.5`

- `kimi --help` shows available commands (`login`, `logout`, `term`, `acp`, `info`, `mcp`, `web`) and global options including `--prompt`/`--print` and `--final-message-only` for non-interactive runs.

- `kimi chat ...` is not a built-in command on this release; prefer `--prompt` + `--print` for non-interactive prompts.

## Want me to...

- Add automated tests that verify `kimi` runs in CI (smoke test)? ✅
- Create a minimal sample config `~/.kimi/config.toml` for local dev? ✅
- Run a demo prompt with a configured API key (I can run it if you provide an API key or set the `ANTHROPIC_API_KEY` secret)? ✅

If you'd like, I can open a PR that adds this file and the README snippet into the repo so it is version controlled.