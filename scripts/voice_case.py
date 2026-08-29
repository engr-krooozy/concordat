"""File a fraud report the way a customer actually files one: by talking.

Publishes a kickoff event carrying only a GCS URI. The fleet listens to the recording,
extracts the account, the amount and the window, writes its own case file, and runs the
same investigation it would have run from typed text — which is the point. The intake got
wider; the pipeline did not change.

    CLOUDSDK_ACTIVE_CONFIG_NAME=concordat BANK=alpha .venv/bin/python -m scripts.voice_case
"""

from __future__ import annotations

import os
import uuid

from services.bank.config import load_config
from services.bank.events import CaseEvent, EventBus

AUDIO = os.environ.get("VOICE_NOTE", "gs://concordat-alpha-intake/fraud-report.mp3")


def main() -> None:
    cfg = load_config()
    case_id = f"case-{uuid.uuid4().hex[:8]}"
    EventBus(cfg).publish(
        CaseEvent(
            type="case.kickoff",
            bank=cfg.bank,
            case_id=case_id,
            report_audio=AUDIO,
            # the fallback if the recording turns out to be unusable
            report="Customer reported a suspected unauthorised transfer by voice note.",
        )
    )
    print(f"filed {case_id} from {AUDIO}")
    print("watch it at https://mission-control-fa7ntw3nkq-uc.a.run.app")


if __name__ == "__main__":
    main()
