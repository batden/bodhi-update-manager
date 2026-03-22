"""Backend registry and abstract base class for update discovery."""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple

from bodhi_update.models import UpdateItem


class UpdateBackend(ABC):
    """Interface for update discovery and installation backends."""

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """A unique string identifier for this backend, e.g., 'apt', 'python'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """A human-readable name for the backend, e.g., 'Debian/Ubuntu packages'."""

    def is_available(self) -> bool:
        """Return True if this backend is supported on the current system."""
        return False

    def check_busy(self) -> Tuple[bool, str]:
        """Check if the package manager is currently locked or running.

        Return (True, reason) if busy, otherwise (False, "").
        """
        return False, ""

    def refresh(self) -> Tuple[bool, str]:
        """Refresh the local list of available updates.

        Return (True, "") on success, or (False, error_message).
        """
        return True, ""

    def get_updates(self) -> Tuple[List[UpdateItem], int]:
        """Read the local cache and return available updates.

        Return (updates_list, total_download_bytes).
        """
        return [], 0

    @abstractmethod
    def build_install_command(self, packages: List[str] | None = None) -> list[str]:
        """Return an argv list required to install the given packages.

        If packages is None or empty, return the argv to upgrade all available
        packages.  The list is passed directly to VTE spawn_async — no shell
        layer is used.
        """


class BackendRegistry:
    """Singleton registry holding all instantiated update backends."""

    def __init__(self) -> None:
        self._backends: Dict[str, UpdateBackend] = {}

    def register(self, backend: UpdateBackend) -> None:
        """Register a backend instance."""
        self._backends[backend.backend_id] = backend

    def get_backend(self, backend_id: str) -> UpdateBackend | None:
        """Return a registered backend by ID, or None if not found."""
        return self._backends.get(backend_id)

    def get_all_backends(self) -> List[UpdateBackend]:
        """Return all registered backends unconditionally."""
        return list(self._backends.values())

    def is_initialized(self) -> bool:
        """Return True if the registry has been initialized with backends."""
        return bool(self._backends)


_REGISTRY = BackendRegistry()


def get_registry() -> BackendRegistry:
    return _REGISTRY


def initialize_registry() -> None:
    """Register all backends that are available on this installation.

    APT, Snap, and Flatpak are registered as standard backends when their
    module files are present.  Python (pip) and Rust (cargo) are optional
    extras selected at install time.  All backends are imported conditionally:
    if a module file is absent the ImportError is silently swallowed and that
    backend is simply absent from the registry.
    """
    reg = get_registry()
    if reg.is_initialized():
        return

    from bodhi_update.plugins.apt import AptBackend  # noqa: PLC0415
    reg.register(AptBackend())

    try:
        from bodhi_update.plugins.python import PythonBackend  # noqa: PLC0415
        reg.register(PythonBackend())
    except ImportError:
        pass

    try:
        from bodhi_update.plugins.rust import RustBackend  # noqa: PLC0415
        reg.register(RustBackend())
    except ImportError:
        pass

    try:
        from bodhi_update.plugins.snap import SnapBackend  # noqa: PLC0415
        reg.register(SnapBackend())
    except ImportError:
        pass

    try:
        from bodhi_update.plugins.flatpak import FlatpakBackend  # noqa: PLC0415
        reg.register(FlatpakBackend())
    except ImportError:
        pass
