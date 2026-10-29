"""Load published skills into the native AgentScope Toolkit."""

import asyncio

from agentscope.tool import Toolkit

from examples.agentscope._common import context, parser
from polaris_ai.agentscope import PolarisSkillLoader


async def main(argv=None):
    arguments = parser("Load published Polaris Skills")
    arguments.add_argument("--name", action="append", default=[])
    arguments.add_argument("--version", default="")
    args = arguments.parse_args(argv)
    sdk = context(args, entry=__file__)
    try:
        async with PolarisSkillLoader(
            sdk,
            args.namespace,
            names=args.name,
            version=args.version,
        ) as loader:
            toolkit = Toolkit(skills_or_loaders=[loader])
            print(await toolkit.get_skill_instructions() or "No published skills")
            for skill in await loader.list_skills():
                print(f"{skill.name}: {skill.dir}")
    finally:
        await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
