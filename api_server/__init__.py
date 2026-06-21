"""API server package.

Import ``create_app`` directly from :mod:`api_server.app`. The package __init__
intentionally does not eagerly import ``app`` to avoid a circular import:
``agent_orchestration.adapters.openai_adapter`` imports from
``api_server.schemas.openai`` (triggering this package), while ``api_server.app``
imports the routes that import that adapter.
"""
