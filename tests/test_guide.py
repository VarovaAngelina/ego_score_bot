"""Guide embed tests."""

from bot.utils.guide import GUIDE_EMBED_TITLE, build_guide_embed


def test_build_guide_embed() -> None:
    embed = build_guide_embed(top_limit=10)
    assert embed.title == GUIDE_EMBED_TITLE
    assert "Competitive" in embed.description
    assert "Swiftplay" in embed.description
    assert "Без ранга" in embed.description
    assert "/register" in embed.fields[1].value
    assert "топ-10" in embed.fields[1].value
    assert "ACS" in embed.fields[2].value
    assert "↑" in embed.fields[3].value
