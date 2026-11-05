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

"""Polaris extensions for Python AI frameworks."""

from ._version import __version__
from .log import (
    PolarisAILogger,
    PolarisAILogOptions,
    configure_ai_logging,
    get_ai_logger,
    use_ai_logger,
)

__all__ = [
    "PolarisAILogOptions",
    "PolarisAILogger",
    "configure_ai_logging",
    "get_ai_logger",
    "use_ai_logger",
    "__version__",
]
