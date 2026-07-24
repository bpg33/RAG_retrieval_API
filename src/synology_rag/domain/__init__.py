"""Protocol-independent domain layer: typed models and errors.

Nothing in this package may import FastAPI, MCP, Qdrant, or psycopg types. The
retrieval engine returns these objects; adapters translate them to/from the
wire.
"""
