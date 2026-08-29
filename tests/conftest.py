"""Keep the unit suite hermetic.

Model Armor and Memory Bank are both network calls. A test that reaches for either is slow
when the network is there and slower when it is not — the client retry budget is measured in
tens of seconds. Both are designed to be absent: the gate's guarantee is rules plus Gemma,
and a fleet that cannot recall simply starts from nothing, as it always used to. So both are
off by default here, and the tests that care about them turn one on and stub the client
rather than calling Google.
"""

import pytest


@pytest.fixture(autouse=True)
def no_network_scanners(monkeypatch):
    monkeypatch.setenv("MODEL_ARMOR", "off")
    monkeypatch.setenv("AGENT_MEMORY", "off")
