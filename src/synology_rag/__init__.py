"""Synology RAG Retrieval Platform.

A read-only Retrieval-Augmented Generation platform over an existing
Synology-hosted Qdrant + PostgreSQL index. One shared, protocol-independent
retrieval engine is exposed through a local REST API and a local MCP adapter.
"""

__version__ = "0.1.0"
