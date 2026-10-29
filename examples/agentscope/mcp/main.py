"""Resolve a Polaris MCP Server and optionally inspect its native Tool list."""

import asyncio
import json

from examples.agentscope._common import context, parser
from polaris_ai.agentscope import PolarisMCPResolver
from polaris_ai.agentscope.mcp import mcp_endpoint


async def main(argv=None):
    arguments = parser("Resolve an MCP Server through Polaris")
    arguments.add_argument("--service", default="search-mcp")
    arguments.add_argument("--protocol-version", default="")
    arguments.add_argument("--scheme", default="")
    arguments.add_argument("--mcp-timeout", type=float, default=30.0)
    arguments.add_argument("--no-filter-contract", action="store_true")
    arguments.add_argument("--connect", action="store_true")
    args = arguments.parse_args(argv)

    sdk = context(args, entry=__file__)
    resolver = PolarisMCPResolver(sdk, args.namespace)
    try:
        instances = await resolver.async_candidates(
            args.service, protocol_version=args.protocol_version,
        )
        if not instances:
            raise LookupError(f"No healthy MCP instance for {args.namespace}/{args.service}")
        first = instances[0]
        url, _port, protocol = mcp_endpoint(first, args.scheme)
        disabled = await resolver.async_disabled_tools(
            args.service, protocol=protocol, version=first.get_version(),
        )
        tools = []
        if args.connect:
            client = await resolver.async_create_client(
                args.service,
                protocol_version=args.protocol_version,
                scheme=args.scheme,
                timeout=args.mcp_timeout,
                filter_contract=not args.no_filter_contract,
            )
            try:
                tools = [tool.name for tool in await client.list_raw_tools()]
            finally:
                await client.close()
        result = {
            "service": args.service,
            "instances": [item.get_id() for item in instances],
            "url": url,
            "protocol": protocol,
            "disabled_tools": disabled,
            "tools": tools,
        }
        print(json.dumps(result), flush=True)
        return result
    finally:
        await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
