from calendar import monthrange
from datetime import date


def month_start(value: date) -> date:
    return value.replace(day=1)


def month_end(value: date) -> date:
    return value.replace(day=monthrange(value.year, value.month)[1])


def add_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def due_date_for(target_month: date, month_offset: int, due_day: int) -> date:
    shifted = add_months(month_start(target_month), month_offset)
    day = min(due_day, monthrange(shifted.year, shifted.month)[1])
    return shifted.replace(day=day)


def iter_months(start: date, end: date, step: int = 1):
    current = month_start(start)
    final = month_start(end)
    while current <= final:
        yield current
        current = add_months(current, step)
