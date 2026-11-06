"""Cost from usage, priced by pricing.yaml in Decimal."""
from conftest import REPO

from academy_server.pricing import Pricing

PRICES = Pricing.load(REPO / "pricing.yaml")


def test_matches_the_gateways_cost_for_the_first_live_run():
    # 22 in x $4/M + 66 out x $20/M; the gateway's x-litellm-response-cost-original said the same.
    assert PRICES.cost_usd("claude-opus-5-5", {"input_tokens": 22, "output_tokens": 66}) == 0.001408


def test_cache_reads_and_both_write_ttls():
    usage = {"input_tokens": 1000, "output_tokens": 100, "cache_read_input_tokens": 2000,
             "cache_creation_input_tokens": 1000, "cache_creation": {"ephemeral_1h_input_tokens": 400}}
    # 1000x4 + 100x20 + 2000x0.20 + 600x5 (5-minute writes) + 400x8 (1-hour writes) = 12,600 per million
    assert PRICES.cost_usd("claude-opus-5-5", usage) == 0.0126


def test_haiku_4_5_is_priced():
    # 1000 x $1 + 100 x $5 per million
    assert PRICES.cost_usd("claude-haiku-4-5", {"input_tokens": 1000, "output_tokens": 100}) == 0.0015


def test_no_price_without_a_known_model_or_usage():
    assert PRICES.cost_usd("not-a-model", {"input_tokens": 10}) is None
    assert PRICES.cost_usd("claude-opus-5-5", None) is None
