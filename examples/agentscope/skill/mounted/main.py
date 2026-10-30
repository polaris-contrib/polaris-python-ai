# Tencent is pleased to support the open source community by making polaris-python-ai available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# Licensed under the BSD 3-Clause License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://opensource.org/licenses/BSD-3-Clause
#
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

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
