"""Versline bridge: a machine-readable front end for other programs (the Versobs Obsidian plugin, editors, scripts).

    versline bridge info              -> one JSON document: versions + every tool with its parameter schema
    versline bridge run TOOL          -> reads one JSON request line on stdin, streams NDJSON events on stdout

See docs/en/library.md ("Bridge protocol") for the event format.
"""

PROTOCOL_VERSION = 1
