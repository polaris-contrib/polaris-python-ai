from unittest.mock import patch

from polaris_ai.agentscope.context import (
    DEFAULT_DISCOVERY_ADDRESS,
    PolarisAgentContext,
    derive_skill_addresses,
)
from tests._support import FakeContext, FakeEngine


def test_skill_address_derivation_supports_hosts_ipv6_and_deduplication():
    assert derive_skill_addresses([
        "example.com:8091",
        "127.0.0.1:8091",
        "[2001:db8::1]:8091",
        "example.com:8092",
    ]) == [
        "example.com:8094",
        "127.0.0.1:8094",
        "[2001:db8::1]:8094",
    ]


def test_invalid_skill_address_derivation_is_rejected():
    for addresses in (
        [],
        ["example.com"],
        ["example.com:http"],
        ["example.com:0"],
        ["example.com:65536"],
        ["2001:db8::1:8091"],
        ["  "],
    ):
        try:
            derive_skill_addresses(addresses)
        except ValueError:
            continue
        raise AssertionError(f"Expected invalid addresses to fail: {addresses}")


def test_owned_context_uses_java_address_rules_and_closes_once():
    context = FakeContext(FakeEngine())
    created_configs = []

    def initialize(config, *, log_options=None):
        created_configs.append(config)
        return context

    with patch("polaris_ai.agentscope.context.init_context_by_config", side_effect=initialize):
        manager = PolarisAgentContext.from_address(
            ["127.0.0.1:8091", "[2001:db8::2]:18091"],
            "production",
            connector_token="connector-token",
        )
        assert manager.owns_context
        assert manager.context is context
        assert manager.namespace == "production"
        assert manager.provider.context is context
        assert manager.consumer.context is context
        assert manager.skill.context is context
    config = created_configs[0]
    assert not config.get_global().get_stat_reporter().is_enable()
    assert not config.get_provider().get_lossless().is_enable()
    assert config.get_ai().get_skill().get_server_connector().addresses == [
        "127.0.0.1:8094",
        "[2001:db8::2]:8094",
    ]
    manager.close()
    assert context.is_destroy()
    manager.close()


def test_owned_context_does_not_modify_supplied_context_and_does_not_destroy_it():
    context = FakeContext(FakeEngine())
    manager = PolarisAgentContext("default", sdk_context=context)
    assert not manager.owns_context
    manager.close()
    assert not context.is_destroy()


def test_partial_api_initialization_failure_closes_created_context():
    context = FakeContext(FakeEngine())

    class BrokenProvider:
        def __init__(self, value):
            raise RuntimeError("provider initialization failed")

    with (
        patch("polaris_ai.agentscope.context.init_context_by_config", return_value=context),
        patch("polaris_ai.agentscope.context.ProviderAPI", BrokenProvider),
    ):
        try:
            PolarisAgentContext.from_address(DEFAULT_DISCOVERY_ADDRESS)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Expected provider initialization failure")
    assert context.is_destroy()
