"""Load only skills mounted on one registered Agent service."""

import asyncio

from agentscope.tool import Toolkit

from examples.agentscope._common import context, parser
from polaris_ai.agentscope import PolarisSkillLoader


async def main(argv=None):
    arguments = parser("Load mounted Polaris Skills")
    arguments.add_argument("--service", required=True)
    arguments.add_argument("--version", default="")
    args = arguments.parse_args(argv)
    sdk = context(args, entry=__file__)
    try:
        async with PolarisSkillLoader(
            sdk,
            args.namespace,
            service_name=args.service,
            version=args.version,
        ) as loader:
            toolkit = Toolkit(skills_or_loaders=[loader])
            print(await toolkit.get_skill_instructions() or "No mounted skills")
    finally:
        await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
