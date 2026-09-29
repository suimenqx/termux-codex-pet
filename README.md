# Codex Pet for Termux

A small, persistent robot overlay for Codex CLI on Android. Codex lifecycle hooks send short JSON events over a private Unix socket to one Termux:GUI daemon. The daemon keeps session state in memory; it does not poll Codex or start a GUI for each hook. Android notifications appear only when the overlay cannot be reached for approval or completion events.

## Install

Requirements: Termux and the matching-signature Termux:GUI app. In Android settings enable **Termux:GUI → Advanced → Display over other apps**. The script installs `termuxgui` with pip if needed; it does not install an APK.

```sh
git clone https://github.com/suimenqx/termux-codex-pet.git ~/codex-pet
cd ~/codex-pet
./install.sh
```

The installer creates `~/.local/bin/codex-pet` and `~/.local/bin/codex-pet-event`, with links in Termux's `bin` directory so the commands are on `PATH`. Config lives under `~/.config/codex-pet/`, and the socket/log under `~/.cache/codex-pet/`. It backs up any Codex config file it changes. Existing Codex settings and unrelated hooks are retained. On Codex 0.156.1, hooks are enabled by default, but new hooks require review and trust. **Restart Codex, then run `/hooks` and trust the `~/.codex/hooks.json` hooks.** The Pet works through its CLI before that step.

## Commands

```sh
codex-pet start       # safe to call repeatedly
codex-pet stop
codex-pet restart
codex-pet status      # daemon, GUI, state, session count
codex-pet test        # show every state in sequence
```

Tap the Pet to open or close its compact detail bubble. The bubble normally opens on the left and moves to the right near the left edge. It grows to fit its short message, opens automatically for approval and completion, and closes when those states end. Touching an automatic detail keeps it open until you close it. Drag the Pet to a new position; the position is saved in `~/.config/codex-pet/config.json` and restored on restart. The icon-only Pet is about 64 dp wide. A working session changes its color and animates slowly; two or more working sessions show a count badge. Any approval has priority. Done and interrupted return to idle after a short hold. The test command can show `error`; Codex hooks do not infer errors from unrelated failures.

## Hook integration

The installer adds the same `codex-pet-event` command for `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, `Stop`, `Interrupt`, and `SessionEnd`. The helper reads Codex's JSON from stdin, extracts the session/turn/cwd and a short assistant summary where available, and exits successfully even if the Pet fails. `SessionEnd` removes that session. If Android kills the daemon, the next hook starts it again under a lock and sends its event. The hooks observe Codex; they never approve, deny, or change execution.

## Troubleshooting

- `codex-pet status` reports `GUI=unavailable`: the daemon retries automatically with a short backoff; run `codex-pet start` to retry immediately. If it still fails, confirm the Android overlay permission and compatible app signatures, then run `codex-pet restart`.
- `codex-pet test` shows the six states without running a Codex turn.
- Read `~/.cache/codex-pet/pet.log` for GUI or IPC errors. The log rotates at about 512 KB.
- If a Codex prompt does not change the Pet, restart Codex and use `/hooks` to review/trust the new hook definition. Check `codex features list` for `hooks` and inspect `~/.codex/hooks.json`.
- If Termux:GUI is killed, send another Codex prompt or run `codex-pet start`.

## Uninstall

```sh
cd ~/codex-pet
./uninstall.sh
```

This stops the daemon, removes its CLI links and runtime files, and removes only the Pet hook commands. It keeps Python/`termuxgui`, Codex config backups, and the saved position for a later reinstall.

## License

MIT. See [LICENSE](LICENSE).
