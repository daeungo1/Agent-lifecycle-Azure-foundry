from __future__ import annotations

from agent_framework import MCPStreamableHTTPTool

TOOLBOX_TOKEN_SCOPE = "https://ai.azure.com/.default"


def build_toolbox(endpoint: str, credential: object) -> MCPStreamableHTTPTool:
    def _header_provider(_context: dict[str, object]) -> dict[str, str]:
        token = credential.get_token(TOOLBOX_TOKEN_SCOPE)
        return {"Authorization": f"Bearer {token.token}"}

    return MCPStreamableHTTPTool(
        name="department-toolbox",
        url=endpoint,
        load_tools=False,
        load_prompts=False,
        header_provider=_header_provider,
    )
