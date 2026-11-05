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

"""Framework-independent call result reporting for AI adapters."""

import time

from polaris.pkg.model.service import (
    RetStatus,
    ServiceCallResult,
    ServiceInfo,
)

from polaris_ai.log import get_ai_logger


class PolarisCallReporter:
    """Report one logical AI call without changing its business result."""

    def __init__(
        self,
        consumer,
        namespace: str,
        *,
        caller_service: str = "",
        labels: str = "",
        caller_ip: str = "",
        logger=None,
    ):
        if consumer is None:
            raise ValueError("A ConsumerAPI is required")
        self.consumer = consumer
        self.namespace = namespace.strip() or "default"
        self.caller_service = caller_service.strip()
        self.labels = labels
        self.caller_ip = caller_ip
        self.logger = logger if logger is not None else get_ai_logger("metrics")

    def _build_result(
        self,
        *,
        service: str,
        host: str,
        port: int,
        method: str,
        instance_type: str,
        started_at: float,
        success: bool,
        ret_code: int | None = None,
        timeout: bool = False,
    ):
        if not service or not host:
            return None
        status = RetStatus.RetSuccess if success else (
            RetStatus.RetTimeout if timeout else RetStatus.RetFail
        )
        return ServiceCallResult(
            ret_status=status,
            ret_code=ret_code,
            delay=max(0, int((time.monotonic() - started_at) * 1000)),
            method=method,
            caller_service=(
                ServiceInfo(namespace=self.namespace, service=self.caller_service)
                if self.caller_service else None
            ),
            caller_ip=self.caller_ip or None,
            labels=self.labels or None,
            instance_type=instance_type,
            namespace=self.namespace,
            service=service,
            host=host,
            port=port,
        )

    async def report(
        self,
        *,
        service: str,
        host: str,
        port: int,
        method: str,
        instance_type: str,
        started_at: float,
        success: bool,
        ret_code: int | None = None,
        timeout: bool = False,
    ):
        result = self._build_result(
            service=service,
            host=host,
            port=port,
            method=method,
            instance_type=instance_type,
            started_at=started_at,
            success=success,
            ret_code=ret_code,
            timeout=timeout,
        )
        if result is None:
            return
        try:
            await self.consumer.async_update_service_call_result(result)
        except Exception as error:
            self.logger.warning_throttled(
                ("report", instance_type, service),
                "Failed to report %s call for %s: %s", instance_type, service, error,
            )

    def report_sync(
        self,
        *,
        service: str,
        host: str,
        port: int,
        method: str,
        instance_type: str,
        started_at: float,
        success: bool,
        ret_code: int | None = None,
        timeout: bool = False,
    ):
        """Synchronously report one synchronous framework call."""
        result = self._build_result(
            service=service,
            host=host,
            port=port,
            method=method,
            instance_type=instance_type,
            started_at=started_at,
            success=success,
            ret_code=ret_code,
            timeout=timeout,
        )
        if result is None:
            return
        try:
            self.consumer.sync_update_service_call_result(result)
        except Exception as error:
            self.logger.warning_throttled(
                ("report-sync", instance_type, service),
                "Failed to report %s call for %s: %s", instance_type, service, error,
            )
