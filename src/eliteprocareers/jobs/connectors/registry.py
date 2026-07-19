"""
Connector registry — the ingestion engine (and future application workflow)
looks sources up here instead of branching on source name. Adding a new
connector means writing the connector and importing it in __init__.py;
nothing else in the system changes.
"""

from eliteprocareers.jobs.connectors.base import JobConnector, SupportTier


class ConnectorRegistry:
    def __init__(self):
        self._connectors: dict[str, type[JobConnector]] = {}

    def register(self, connector_cls: type[JobConnector]) -> type[JobConnector]:
        """Use as a decorator on a JobConnector subclass."""
        self._connectors[connector_cls.source_name] = connector_cls
        return connector_cls

    def get(self, source_name: str) -> type[JobConnector]:
        if source_name not in self._connectors:
            raise KeyError(f"No connector registered for source '{source_name}'.")
        return self._connectors[source_name]

    def all(self) -> list[type[JobConnector]]:
        return list(self._connectors.values())

    def by_tier(self, tier: SupportTier) -> list[type[JobConnector]]:
        return [c for c in self._connectors.values() if c.support_tier == tier]

    def with_capability(self, capability: str) -> list[type[JobConnector]]:
        """capability is a ConnectorCapabilities field name, e.g. 'scheduled_polling'."""
        return [
            c for c in self._connectors.values()
            if getattr(c.capabilities, capability, False)
        ]


registry = ConnectorRegistry()
