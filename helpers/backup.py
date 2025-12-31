from datetime import datetime
from typing import Dict, List, Set, Tuple


def get_week_of_year(date: datetime) -> Tuple[int, int]:
    """
    Calculates the ISO week key for a given date.

    Args:
        date: A datetime object.

    Returns:
        A tuple containing the year and week number.
    """
    iso_calendar = date.isocalendar()
    return (iso_calendar[0], iso_calendar[1])


def get_month_of_year(date: datetime) -> Tuple[int, int]:
    """
    Calculates the month key for a given date.

    Args:
        date: A datetime object.

    Returns:
        A tuple containing the year and month.
    """
    return (date.year, date.month)


def mark_backups(dates: List[datetime]) -> Dict[datetime, Set[str]]:
    """
    Assigns retention markers (daily, weekly, monthly) to each backup date.

    Args:
        dates: A list of backup dates, sorted ascendingly (oldest first).

    Returns:
        A dictionary mapping each date to a set of markers.
    """
    if not dates:
        return {}

    result = {}
    seen_weeks = set()
    seen_months = set()

    for i, date in enumerate(dates):
        markers = set()
        markers.add("daily")

        week_key = get_week_of_year(date)
        month_key = get_month_of_year(date)

        if week_key not in seen_weeks:
            markers.add("weekly")
            seen_weeks.add(week_key)

        if month_key not in seen_months:
            markers.add("monthly")
            seen_months.add(month_key)

        # first backup always gets weekly and monthly markers
        if i == 0:
            markers.add("weekly")
            markers.add("monthly")

        result[date] = markers

    return result


def get_backup_to_keep(
    markers_map: Dict[datetime, Set[str]], policy: Dict[str, int]
) -> Set[datetime]:
    """
    Applies a retention policy to determine which backups to keep.

    Args:
        markers_map: A dictionary mapping dates to a set of markers.
        policy: A dictionary with 'daily', 'weekly', 'monthly' keys and quota values.

    Returns:
        A set of dates that should be kept.
    """
    sorted_dates = sorted(markers_map.keys(), reverse=True)

    kept_monthly = []
    kept_weekly = []
    kept_daily = []

    dates_to_keep = set()

    for date in sorted_dates:
        markers = markers_map.get(date, set())
        should_keep = False

        if "monthly" in markers and len(kept_monthly) < policy.get("monthly", 0):
            kept_monthly.append(date)
            should_keep = True

        if "weekly" in markers and len(kept_weekly) < policy.get("weekly", 0):
            kept_weekly.append(date)
            should_keep = True

        if "daily" in markers and len(kept_daily) < policy.get("daily", 0):
            kept_daily.append(date)
            should_keep = True

        if should_keep:
            dates_to_keep.add(date)

    return dates_to_keep


def get_backups_to_keep(dates: List[datetime], policy: Dict[str, int]) -> Set[datetime]:
    """
    Applies a retention policy to a list of dates.

    Args:
        dates: A list of backup dates.
        policy: A dictionary with 'daily', 'weekly', 'monthly' keys and quota values.

    Returns:
        A set of dates that should be kept according to the policy.
    """
    if not dates:
        return set()

    sorted_dates = sorted(dates)
    markers = mark_backups(sorted_dates)
    return get_backup_to_keep(markers, policy)
