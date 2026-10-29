"""Start the Skill-backed A2A provider with published mode as the default."""

import asyncio

from examples.agentscope.a2a.provider.main import main as provider_main


async def main(argv=None):
    arguments = list(argv) if argv is not None else []
    if not any(argument == "--skill-source" or argument.startswith("--skill-source=")
               for argument in arguments):
        arguments = ["--skill-source", "published", *arguments]
    return await provider_main(arguments)


if __name__ == "__main__":
    asyncio.run(main())
