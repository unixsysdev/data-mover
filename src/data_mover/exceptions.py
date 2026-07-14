"""Domain-specific exceptions raised by Data Mover."""


class DataMoverError(Exception):
    """Base class for expected Data Mover failures."""


class ConfigurationError(DataMoverError):
    """Raised when an export request is invalid or incomplete."""


class DestinationExistsError(DataMoverError):
    """Raised when an export would replace a file without permission."""


class ExportError(DataMoverError):
    """Raised when the database result cannot be exported safely."""


class OptionalDependencyError(DataMoverError):
    """Raised when an optional output dependency is unavailable."""
