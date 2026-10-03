# Codex Pet for Termux

[简体中文使用指南](README.zh-CN.md)

A small mascot that floats over Android apps and shows what Codex CLI is doing. The default appearance is a lively Akita Inu; the original robot remains available. Codex hooks send events through a private Unix socket to one Termux:GUI process. There is no polling, web server, or separate APK. Android notifications are used only when the overlay is unavailable for a needs-input or ready event.

## Install and first check

1. Install Termux and Termux:GUI from compatible, matching-signature sources.
2. In Android, enable **Termux:GUI → Advanced → Display over other apps**.
3. In Termux, run:

   ```sh
   pkg update
   pkg install -y git
   git clone https://github.com/suimenqx/termux-codex-pet.git ~/codex-pet
   cd ~/codex-pet
   bash ./install.sh
   codex-pet status
   codex-pet test
   ```

The installer installs Python, Pillow (`python-pillow`), and the `termuxgui` Python binding if missing. It copies the app into a versioned runtime under `~/.local/share/codex-pet/`, installs stable command wrappers, merges the Pet hooks into the existing Codex configuration, restarts the daemon, and runs an IPC smoke check. If a checked installation step fails, it restores the prior runtime links, commands, and hook configuration; it restarts the prior daemon when one was running. The editable checkout can then move without changing the installed runtime. It backs up any Codex configuration file it changes. It does not install the Termux:GUI Android app or grant overlay permission. `codex-pet test` demonstrates Idle and the four official activity states; Ready remains visible as an icon until a later event changes it or the session ends. See the [detailed installation and dependency guide](docs/installation.md) for preflight checks, manual recovery commands, expected output, and cases that require the user to act on Android.

**For live Codex events:** restart Codex after installation. In a new session, open `/hooks` to review the Pet commands and trust them if Codex prompts. The installer uses inline hooks in `~/.codex/config.toml` when that config has inline event groups; otherwise it uses `~/.codex/hooks.json`. The install output reports which mode was used. You can inspect `~/.config/codex-pet/install.json` later. Pet hooks only observe events; they never approve or deny Codex actions.

Submit a prompt to see **Running**. When Codex requests tool permission, the Pet shows **Needs input**. A tool response moves the session back to **Running**. When the turn stops, the Pet shows **Ready** until a later event changes that session's state or the session ends.

## Daily use

```sh
codex-pet start       # start if needed; safe to run twice
codex-pet stop        # close the overlay and daemon
codex-pet restart     # restart the active release and reconnect the overlay
codex-pet status      # daemon, GUI connection, state, pet, project, session counts
codex-pet test        # cycle through all visual states
codex-pet pet list    # list supported appearances
codex-pet pet use akita
codex-pet pet use robot
codex-pet pet use pixel_dog
```

The Pet is a single, roughly 64 dp floating icon. The Akita uses high-resolution, transparent 256 × 256 PNG frames in a cheerful style: a large round cream face, bright orange-red crown with a pale blaze, small upright ears, and an open smile above a compact body. A plain blue collar stays consistent across all states and stopping transitions; expressions and actions convey status. Idle breathes, blinks, and slowly sways its tail through a wider arc; Running uses ten poses over the same 640 ms cycle: two limb breakdowns divide the larger extension/recovery changes while preserving all eight previous drawings and key times. The rejected sixteen-frame redraw is archived; see the [repair record](docs/artwork/akita/2026-10-repair.md). Needs input gives a gentle paw wave. When Running finishes, Ready first settles and turns toward you over 360 ms, then crouches for one relaxed happy hop. From other states it starts with the crouch, then loops slow breathing, a slow face-only blink, and a gentle tail sway. Blocked plays a short thoughtful head tilt and rests on its final pose. A steady animation clock keeps frame timing consistent while touch events are handled. Hook events that leave the displayed frame unchanged do not resend its PNG. The original robot remains selectable and animated. `codex-pet pet list` shows the catalog and current choice; `codex-pet pet use <id>` switches to any listed appearance. The choice is saved alongside the overlay position in `~/.config/codex-pet/config.json` and changes the live overlay when the daemon is running. Tapping has no action. To move the Pet, drag from anywhere on the icon; it follows your finger after about 6 dp of movement. Releasing saves the position; cancellation or screen-off restores the last saved position. Extra fingers do not start a second drag.

**Pixel Dog** is an additional grey pixel-art dog, imported from [rmazanek's CC0 Dog sprite sheet](https://opengameart.org/content/dog-3). It stands and wags its tail while idle, runs through five original poses at 130 ms each, barks for Needs input, sits down once then wags for Ready, and sits still for Blocked. Its 64×64 transparent frames use the same 64 dp overlay and controls. Select it with `codex-pet pet use pixel_dog`; adding it does not change Akita, Robot or the saved appearance. Source, license, original timing references and reproducible export are recorded in the [import brief](docs/artwork/pixel_dog/2026-10-import/brief.md).

You can add a separate local Pet Pack with `codex-pet pet import /path/to/pack`.
The directory must contain a valid `pet.json` and its referenced frames. Import
validates and copies it into `~/.local/share/codex-pet/pets/<id>/`, then lists it
under `pet list`; use `pet use <id>` to select it. Import does not change the
current pet or position. Built-in IDs and existing local IDs cannot be replaced;
give a revised pack a new ID. Local packs remain available after reinstall or
rollback to a version supporting local packs, and are retained on uninstall.

The optional [community preview importer](docs/artwork/community_previews/2026-10-import/brief.md)
prepares five separate local packs: `boba`, `mochi`, `golden_retriever`, `vpet`,
and `bongo_cat`. The first three preserve Petdex's pixel-style art; VPet uses
the original humanoid animations from [LorisYounger/VPet](https://github.com/LorisYounger/VPet),
with its separate animation attribution/terms. Bongo Cat uses the classic
[bongo.cat](https://github.com/Externalizable/bongo.cat) drumming layers, not
the Live2D edition. These previews are not bundled with installation. Their
source/provenance records are preserved locally; unverified image redistribution
rights are not inferred from a project's code license.

```sh
python tools/import_community_previews.py \
  --sources "$HOME/.cache/codex-pet/community-sources" \
  --output "$HOME/.cache/codex-pet/community-packs" --download
codex-pet pet import "$HOME/.cache/codex-pet/community-packs/vpet"
codex-pet pet use vpet
```

The exporter refuses an existing output directory and checks locked source
hashes. Import the other generated directories individually to make them
selectable. A preview is a chance to assess appearance and motion on the device,
not a claim that its animation has passed human review.

The [community pet integration notes](docs/community-pet-integration.md) record
how these existing assets were found, converted and imported, which boundaries
were reused, and what the device checks established. Use this path when adding
an existing community pet.

The [pet image and animation standards](docs/animation-assets.md) cover character scale and registration, motion timing and in-between frames, agent generation prompts, a production-brief template, and acceptance checks. They also identify the limits of the current artwork and audit tools. The following visual descriptions refer to Akita; all pets share the same state events.

| State | What you see | When it changes |
| --- | --- | --- |
| Idle | Slow breath, occasional blink, and a gentle tail sway | Session starts, ends, or its turn is interrupted |
| Running | Compact gallop with staggered forepaw and hind-paw motion; a count badge appears with multiple active sessions | You submit a prompt or Codex resumes after a tool call |
| Needs input | Gentle raised-paw wave | Codex requests tool permission |
| Ready | A slight crouch and one relaxed hop on entry, then slow breathing, a slow face-only blink, and a gentle tail sway | The turn stops; remains until a later event changes its state or the session ends |
| Blocked | Brief thoughtful head tilt, then a resting pose | Demo state only; hooks do not receive a definitive failed-turn event |

With multiple Codex sessions, status priority follows the public Pet order: Needs input, Blocked, Ready, Running. The mascot shows a count when two or more sessions are running.

**State accuracy:** Codex documents the four activity names and their priority, but this hook integration does not receive the same internal status stream as the desktop app. Hooks expose prompt, tool-permission, tool, stop, interrupt, and session lifecycle events; they do not report whether a stopped turn failed, whether activity is unread, or when Codex asks a text-only question. A denied permission with no tool result may stay at Needs input until another hook event arrives. This implementation never infers Blocked from an error-looking tool result. A Stop hook keeps the session Ready, and Interrupt makes it Idle. Late PostToolUse or PermissionRequest hooks cannot reopen that finished turn; a new UserPromptSubmit, session lifecycle event, or explicit manual state change can change it. A session whose turn ID is unknown adopts its next observed ID, including on Stop; known mismatched IDs are rejected unless a new prompt starts the turn. A Stop hook from another integration can also request a continuation, briefly changing Ready back to Running when the next prompt event arrives. A definitive failed-turn signal requires every CLI session to use the same App Server event stream; that is not enabled by this hooks-only Termux integration.

## Update

The installed runtime is independent of the checkout. After pulling new code, run the installer to deploy a fresh private copy and restart the daemon:

```sh
cd ~/codex-pet
git pull --ff-only origin main
bash ./install.sh
codex-pet status
```

## How hooks and recovery work

The installer registers `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, `PostToolUse`, `Stop`, `Interrupt`, and `SessionEnd`. Each calls `codex-pet-event` with Codex's JSON. The helper exits successfully even if the Pet fails. Startup lock contention shares the startup deadline; a stalled GUI cannot block event wakeups. Native handshakes and replies have bounded reads, and a broken connection is discarded before reconnecting. If Android kills the daemon, the next Codex event starts it again; Termux:Boot is not required. `SessionEnd` removes that session. Runtime files are in `~/.cache/codex-pet/` (`pet.sock` and the rotating `pet.log`).

## Troubleshooting

- **Pet is missing:** run `codex-pet status`. If stopped, run `codex-pet start`. A later Codex event also restarts a killed daemon.
- **`GUI=unavailable`:** check the Termux:GUI overlay permission and matching app signatures, then run `codex-pet restart`. Read `~/.cache/codex-pet/pet.log` if it still fails.
- **Renderer diagnosis:** `codex-pet status` includes the actual binding/plugin version, current transport, selection reason, remembered shared fallback and latest connection error. The shared implementation is present but its default rollout is still gated by device acceptance; ordinary installations currently use PNG. Shared frame, event-channel or movement-connection failure opens a fresh PNG connection and keeps shared disabled until daemon restart.
- **Pet works in `codex-pet test` but ignores prompts:** restart Codex, open `/hooks`, and trust the Pet hooks. Check the file matching `hooks_mode` in `~/.config/codex-pet/install.json`. `codex features list` should show `hooks` enabled.
- **Pet shows an old design after updating the checkout:** run `bash ./install.sh` from that checkout to deploy it and restart the daemon. `codex-pet restart` alone restarts the already installed release.
- **Colored specks around Akita edges:** update the checkout and run `bash ./install.sh` to deploy the PNG rendering fix and restart the daemon. An older installed release keeps the raw-buffer renderer until it is redeployed.
- **Drag is unreliable:** confirm `GUI=ready` with `codex-pet status`, then run `codex-pet restart`. Drag from anywhere on the icon and move it about 6 dp.

## Review a screen recording

Run `python tools/review_recording.py path/to/recording.mp4` from the checkout. It creates a local overview and original frame timestamps under `~/.cache/codex-pet/recordings/`. Add `--crop x,y,width,height` and repeatable `--window name:start:end` to create pet-only playback, slow motion, frame stepping and labelled contact sheets. The input is preserved; nothing is uploaded. See the [repeatable recording workflow](docs/recording-review.md) for coordinates, variable-frame-rate interpretation and the next-recording comparison process.

The [deployed revision](docs/artwork/akita/2026-10-continuity/brief.md) uses ten running poses and three stopping poses. The latest recording confirms the transition to Ready, but exposes limb shape and running rhythm problems. A [complete-cycle redraw and timed comparison](docs/artwork/akita/2026-10-rhythm/review.md) is saved for review; its hind-leg recovery failed visual review and has not replaced the device animation. `tools/audit_animation.py` now reports each exposure, paw displacement, and chord speed. Passing file or playback tests does not certify natural gait.

## Uninstall

```sh
cd ~/codex-pet
bash ./uninstall.sh
```

This stops the daemon, removes its command wrappers, installed runtime releases, and Pet hook commands. It preserves Python dependencies, Codex configuration backups, and the saved position and appearance for a later reinstall.

## License

MIT. See [LICENSE](LICENSE).

Animation review tools use the same compiled packs and frame composition as the overlay. For example, `python tools/preview_animation.py --pet akita --state ready --from-state running` includes the completion transition; `python tools/audit_animation.py --pet robot --state running --count 10` exports the Robot badge. Both accept `--cycles`. Audit paw measurements apply to Akita; candidate previews retain their separate explicit file list.
