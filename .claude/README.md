# Using EDPA with Claude Code

EDPA provides Claude Code skills and commands for conversational governance management.

## Installation

Add this directory as a Claude Code plugin, or install the full [TECHNOMATON Hub](https://github.com/technomaton/technomaton-hub) which includes EDPA alongside 14 other capability packs.

## Commands

| Command | Description |
|---------|-------------|
| `/edpa setup` | Initialize EDPA governance for a project |
| `/edpa close-iteration` | Close iteration — compute hours + generate reports |
| `/edpa reports` | Generate timesheets, snapshots, Excel exports |
| `/edpa calibrate` | Auto-calibrate CW heuristics (after 1st PI) |

## Skills

The commands above invoke these skills:

- **edpa-setup** — Project initialization (GitHub Projects, config, CI)
- **edpa-engine** — Evidence-driven calculation (the core EDPA formula)
- **edpa-reports** — Timesheet and export generation
- **edpa-autocalib** — CW heuristic optimization via Karpathy's autoresearch loop

## MCP Server

EDPA uses the GitHub MCP server for API access. See `.mcp.json` for configuration.

## Part of TECHNOMATON Hub

EDPA is one of 15 capability packs in [TECHNOMATON Hub](https://github.com/technomaton/technomaton-hub) — a curated collection of AI-powered skills for development, operations, security, marketing, finance, and governance.
