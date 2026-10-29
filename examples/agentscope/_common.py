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

"""SDK setup shared by the AgentScope examples."""

import argparse
import os
from pathlib import Path

from polaris.api.config import init_context_by_config
from polaris.pkg.config.api import Configuration

from examples._internal._runtime import (
    configure_e2e_event_reporting,
    demo_backup_directory,
    demo_log_options,
)


def parser(description):
    arguments = argparse.ArgumentParser(description=description)
    arguments.add_argument("--config", help="Path to polaris.yaml")
    arguments.add_argument(
        "--address",
        default=os.environ.get("POLARIS_SERVER_ADDRESS"),
        help="Override the Polaris gRPC address",
    )
    arguments.add_argument(
        "--skill-address", default=os.environ.get("POLARIS_SKILL_SERVER_ADDRESS")
    )
    arguments.add_argument("--timeout", type=int, help="SDK API timeout in milliseconds")
    arguments.add_argument("--namespace", default="default")
    return arguments


def context(args, *, entry=None, component=None):
    config = Configuration.from_file(args.config) if args.config else Configuration.from_env()
    config.set_default()
    if args.address:
        config.global_config.server_connector.addresses = [args.address]
    if args.skill_address:
        config.get_ai().get_skill().get_server_connector().addresses = [args.skill_address]
    if args.timeout is not None:
        config.get_global().get_api().timeout = args.timeout
    if os.environ.get("POLARIS_DEMO_OFFLINE") == "1":
        config.get_global().get_api().bind_ip = "127.0.0.1"
        config.get_global().get_stat_reporter().enable = False
        config.get_global().get_event_reporter().enable = False
    else:
        configure_e2e_event_reporting(config)
    entry = entry or __file__
    component = component or Path(entry).parent.name
    root = demo_backup_directory(entry, component=component)
    config.get_consumer().get_local_cache().persist_dir = str(root / "instances")
    config.get_ai().get_skill().get_server_connector().persist_dir = str(root / "skills")
    return init_context_by_config(config, log_options=demo_log_options(entry, component=component))
