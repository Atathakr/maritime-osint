## Summary

Brief description of what this PR does and why.

## Type of Change

- [ ] Bug fix
- [ ] New indicator implementation (IND__ — name)
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update
- [ ] Refactoring

## Related Issue

Closes #

## Changes Made

- `file.py` — description
- `db.py` — new tables / queries (if applicable)
- `docs/indicators.md` — updated status (if applicable)

## Indicator Changes (if applicable)

**Indicator:** IND__ — name
**Previous status:** Not yet implemented
**New status:** Implemented

Score formula added:
```
min(count × N, CAP)  -- INDXX  description
```

Constants added to `risk_config.py`:
```python
INDXX_PTS_PER_EVENT = N
INDXX_CAP           = M
```

## Testing

- [ ] Tested locally with SQLite
- [ ] Tested with PostgreSQL
- [ ] Verified detection output against real or synthetic data
- [ ] Verified risk score calculation for edge cases

**Test scenario:**

## Checklist

- [ ] `ruff check .` passes
- [ ] `ruff format .` applied
- [ ] All DB calls in `db.py`
- [ ] All scoring weights in `risk_config.py` (not hardcoded)
- [ ] All new endpoints have `@login_required`
- [ ] `docs/indicators.md` updated if indicator status changed
- [ ] No secrets, `.env` files, or database files in the diff
