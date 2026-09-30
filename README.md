# Codex Pet for Termux

[简体中文使用指南](README.zh-CN.md)

A small mascot that floats over Android apps and shows what Codex CLI is doing. The default appearance is a lively Akita Inu; the original robot remains available. Codex hooks send events through a private Unix socket to one Termux:GUI process. There is no polling, web server, or separate APK. Android notifications are used only when the overlay is unavailable for a needs-input or ready event.

## Install and first check

1. Install Termux and Termux:GUI from compatible, matching-signature sources.
2. In Android, enable **Termux:GUI → Advanced → Display over other apps**.
3. In Termux, run:

   ```sh
   git clone https://github.com/suimenqx/termux-codex-pet.git ~/codex-pet
   cd ~/codex-pet
   ./install.sh
   codex-pet status
   codex-pet test
   ```

The installer installs Python, libpng, and the official `termuxgui` Python binding if missing, creates the CLI links, merges the Pet hooks into the existing Codex configuration, starts the daemon, and runs an IPC smoke check. It backs up any Codex configuration file it changes. It does not install an Android APK or replace unrelated Codex settings. `codex-pet test` demonstrates Idle and the four official activity states; Ready remains visible as an icon until a later event changes it or the session ends.

**For live Codex events:** restart Codex after installation. On Codex CLI 0.156.1, open `/hooks` in the new session and trust the Pet hook commands if prompted. The installer uses inline hooks in `~/.codex/config.toml` when that config has inline event groups; otherwise it uses `~/.codex/hooks.json`. The install output reports which mode was used. You can inspect `~/.config/codex-pet/install.json` later. Pet hooks only observe events; they never approve or deny Codex actions.

Submit a prompt to see **Running**. When Codex requests tool permission, the Pet shows **Needs input**. A tool response moves the session back to **Running**. When the turn stops, the Pet shows **Ready** until a later event changes that session's state or the session ends.

## Daily use

```sh
codex-pet start       # start if needed; safe to run twice
codex-pet stop        # close the overlay and daemon
codex-pet restart     # reload the installed code and reconnect the overlay
codex-pet status      # daemon, GUI connection, state, pet, project, session counts
codex-pet test        # cycle through all visual states
codex-pet pet list    # list supported appearances
codex-pet pet use akita
codex-pet pet use robot
```

The Pet is a single, roughly 64 dp floating icon. The Akita uses high-resolution, transparent 256 × 256 PNG frames in a cheerful style: a large round cream face, bright orange-red crown with a pale blaze, small upright ears, and an open smile above a compact body. Idle breathes and blinks slowly; Running loops a lively small run; Needs input gives a gentle paw wave. Ready plays a happy hop once, and Blocked plays a short thoughtful head tilt; each then rests on its final pose. The original robot remains selectable and animated. `codex-pet pet list` shows the catalog and current choice; `codex-pet pet use <id>` switches to any listed appearance. The choice is saved alongside the overlay position in `~/.config/codex-pet/config.json` and changes the live overlay when the daemon is running. Tapping has no action. To move the Pet, drag from anywhere on the icon; it follows your finger after about 6 dp of movement.

| State | What you see | When it changes |
| --- | --- | --- |
| Idle | Slow breath and occasional blink | Session starts, ends, or its turn is interrupted |
| Running | Small running loop; a count badge appears with multiple active sessions | You submit a prompt or Codex resumes after a tool call |
| Needs input | Gentle raised-paw wave | Codex requests tool permission |
| Ready | One happy hop, then a resting pose | The turn stops; remains until a later event changes its state or the session ends |
| Blocked | Brief thoughtful head tilt, then a resting pose | Demo state only; hooks do not receive a definitive failed-turn event |

With multiple Codex sessions, status priority follows the public Pet order: Needs input, Blocked, Ready, Running. The mascot shows a count when two or more sessions are running.

**State accuracy:** Codex documents the four activity names and their priority, but this hook integration does not receive the same internal status stream as the desktop app. Hooks expose prompt, tool-permission, tool, stop, interrupt, and session lifecycle events; they do not report whether a stopped turn failed, whether activity is unread, or when Codex asks a text-only question. A denied permission with no tool result may stay at Needs input until another hook event arrives. This implementation never infers Blocked from an error-looking tool result. Ready stays visible as an icon until a later event changes that session's state or the session ends. A Stop hook from another integration can also request a continuation, briefly changing Ready back to Running when the next prompt event arrives. A definitive failed-turn signal requires every CLI session to use the same App Server event stream; that is not enabled by this hooks-only Termux integration.

## Update

The CLI links point into the cloned repository. After pulling new code, restart the daemon to load it:

```sh
cd ~/codex-pet
git pull --ff-only origin main
./install.sh
codex-pet restart
codex-pet status
```

## How hooks and recovery work

The installer registers `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, `PostToolUse`, `Stop`, `Interrupt`, and `SessionEnd`. Each calls `codex-pet-event` with Codex's JSON. The helper exits successfully even if the Pet fails. If Android kills the daemon, the next Codex event starts it again; Termux:Boot is not required. `SessionEnd` removes that session. Runtime files are in `~/.cache/codex-pet/` (`pet.sock` and the rotating `pet.log`).

## Troubleshooting

- **Pet is missing:** run `codex-pet status`. If stopped, run `codex-pet start`. A later Codex event also restarts a killed daemon.
- **`GUI=unavailable`:** check the Termux:GUI overlay permission and matching app signatures, then run `codex-pet restart`. Read `~/.cache/codex-pet/pet.log` if it still fails.
- **Pet works in `codex-pet test` but ignores prompts:** restart Codex, open `/hooks`, and trust the Pet hooks. Check the file matching `hooks_mode` in `~/.config/codex-pet/install.json`. `codex features list` should show `hooks` enabled.
- **Pet shows an old design after updating:** run `codex-pet restart`; a running daemon does not reload Python files automatically.
- **Drag is unreliable:** confirm `GUI=ready` with `codex-pet status`, then run `codex-pet restart`. Drag from anywhere on the icon and move it about 6 dp.

## Uninstall

```sh
cd ~/codex-pet
./uninstall.sh
```

This stops the daemon, removes its CLI links and runtime files, and removes only the Pet hook commands. It preserves Python dependencies, Codex configuration backups, and the saved position and appearance for a later reinstall.

## License

MIT. See [LICENSE](LICENSE).
