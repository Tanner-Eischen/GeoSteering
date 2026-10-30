from __future__ import annotations

import numpy as np
import pandas as pd

from app.geo.formation import Scenario
from app.geo.observation_model import sample_logs


def sample_station(station: dict[str, float], scenario: Scenario, seed: int, step_index: int) -> dict[str, float]:
    # Step-keyed random streams keep noise comparable across different paths.
    stream_seed = int(np.random.SeedSequence([seed, step_index]).generate_state(1)[0])
    return {key: float(value) for key, value in sample_logs(pd.DataFrame([station]), scenario, stream_seed).iloc[0].items()}
