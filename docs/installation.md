# Installation and dependency guide

This guide is for installing Codex Pet on an Android device running Termux. Use it as an agent checklist: the shell steps can be run in Termux, while Android app installation, overlay permission, and any Codex hook trust prompt need the user's attention.

## Requirements

| Requirement | Needed for | How it is provided |
| --- | --- | --- |
| Termux on Android | Running the daemon and CLI | Install the Termux app. Run this guide inside its terminal, where `pkg` and `PREFIX` are set. |
| Termux:GUI Android app | Creating the native floating overlay | Install it separately from a source whose signature is compatible with the installed Termux app. `install.sh` cannot install an APK. |
| Overlay permission | Showing the Pet over other apps | In Android, open **Termux:GUI → Advanced → Display over other apps** and enable it. The installer cannot grant this permission. |
| `git` command | Cloning the repository | Install before cloning with `pkg install -y git`; `install.sh` cannot install Git before the repository is downloaded. |
| Python, Pillow (`python-pillow`), `termuxgui` Python binding | Rendering Pet frames and talking to Termux:GUI | `install.sh` installs these when missing. |
| Codex CLI | Driving states from real Codex sessions | Optional for installing and demoing the Pet; required for live Codex hooks. Install Codex separately if needed. |
| Termux:API app and package | Optional notifications when the overlay is unavailable | Not needed for the overlay. Install the compatible Android app and `pkg install termux-api` only if notification fallback is wanted. |

Network access is needed for GitHub, Termux package repositories, and PyPI when their respective files or dependencies are missing. Root access, `termux-setup-storage`, Termux:Boot, and a separate Pet APK are not required.

## Install from a new checkout

First install Termux and Termux:GUI from compatible signing sources, then enable the overlay permission in Android. In the Termux app, run:

```sh
pkg update
pkg install -y git
git clone https://github.com/suimenqx/termux-codex-pet.git ~/codex-pet
cd ~/codex-pet
bash ./install.sh
codex-pet status
codex-pet test
```

If `~/codex-pet` already exists, inspect it before updating:

```sh
git -C ~/codex-pet status --short --branch
```

Keep the checkout on `main`; only run the following when local changes are absent or have been handled:

```sh
git -C ~/codex-pet pull --ff-only origin main
```

The installer copies the runtime files into a versioned release under `~/.local/share/codex-pet/releases/` and creates stable command wrappers under `~/.local/bin/`. The running Pet no longer depends on the checkout location, so the checkout can be moved after installation. Keep a checkout available when you want to update or uninstall. If the checkout is on Android shared storage, use `bash ./install.sh`; shared storage does not allow direct execution of scripts.

`install.sh` installs missing Python and `python-pillow` packages through `pkg`, then installs the `termuxgui` Python binding through `python -m pip`. The deployment module stages a private runtime release, verifies real Pillow PNG decoding plus both pack manifests and every referenced image, then atomically activates it, creates stable command wrappers, merges Pet hooks into the existing Codex configuration, restarts the daemon, and sends an IPC smoke event. It backs up Codex configuration files before changing them. If a checked installation step fails, it restores the prior runtime links, command paths, and hook files, then restarts the prior daemon if it was running. The active and previous runtime releases are kept separately. It does not install the Termux:GUI Android app, enable Android permissions, install Codex CLI, or silently trust a hook prompt.

The installer updates `~/.codex/config.toml` when it contains inline hook event groups; otherwise it merges Pet commands into `~/.codex/hooks.json`. A `hooks.state` metadata block alone does not select inline mode. Existing user hooks are preserved, modified files are backed up, and the selected mode is recorded in `~/.config/codex-pet/install.json`. The Python `import termuxgui` check verifies only the binding; `GUI=ready` from `codex-pet status` is the device-side check for the Android app and its permission.

Expected checks:

- `codex-pet status` reports `GUI=ready` and `pet=akita`. `state=idle` with no active Codex sessions is normal.
- `codex-pet test` displays Idle, Running, Needs input, Ready, and Blocked, then removes its temporary test session. Allow about 18 seconds. With no other active sessions, the Pet returns to Idle; end or isolate other sessions when visually checking each selected state.
- The installer reports `Codex hooks installed (inline)` or `Codex hooks installed (json)`. If it changes an existing hooks file, it prints the backup path.
- The runtime log is `~/.cache/codex-pet/pet.log`.
- Status also reports renderer transport, actual binding/plugin versions, the selection reason, any remembered shared fallback, and the latest connection error. PNG remains the default while Android-side shared-resource acceptance is pending. USB/ADB access is not required to install or use the Pet.

## Dependency checks and recovery

Run these commands from the checkout in Termux to identify the relevant dependency without guessing:

```sh
command -v pkg
command -v git
printf 'PREFIX=%s\n' "${PREFIX:-unset}"
python -c 'from codex_pet.image_codec import check_capability; check_capability(); print("Pillow PNG OK")'
python -c 'import termuxgui; print(termuxgui.__file__)'
```

| Symptom | Meaning and next step |
| --- | --- |
| `pkg` is missing or `PREFIX=unset` | The command is not running in the Termux app, or the Termux environment is damaged. Do not run `install.sh` from desktop Linux, macOS, or an Android shell. Open Termux and repeat the checks. |
| `git: command not found` before cloning | Run `pkg install -y git`. If package metadata is stale, run `pkg update` first. |
| `Unable to locate package` or repository download errors | Preserve the full `pkg` output. Check network access; refresh package metadata with `pkg update`. If the selected mirror is unavailable, use Termux's repository selector and retry. |
| `Pillow PNG capability unavailable` | Run `pkg install -y python-pillow`, then repeat the actual PNG decode check from the checkout. Import alone does not verify the decoder. Pack/codec preflight failures preserve the active release. |
| `No module named termuxgui` | Run `python -m pip install termuxgui`, then repeat the import check. If pip fails, report its complete output and check PyPI/network access; do not substitute a different binding package. |
| `Codex Pet did not start` or `GUI=unavailable` | Check that the Termux:GUI Android app is installed, its signing source is compatible with Termux, and **Display over other apps** is enabled. Then run `codex-pet restart`, `codex-pet status`, and inspect `~/.cache/codex-pet/pet.log`. |
| `Cannot install over directory` | A directory occupies a CLI link path. Inspect it and any files inside before choosing a backup or another location; the installer intentionally refuses to replace directories. |
| `hooks.json has an unexpected shape` or TOML parse error | Stop before replacing Codex configuration. Preserve the file and error output for inspection; the installer backs up files it edits but will not guess how to rewrite malformed user data. |
| `codex-pet test` passes but live prompts do not change the Pet | Confirm Codex CLI is installed and hooks are enabled. Restart Codex, open `/hooks`, review and trust the Pet command if Codex prompts. Check `hooks_mode` in `~/.config/codex-pet/install.json` to see which configuration file was updated. |

When a command fails, stop at the first failure, capture the exact command and full output, and apply the matching recovery step. Do not repeatedly rerun the installer after a dependency or config failure.

## Connect a Codex session

The Pet can be installed and its states demoed without Codex CLI. For live states, install and start Codex, then restart it after installing the hooks. In a new Codex session, use `/hooks` to inspect the registered commands. If Codex asks to trust them, show that prompt to the user and let them decide. The installer records whether it used inline hooks in `~/.codex/config.toml` or `~/.codex/hooks.json` in `~/.config/codex-pet/install.json`.

To remove the integration, run `bash ./uninstall.sh` from a checkout. It stops the daemon, removes managed command wrappers, Pet-owned hooks, and marked runtime releases, while preserving Python packages, Codex backups, and saved appearance/position.

The image contract is packed straight RGBA8 in sRGB. Untagged PNGs use the pack’s declared sRGB space. ICC, HDR and incompatible gamma/chromaticity are rejected instead of implicitly converted. No NumPy runtime dependency is installed. Measured here: Python 3.14.6, Pillow 12.3.0, binding 0.1.6 and Termux:GUI version 7; other devices still require their own permission and GUI checks.
