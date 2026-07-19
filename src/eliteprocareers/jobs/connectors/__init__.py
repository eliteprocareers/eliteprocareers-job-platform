"""
Importing this package registers every connector (the @registry.register
decorator runs on import). Anything that needs the registry populated
should import from here, not from individual connector modules directly.
"""

from eliteprocareers.jobs.connectors.registry import registry
from eliteprocareers.jobs.connectors.base import SupportTier, ConnectorCapabilities

# Import order doesn't matter for registration, but keep reference
# implementation first for readability.
from eliteprocareers.jobs.connectors import greenhouse  # noqa: F401
from eliteprocareers.jobs.connectors import lever  # noqa: F401
from eliteprocareers.jobs.connectors import brightermonday  # noqa: F401
from eliteprocareers.jobs.connectors import myjobmag  # noqa: F401
from eliteprocareers.jobs.connectors import roadmap  # noqa: F401

__all__ = ["registry", "SupportTier", "ConnectorCapabilities"]
