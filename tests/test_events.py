import base64
import json

import pytest
from pydantic import ValidationError

from services.bank.case import CaseState
from services.bank.events import CaseEvent, decode_push


def test_event_round_trip_through_push_envelope():
    ev = CaseEvent(type="case.kickoff", bank="alpha", case_id="c9", report="stolen funds")
    envelope = {"message": {"data": base64.b64encode(ev.model_dump_json().encode()).decode()}}
    assert decode_push(envelope) == ev


def test_unknown_event_type_rejected():
    with pytest.raises(ValidationError):
        CaseEvent(type="case.hack_the_planet", bank="alpha", case_id="c9")


def test_case_state_firestore_round_trip():
    # what CaseStore writes/reads: model_dump(mode="json") -> model_validate
    case = CaseState(case_id="c1", bank="alpha")
    case.log("alpha/test", "noted", "detail")
    restored = CaseState.model_validate(json.loads(json.dumps(case.model_dump(mode="json"))))
    assert restored == case
