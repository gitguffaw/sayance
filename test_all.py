"""Aggregate unittest entrypoint so `python3 -m unittest` runs repo tests."""

from tests.test_canary_assert import *  # noqa: F401,F403
from tests.test_reporting_integrity import *  # noqa: F401,F403
from tests.test_token_accounting import *  # noqa: F401,F403

