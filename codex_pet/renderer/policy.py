"""Backend capability policy and immutable diagnostics; no business states."""
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

# Enable only after the production/native/human gates recorded in issue #14.
SHARED_ROLLOUT_APPROVED = False


@dataclass(frozen=True)
class RendererPolicy:
    binding_version: str
    shared_approved: bool = False

    @classmethod
    def installed(cls) -> 'RendererPolicy':
        try:
            binding = version('termuxgui')
        except PackageNotFoundError:
            binding = 'unknown'
        return cls(binding, SHARED_ROLLOUT_APPROVED)

    def choose(self, canvas: tuple[int, int], plugin_version: int) -> tuple[str, str]:
        if not self.shared_approved:
            return 'png', 'shared device acceptance pending'
        if self.binding_version != '0.1.6' or plugin_version != 7:
            return 'png', 'unverified binding or plugin version'
        if canvas != (256, 256):
            return 'png', 'conservative policy for this canvas'
        return 'shared', 'verified 256x256 capability'


@dataclass(frozen=True)
class RendererStatus:
    binding_version: str = 'unknown'
    plugin_version: int | None = None
    transport: str = 'pending'
    reason: str = 'starting'
    fallback_reason: str = ''
    last_connection_error: str = ''
