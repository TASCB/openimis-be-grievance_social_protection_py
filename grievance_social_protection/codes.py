"""Codes of the grievance setup lists (categories, types, channels), given by the backend.

A code is the list's prefix and a running number, at least three digits: GC001, GT056, GCH002. People
never type them; they are given when an entry is first saved and never change.
"""
import re

PREFIXES = {
    'GrievanceCategory': 'GC',
    'GrievanceType': 'GT',
    'GrievanceChannel': 'GCH',
}


def next_code(model, prefix):
    """The next free code of `model`: one past the highest number used so far, deleted entries included."""
    pattern = re.compile(rf'^{re.escape(prefix)}(\d+)$')
    highest = 0
    for code in model.objects.filter(code__startswith=prefix).values_list('code', flat=True):
        match = pattern.match(code or '')
        if match:
            highest = max(highest, int(match.group(1)))
    return f'{prefix}{highest + 1:03d}'


def missing_code(code):
    return not (code or '').strip()
