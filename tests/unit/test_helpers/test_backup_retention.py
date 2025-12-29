import pytest
from datetime import datetime
from helpers.backup import get_backups_to_keep

TEST_CASES = [
    (
        "no_backups",
        [],
        {"daily": 7, "weekly": 4, "monthly": 12},
        set(),
    ),
    (
        "not_enough_backups",
        [datetime(2025, 1, 1)],
        {"daily": 7, "weekly": 4, "monthly": 12},
        {datetime(2025, 1, 1)},
    ),
    (
        "only_daily",
        [datetime(2025, 1, d) for d in range(1, 6)],
        {"daily": 2, "weekly": 0, "monthly": 0},
        {datetime(2025, 1, 5), datetime(2025, 1, 4)},
    ),
    (
        "weekly_and_daily",
        [datetime(2025, 1, d) for d in range(1, 15)],  # Jan 1 to 14
        {"daily": 2, "weekly": 2, "monthly": 1},
        {
            datetime(2025, 1, 14),  # daily
            datetime(2025, 1, 13),  # daily, weekly
            datetime(2025, 1, 6),  # weekly
            datetime(2025, 1, 1),  # monthly (and weekly)
        },
    ),
    (
        "multi_month",
        [datetime(2024, 12, d) for d in range(25, 32)]
        + [datetime(2025, 1, d) for d in range(1, 11)],
        {"daily": 3, "weekly": 2, "monthly": 2},
        {
            datetime(2025, 1, 10),  # daily
            datetime(2025, 1, 9),  # daily
            datetime(2025, 1, 8),  # daily
            datetime(2025, 1, 6),  # weekly
            datetime(2025, 1, 1),  # monthly
            datetime(2024, 12, 30),  # weekly
            datetime(2024, 12, 25),  # monthly (and weekly)
        },
    ),
    (
        "zero_policy",
        [datetime(2025, 1, d) for d in range(1, 11)],
        {"daily": 0, "weekly": 0, "monthly": 0},
        set(),
    ),
    (
        "more_retention_than_backups",
        [datetime(2025, 1, d) for d in range(1, 5)],
        {"daily": 10, "weekly": 10, "monthly": 10},
        {datetime(2025, 1, d) for d in range(1, 5)},
    ),
    (
        "first_backup_is_kept",
        [datetime(2025, 1, 1), datetime(2025, 1, 2)],
        {"daily": 1, "weekly": 1, "monthly": 1},
        {datetime(2025, 1, 2), datetime(2025, 1, 1)},
    ),
]


@pytest.mark.parametrize(
    "test_id, dates, policy, expected", TEST_CASES, ids=[t[0] for t in TEST_CASES]
)
def test_get_backups_to_keep(test_id, dates, policy, expected):
    """
    Tests the get_backups_to_keep function with various scenarios.

    Args:
        test_id: An identifier for the test case.
        dates: A list of datetime objects representing backup dates.
        policy: A dictionary defining the retention policy.
        expected: A set of datetime objects that should be kept.
    """
    result = get_backups_to_keep(dates, policy)
    assert result == expected
