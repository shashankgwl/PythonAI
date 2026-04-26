import asyncio
import sys

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


async def main() -> None:
    prompt_id = sys.argv[1] if len(sys.argv) > 1 else "11"

    async with sse_client("http://localhost:8077/sse") as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools:", [tool.name for tool in tools.tools])

            result = await session.call_tool(
                "GetPromptsById",
                {"prompt_id": prompt_id},
            )
            print("Is error:", result.isError)
            print("Structured content:", result.structuredContent)
            print("Content:", result.content)


if __name__ == "__main__":
    asyncio.run(main())
