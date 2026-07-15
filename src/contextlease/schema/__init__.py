"""Packaged JSON Schema for ContextLease configuration files."""

from importlib import resources


def config_schema_resource():
    """Return the traversable resource for the configuration JSON Schema."""
    return resources.files(__package__).joinpath("contextlease.schema.json")


__all__ = ["config_schema_resource"]
