"""Tests for market mapping — event to token/market eşleşme."""

import pytest
from backend.market_data.mapping import (
    MarketMapper,
    MarketMap,
    MarketSide,
    MappingStatus,
    TokenMapping,
)


def _make_event(
    condition_id="0xabc",
    question="Will BTC go up in the next 5 minutes?",
    tokens=None,
):
    event = {"conditionId": condition_id, "question": question}
    if tokens is not None:
        event["tokens"] = tokens
    return event


def _make_tokens():
    return [
        {"token_id": "tok_up", "outcome": "Up"},
        {"token_id": "tok_down", "outcome": "Down"},
    ]


# ===== Successful Mapping Tests =====

class TestSuccessfulMapping:
    def test_map_event_with_tokens(self):
        mapper = MarketMapper()
        result = mapper.map_event(_make_event(tokens=_make_tokens()))

        assert result.status == MappingStatus.MAPPED
        assert result.condition_id == "0xabc"
        assert result.asset == "BTC"
        assert len(result.tokens) == 2

    def test_up_down_sides_classified(self):
        mapper = MarketMapper()
        result = mapper.map_event(_make_event(tokens=_make_tokens()))

        assert result.up_token is not None
        assert result.up_token.side == MarketSide.UP
        assert result.up_token.token_id == "tok_up"

        assert result.down_token is not None
        assert result.down_token.side == MarketSide.DOWN
        assert result.down_token.token_id == "tok_down"

    def test_is_complete_with_both_sides(self):
        mapper = MarketMapper()
        result = mapper.map_event(_make_event(tokens=_make_tokens()))
        assert result.is_complete is True

    def test_frozen_model(self):
        mapper = MarketMapper()
        result = mapper.map_event(_make_event(tokens=_make_tokens()))
        with pytest.raises(AttributeError):
            result.status = MappingStatus.UNMAPPABLE

    def test_mapped_at_timestamp(self):
        mapper = MarketMapper()
        result = mapper.map_event(_make_event(tokens=_make_tokens()))
        assert result.mapped_at is not None


# ===== Unmappable Event Tests =====

class TestUnmappableEvents:
    def test_no_tokens_returns_unmappable(self):
        mapper = MarketMapper()
        result = mapper.map_event(_make_event(tokens=[]))

        assert result.status == MappingStatus.UNMAPPABLE
        assert len(result.tokens) == 0

    def test_missing_condition_id_returns_unmappable(self):
        mapper = MarketMapper()
        result = mapper.map_event({"question": "Will BTC go up?"})

        assert result.status == MappingStatus.UNMAPPABLE
        assert result.condition_id == ""

    def test_no_token_field_returns_unmappable(self):
        mapper = MarketMapper()
        result = mapper.map_event(_make_event())  # no tokens param

        assert result.status == MappingStatus.UNMAPPABLE

    def test_unmappable_has_no_up_down(self):
        mapper = MarketMapper()
        result = mapper.map_event(_make_event(tokens=[]))
        assert result.up_token is None
        assert result.down_token is None
        assert result.is_complete is False


# ===== Duplicate / Ambiguous Tests =====

class TestDuplicateMapping:
    def test_single_side_not_complete(self):
        """Only one token → not complete."""
        mapper = MarketMapper()
        result = mapper.map_event(_make_event(tokens=[
            {"token_id": "tok_up", "outcome": "Up"},
        ]))

        assert result.status == MappingStatus.MAPPED
        assert result.is_complete is False
        assert result.up_token is not None
        assert result.down_token is None

    def test_tokens_with_missing_id_skipped(self):
        """Tokens without token_id are skipped."""
        mapper = MarketMapper()
        result = mapper.map_event(_make_event(tokens=[
            {"token_id": "tok_up", "outcome": "Up"},
            {"outcome": "Down"},  # no token_id
        ]))

        assert len(result.tokens) == 1


# ===== Side Classification Tests =====

class TestSideClassification:
    def test_yes_is_up(self):
        mapper = MarketMapper()
        assert mapper._classify_side("Yes") == MarketSide.UP

    def test_no_is_down(self):
        mapper = MarketMapper()
        assert mapper._classify_side("No") == MarketSide.DOWN

    def test_up_keyword(self):
        mapper = MarketMapper()
        assert mapper._classify_side("Up") == MarketSide.UP

    def test_higher_is_up(self):
        mapper = MarketMapper()
        assert mapper._classify_side("Higher") == MarketSide.UP

    def test_unknown_defaults_to_down(self):
        mapper = MarketMapper()
        assert mapper._classify_side("something") == MarketSide.DOWN


# ===== Boundary Tests =====

class TestMappingBoundaries:
    def test_no_ptb_import(self):
        import backend.market_data.mapping as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "ptb" not in line.lower()

    def test_no_strategy_import(self):
        import backend.market_data.mapping as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "execution" not in line

    def test_no_registry_import(self):
        import backend.market_data.mapping as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "registry" not in line
