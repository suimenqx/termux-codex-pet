# Codex Pet for Termux

[简体中文使用指南](README.zh-CN.md)

A small robot that floats over Android apps and shows what Codex CLI is doing. Codex hooks send events through a private Unix socket to one Termux:GUI process. There is no polling, web server, or separate APK. Android notifications are used only when the overlay is unavailable for an approval or completion event.

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

The installer installs Python and the official `termuxgui` Python binding if missing, creates the CLI links, merges the Pet hooks into the existing Codex configuration, starts the daemon, and runs an IPC smoke check. It backs up any Codex configuration file it changes. It does not install an Android APK or replace unrelated Codex settings. `codex-pet test` takes about 23 seconds and shows all six states before returning to idle.

**For live Codex events:** restart Codex after installation. On Codex CLI 0.156.1, open `/hooks` in the new session and trust the Pet hook commands if prompted. The installer uses inline hooks in `~/.codex/config.toml` when that config already has hooks; otherwise it uses `~/.codex/hooks.json`. The install output reports which mode was used. You can inspect `~/.config/codex-pet/install.json` later. Pet hooks only observe events; they never approve or deny Codex actions.

Submit a Codex prompt to see **Working**. If Codex requests permission, the Pet shows **Needs approval** until another lifecycle event arrives. When Codex finishes, it briefly shows **Done** and then returns to idle.

## Daily use

```sh
codex-pet start       # start if needed; safe to run twice
codex-pet stop        # close the overlay and daemon
codex-pet restart     # reload the installed code and reconnect the overlay
codex-pet status      # daemon, GUI connection, state, project, session counts
codex-pet test        # cycle through all visual states
```

Tap the robot to open or close its activity bubble. The compact card is 116 dp wide, with a 5 dp speech tail; its text aligns toward the robot so the project, colored status, and short message read as one conversation. The bubble switches sides near the left edge. Approval and completion open it automatically; touching it keeps it open until you close it. Start a drag near the robot's center; the point you grabbed stays under your finger, so the robot does not jump. Touches farther from the center can still tap it, but do not start a drag. The position is saved in `~/.config/codex-pet/config.json` and restored after restart. The collapsed robot is about 64 dp wide.

| State | What you see | When it changes |
| --- | --- | --- |
| Idle | Quiet robot | Session starts, ends, or a temporary state expires |
| Working | Slow animation and elapsed time in the card | You submit a prompt |
| Needs approval | Prominent alert and open card | Codex requests permission; remains until a later event |
| Done | Completion feedback and open card | Codex stops; returns to idle after about 6 seconds |
| Interrupted | Pause feedback | Turn is interrupted; returns to idle after about 4 seconds |
| Error | Error icon | Available in `codex-pet test`; hooks do not guess failures |

With multiple Codex sessions, approval takes priority over working, and the robot shows a count when two or more sessions are working.

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

The installer registers `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, `Stop`, `Interrupt`, and `SessionEnd`. Each calls `codex-pet-event` with Codex's JSON. The helper exits successfully even if the Pet fails. If Android kills the daemon, the next Codex event starts it again; Termux:Boot is not required. `SessionEnd` removes that session. Runtime files are in `~/.cache/codex-pet/` (`pet.sock` and the rotating `pet.log`).

## Troubleshooting

- **Pet is missing:** run `codex-pet status`. If stopped, run `codex-pet start`. A later Codex event also restarts a killed daemon.
- **`GUI=unavailable`:** check the Termux:GUI overlay permission and matching app signatures, then run `codex-pet restart`. Read `~/.cache/codex-pet/pet.log` if it still fails.
- **Pet works in `codex-pet test` but ignores prompts:** restart Codex, open `/hooks`, and trust the Pet hooks. Check the file matching `hooks_mode` in `~/.config/codex-pet/install.json`. `codex features list` should show `hooks` enabled.
- **Pet shows an old design after updating:** run `codex-pet restart`; a running daemon does not reload Python files automatically.
- **Drag or tap is unreliable:** confirm `GUI=ready` with `codex-pet status`, then run `codex-pet restart`. Start a drag near the robot's center; touching the activity card keeps it open rather than moving the robot.

## Uninstall

```sh
cd ~/codex-pet
./uninstall.sh
```

This stops the daemon, removes its CLI links and runtime files, and removes only the Pet hook commands. It preserves Python dependencies, Codex configuration backups, and the saved position for a later reinstall.

## License

MIT. See [LICENSE](LICENSE).
