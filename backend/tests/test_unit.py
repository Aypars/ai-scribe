from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.api.v1.tasks import _reject_past_due
from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.people import names_match
from app.services.meeting_lang import normalize_lang, speaker_prefix
from app.services.speakers import (
    is_generic_label,
    parse_named_attendees,
    rewrite_labels,
    rewrite_name_list,
    strip_guess_mark,
)
from app.services.storage import StorageError, save_audio
from app.services.turkish import lower_tr


def test_lower_tr_dotted_i():
    assert lower_tr("İstanbul") == "istanbul"
    assert lower_tr("Işık") == "ışık"


def test_names_match_ignores_case_and_i():
    assert names_match("Hasan", "hasan")
    assert names_match("İrem", "irem")
    assert not names_match("Hasan", "Hasan Can")


def test_generic_speaker_labels():
    assert is_generic_label("Konuşmacı F")
    assert is_generic_label("Speaker A")
    assert not is_generic_label("Hasan")
    assert not is_generic_label("Eleman")


def test_parse_named_attendees_splits_and_dedupes():
    assert parse_named_attendees("Ali, ayşe; Ali") == ["Ali", "Ayşe"]
    assert parse_named_attendees("Konuşmacı C") == []


def test_rewrite_name_list_and_labels():
    assert rewrite_name_list("Ali, Konuşmacı C", {"Konuşmacı C": "Hasan"}) == "Ali, Hasan"
    assert rewrite_labels("Konuşmacı C söz aldı", {"Konuşmacı C": "Hasan"}) == "Hasan söz aldı"


def test_strip_guess_mark():
    assert strip_guess_mark("Ali ?") == "Ali"
    assert strip_guess_mark("Ali") == "Ali"


def test_normalize_lang():
    assert normalize_lang("en") == "en"
    assert normalize_lang("English") == "en"
    assert normalize_lang("tr") == "tr"
    assert normalize_lang(None) == "tr"


def test_speaker_prefix_default_turkish():
    assert speaker_prefix() == "Konuşmacı"


def test_password_hash_roundtrip():
    hashed = hash_password("gizli12")
    assert hashed != "gizli12"
    assert verify_password("gizli12", hashed)
    assert not verify_password("yanlis", hashed)


def test_access_token_contains_user():
    import jwt

    from app.core.config import settings
    from app.core.security import ALGORITHM

    token = create_access_token(42)
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert payload["sub"] == "42"


def test_reject_past_due_required():
    with pytest.raises(HTTPException) as err:
        _reject_past_due(None, required=True)
    assert err.value.status_code == 422

    yesterday = date.today() - timedelta(days=1)
    with pytest.raises(HTTPException) as err:
        _reject_past_due(yesterday, required=True)
    assert "geçmiş" in err.value.detail

    today = date.today()
    assert _reject_past_due(today, required=True) == today


def test_save_audio_rejects_bad_type(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    with pytest.raises(StorageError):
        save_audio(1, "notlar.txt", b"hello")
    path = save_audio(1, "kisa.mp3", b"not-empty")
    assert path.endswith(".mp3")
    assert (tmp_path / path).is_file()


def test_smooth_word_speakers_drops_sandwiched_flips():
    from app.services.transcription import _smooth_word_speakers

    e, b = "Konuşmacı E", "Konuşmacı B"
    assert _smooth_word_speakers([e, b, e, e, b, e, e]) == [e] * 7


def test_group_words_keeps_one_speaker_on_flicker():
    from app.services.transcription import _group_words_by_speaker

    groups = _group_words_by_speaker(
        {
            "text": "tane önergemiz vardır başkanım",
            "start": 40,
            "speaker": "SPEAKER_04",
            "words": [
                {"word": "tane", "start": 40.0, "speaker": "SPEAKER_04"},
                {"word": "önergemiz", "start": 40.2, "speaker": "SPEAKER_01"},
                {"word": "vardır", "start": 40.4, "speaker": "SPEAKER_04"},
                {"word": "başkanım", "start": 40.6, "speaker": "SPEAKER_04"},
            ],
        }
    )
    assert len(groups) == 1
    assert groups[0][1] == "tane önergemiz vardır başkanım"
    assert groups[0][2] == "Konuşmacı E"


def test_fit_word_times_pulls_late_alignment_to_segment():
    from app.services.transcription import _fit_word_times, _group_words_by_speaker

    fitted = _fit_word_times(25.0, 40.0, [33.0, 34.0, 39.0])
    assert fitted[0] == pytest.approx(25.0)
    assert fitted[-1] == pytest.approx(40.0)

    groups = _group_words_by_speaker(
        {
            "text": "önergemiz vardır başkanım",
            "start": 25,
            "end": 32,
            "speaker": "SPEAKER_04",
            "words": [
                {"word": "önergemiz", "start": 33.0, "speaker": "SPEAKER_04"},
                {"word": "vardır", "start": 34.0, "speaker": "SPEAKER_04"},
                {"word": "başkanım", "start": 39.0, "speaker": "SPEAKER_04"},
            ],
        }
    )
    assert groups[0][0] == pytest.approx(25.0)


def test_collapse_flicker_merges_short_islands():
    from app.services.transcription import TranscriptSegment, collapse_speaker_flicker

    rows = [
        TranscriptSegment(40, "tane", "Konuşmacı E"),
        TranscriptSegment(40, "önergemiz", "Konuşmacı B"),
        TranscriptSegment(40, "vardır başkanım.", "Konuşmacı E"),
        TranscriptSegment(41, "Okutulmasını,", "Konuşmacı E"),
        TranscriptSegment(42, "gündeme alınmasını", "Konuşmacı B"),
        TranscriptSegment(43, "talep ediyoruz.", "Konuşmacı E"),
    ]
    out = collapse_speaker_flicker(rows)
    speakers = {row.speaker for row in out}
    assert speakers == {"Konuşmacı E"}
    joined = " ".join(row.text for row in out)
    assert "önergemiz" in joined
    assert "gündeme alınmasını" in joined
    assert "talep ediyoruz" in joined


def test_spread_long_lines_assigns_later_timestamps():
    from app.services.transcription import TranscriptSegment, spread_long_lines

    text = " ".join(f"kelime{i}" for i in range(30))
    out = spread_long_lines(
        [
            TranscriptSegment(50, text, "Konuşmacı E"),
            TranscriptSegment(80, "son.", "Konuşmacı E"),
        ]
    )
    assert len(out) >= 3
    assert out[0].timestamp == 50
    assert out[1].timestamp > 50
    assert out[-1].timestamp == 80
