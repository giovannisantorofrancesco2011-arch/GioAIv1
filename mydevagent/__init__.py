"""MyDevAgent — assistente di programmazione local-first con 15 agenti specializzati."""

__version__ = "1.0.0"

from .orchestrator import Orchestrator  # noqa: E402

__all__ = ["Orchestrator", "__version__"]
