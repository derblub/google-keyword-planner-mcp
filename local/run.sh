#!/usr/bin/env bash
# Startet den MCP-Server aus diesem Ordner, weil er die .env relativ zum
# Arbeitsverzeichnis liest.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
exec ../go/bin/kwp-mcp "$@"
