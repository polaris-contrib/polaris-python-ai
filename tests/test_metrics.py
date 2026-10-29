from unittest import IsolatedAsyncioTestCase

from polaris.pkg.model.service import InstanceType, RetStatus

from polaris_ai.metrics import PolarisCallReporter


class FakeConsumer:
    def __init__(self):
        self.results = []

    async def async_update_service_call_result(self, result):
        self.results.append(result)


class MetricsTests(IsolatedAsyncioTestCase):
    async def test_report_maps_ai_identity_and_failure_status(self):
        consumer = FakeConsumer()
        reporter = PolarisCallReporter(
            consumer,
            "production",
            caller_service="caller",
            labels="env=prod",
        )
        await reporter.report(
            service="agent",
            host="10.0.0.1",
            port=8080,
            method="message/send",
            instance_type=InstanceType.A2A,
            started_at=0,
            success=False,
            timeout=True,
            ret_code=504,
        )
        result = consumer.results[0]
        self.assertEqual(RetStatus.RetTimeout, result.get_ret_status())
        self.assertEqual("message/send", result.get_method())
        self.assertEqual(InstanceType.A2A, result.instance_type)
        self.assertEqual("production", result.get_namespace())
        self.assertEqual("agent", result.get_service())
        self.assertEqual("10.0.0.1", result.get_host())
        self.assertEqual("caller", result.caller_service.get_service())
        self.assertEqual("env=prod", result.labels)
