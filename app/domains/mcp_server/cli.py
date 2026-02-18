from __future__ import annotations

import uvicorn

from .config import MCPServerSettings
from .server import create_mcp_app


def main() -> None:
    settings = MCPServerSettings()
    app = create_mcp_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
