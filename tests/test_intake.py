"""A voice note has to become the same case a typed report would have.

The value of multimodal intake is that nothing downstream changes: the tracer, the policy
engine and the clean room never learn where the case came from. These check the seam — that
what the model hears is turned into the report shape the rest of the system already reads,
and that a bad recording opens a case anyway rather than losing a fraud report.
"""

import pytest

from services.bank.intake import VoiceReport, _extract_json


def test_a_heard_report_reads_like_the_typed_one():
    """The tracer's prompt looks for an account, an amount and a window. All three survive."""
    heard = VoiceReport(
        account="ALP-9000001",
        amount_ngn=2400000,
        when="the 12th, in the afternoon",
        when_date="2026-08-12",
        channel="web transfer",
        summary="Customer reports an unauthorised web transfer.",
    )

    report = heard.as_report()

    assert "ALP-9000001" in report
    assert "2,400,000 naira" in report
    assert "2026-08-12" in report
    assert "web transfer" in report
    assert report.endswith("trace where the funds went.")


def test_the_report_carries_an_absolute_date_not_the_caller_s_words():
    """Nobody says the year out loud. An early version passed "the twelfth of August"
    straight through and the investigator searched 2024, 2023, then 2021 — sensibly and
    exhaustively — for a ring that happened in 2026. Resolving the year is the intake's job."""
    heard = VoiceReport(account="ALP-9000001", when="the twelfth of August", when_date="2026-08-12")

    report = heard.as_report()

    assert "on 2026-08-12" in report
    # the caller's own phrasing is kept alongside it, not thrown away
    assert "the twelfth of August" in report


def test_an_unresolvable_date_falls_back_to_the_caller_s_words():
    """Better a vague report than a confidently wrong date."""
    report = VoiceReport(account="ALP-9000001", when="some time last week").as_report()

    assert "some time last week" in report
    assert "on " not in report.split("authorise")[1].split(".")[0]


def test_a_half_heard_report_still_opens_a_case():
    """A caller who never says the amount is still a caller reporting fraud. The report must
    stay grammatical rather than emitting 'approximately 0 naira' or a dangling None."""
    report = VoiceReport(account="ALP-9000001").as_report()

    assert "0 naira" not in report
    assert "None" not in report
    assert "an amount" in report and "recently" in report
    assert "unauthorised transfer" in report


def test_an_unnamed_channel_does_not_leak_the_placeholder():
    """'via unknown they did not authorise' would be the model's word, not English."""
    report = VoiceReport(account="ALP-9000001", amount_ngn=2400000, when="today").as_report()

    assert "unknown" not in report


@pytest.mark.parametrize(
    "raw",
    [
        '{"account": "ALP-9000001", "amount_ngn": 2400000}',
        '```json\n{"account": "ALP-9000001", "amount_ngn": 2400000}\n```',
        'Here is what I heard:\n{"account": "ALP-9000001", "amount_ngn": 2400000}\nHope that helps.',
    ],
)
def test_json_survives_the_ways_models_wrap_it(raw):
    """Asked for bare JSON, models fence it, preface it, or apologise around it anyway."""
    assert _extract_json(raw)["account"] == "ALP-9000001"


def test_unparseable_audio_yields_nothing_rather_than_a_guess():
    """No JSON means we do not know what was said. Inventing an account number here would
    put a real customer's funds under investigation on the strength of a hallucination."""
    assert _extract_json("I could not make out the recording.") == {}


def test_the_transcript_never_reaches_the_case_file():
    """The raw transcript is kept for debugging but excluded from serialisation: it is the
    customer's own words, and only the derived report needs to travel."""
    heard = VoiceReport(account="ALP-9000001", transcript="a frightened person, verbatim")

    assert "transcript" not in heard.model_dump()
