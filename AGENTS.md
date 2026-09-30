# Agent working guide

This repository is a Termux Python application with a native Termux:GUI overlay. Use this guide for repository changes; use [README.md](README.md) for the user-facing contract.

## Work sequence

1. Check `git status --short --branch`. Work on `main`; if the checkout is elsewhere, ask for direction before changing branches. Proceed when unrelated edits are identified and protected.
2. Architecture: read [docs/architecture.md](docs/architecture.md) before changing hook ingestion, session state, IPC, daemon recovery, GUI layout or touch, or installation. Then inspect the owning code and tests. For CLI or interaction changes, also read the matching section of `README.md`. Proceed when the affected boundary and contract are clear.
3. Change the owning boundary and add a regression test for changed behavior. Preserve the event-driven path, the hook helper's fail-open behavior, one daemon, and the GUI thread's ownership of Termux:GUI calls. Update both user guides when user-visible behavior changes. Finish this step when the change and its test express the same behavior.
4. Run the affected tests, then `python -m unittest discover -s tests -v` and `git diff --check`. For GUI or end-to-end changes on a Termux device, run `bash ./install.sh` from the checkout to deploy the source into a private runtime release and restart the daemon; then check `codex-pet status`, run `codex-pet test` with other sessions isolated, and inspect recent `~/.cache/codex-pet/pet.log` entries. Verify real touch gestures with a person when shell input injection is unavailable. Finish when checks pass and any physical verification gap is recorded.
5. Stage only task files. Commit directly on `main` and push `origin main` after validation; create no topic branch or PR. Finish when the worktree is clean and `main` matches the pushed remote. Report changed behavior, checks, and any device-only verification gap.

## Source of truth

- Read code and tests for exact APIs, constants, and CLI output; keep this file focused on process.
- Keep runtime files in `~/.cache/codex-pet/`, saved position in `~/.config/codex-pet/`, and Codex hooks in the user's existing Codex configuration. Back up and merge user configuration through the installer rather than replacing it.
