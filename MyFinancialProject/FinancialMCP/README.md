# FinancialMCP

This folder contains a Model Context Protocol (MCP) finance server.

It supports:
- **stdio MCP server** (for MCP clients that spawn a local process)
- **streamable HTTP server** (Express) at `/mcp`

## Prerequisites

- Node.js 18+ (recommended: 20/22/24)

## One-click (Windows)

- Double click `start-http.bat` to run the HTTP server.
- Double click `start-stdio.bat` to run the MCP stdio server.

## Configure tokens

Create a `.env` file in this folder (you can copy from `.env.example`).

- `TUSHARE_TOKEN` is required for most tools.
- You can also pass `TUSHARE_TOKEN` per-request in HTTP mode:
  - Header: `X-Tushare-Token: <token>`
  - or `Authorization: Bearer <token>`

## Run (manual)

```powershell
cd "d:\\新建文件夹\\MyFinancialProject\\FinancialMCP"

# HTTP mode
$env:PORT=3000
node .\\build\\httpServer.js

# stdio mode
node .\\build\\index.js
```

## Health check

```powershell
Invoke-RestMethod http://localhost:3000/health | ConvertTo-Json -Depth 5
```
