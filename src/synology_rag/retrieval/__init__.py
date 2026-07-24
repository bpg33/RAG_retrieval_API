"""The retrieval engine: protocol-independent business logic.

The engine owns validation, embedding, filtering, vector search, metadata
enrichment, deduplication, neighbour expansion, ranking, context budgeting, and
citation assembly. REST and MCP adapters call :class:`RetrievalService` and add
no retrieval logic of their own.
"""
