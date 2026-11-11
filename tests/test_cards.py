"""Flash cards: the deck schema and loader, the /cards page, and reviews recorded like quiz answers
(a "Didn't know" comes back in spaced review until you know it)."""
from __future__ import annotations

import shutil

import pytest
import yaml
from conftest import REPO

from academy_server.content.loader import load_content
from academy_server.content.schema import Deck

DECK = REPO / "content" / "cards" / "build.yaml"


def test_the_build_deck_loads_without_errors():
    tree = load_content(REPO / "content")
    assert tree.errors == []
    deck = tree.decks["build"]
    assert len(deck.cards) == 14 and set(deck.tags) == {"workflow", "cost", "security", "gateway", "engineering"}
    assert all(c.source for c in deck.cards)


@pytest.mark.parametrize("change, message", [
    (lambda d: d["cards"].append(dict(d["cards"][0])), "duplicate card ids"),
    (lambda d: d["cards"][0].update(tag="nope"), "aren't in tags"),
    (lambda d: d["cards"][0].pop("source"), "source"),
    (lambda d: d["cards"][0].update(hint="extra"), "hint"),
])
def test_deck_schema_rejects_mistakes(change, message):
    data = yaml.safe_load(DECK.read_text(encoding="utf-8"))
    change(data)
    with pytest.raises(ValueError, match=message):
        Deck.model_validate(data)


def test_a_bad_deck_is_reported_with_its_path(tmp_path):
    content = tmp_path / "content"
    shutil.copytree(REPO / "content", content)
    (content / "cards" / "broken.yaml").write_text("id: broken\ntitle: x\ntags: {a: A}\ncards: []\n", encoding="utf-8")
    tree = load_content(content)
    assert "build" in tree.decks and "broken" not in tree.decks
    assert any(e.startswith("cards") and "broken.yaml" in e for e in tree.errors)


def test_cards_api_and_page(make_client):
    client = make_client()
    [deck] = client.get("/api/cards").json()["decks"]
    assert deck["id"] == "build" and len(deck["cards"]) == 14
    card = deck["cards"][0]
    assert card["front_html"].startswith("<p>") and "<strong>stateless</strong>" in card["back_html"]
    assert card["last"] is None and card["source"]

    page = client.get("/cards").text
    assert 'id="study"' in page and '<a href="/cards" aria-current="page">Flash cards</a>' in page
    assert '<a href="/cards">Flash cards</a>' in client.get("/").text       # in the top bar everywhere


def test_a_miss_comes_back_in_spaced_review_until_known(make_client):
    client = make_client()
    url = "/api/cards/build/one-lesson-per-session/review"
    r = client.post(url, json={"knew": False})
    assert r.status_code == 200 and r.json()["last"]["correct"] is False
    [m] = client.get("/api/mistakes").json()["still_wrong"]
    assert m["item_id"] == "cards:build:one-lesson-per-session" and m["module_id"] == "cards"
    assert m["concepts"] == ["workflow"] and m["type"] == "flashcard" and "stateless" in m["correct"]
    assert client.get("/api/mistakes", params={"module": "m02"}).json()["still_wrong"] == []   # not in /quiz m02

    home = client.get("/").text
    assert 'href="/cards#one-lesson-per-session"' in home and "Review the flash card" in home

    assert client.post(url, json={"knew": True}).json()["last"]["tries"] == 2
    mistakes = client.get("/api/mistakes").json()
    assert mistakes["still_wrong"] == [] and mistakes["fixed_after_retry"][0]["item_id"].endswith("one-lesson-per-session")
    card = client.get("/api/cards").json()["decks"][0]["cards"][0]
    assert card["last"]["correct"] is True


def test_flash_cards_get_their_own_share_of_spaced_review(make_client):
    """Eight older quiz misses don't push a missed card off the home page; the rest are counted."""
    client = make_client()
    store = client.app.state.store
    for i in range(8):
        store.record_quiz_attempt(item_id=f"m02.lab02.s01:q{i}", module_id="m02", type="mcq", answer=0,
                                  correct=False, step_id="m02.lab02.s01", question=f"question {i}")
    client.post("/api/cards/build/utf8/review", json={"knew": False})
    home = client.get("/").text
    assert 'href="/cards#utf8"' in home and "and 2 more, oldest first" in home


def test_unknown_deck_or_card_is_404(make_client):
    client = make_client()
    assert client.post("/api/cards/nope/x/review", json={"knew": True}).status_code == 404
    assert client.post("/api/cards/build/nope/review", json={"knew": True}).status_code == 404
    assert client.post("/api/cards/build/utf8/review", json={}).status_code == 422
