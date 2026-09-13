"""In-process MCP-style lab simulator; not a network MCP transport."""
import itertools
import json
from tools import TOOLS_SCHEMA, PetCareStore, dispatch_tool_call


class MCPPetCareServer:
    def __init__(self, store=None, server_name="pet-care-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"
        self.store = store or PetCareStore()
        self._ids = itertools.count(1)

    def list_tools(self):
        return TOOLS_SCHEMA

    def call_tool(self, tool_name, arguments):
        return {"jsonrpc": "2.0", "id": next(self._ids),
                "server": self.server_name, "tool": tool_name,
                "result": json.loads(dispatch_tool_call(tool_name, arguments, self.store))}


if __name__ == "__main__":
    store = PetCareStore(":memory:")
    server = MCPPetCareServer(store)
    print(f"MCP Server: {server.server_name}; Tools: {len(server.list_tools())}")
    print(json.dumps(server.call_tool("query_pet_care", {"pet_id": "PET001"}), ensure_ascii=False, indent=2))
    store.close()
