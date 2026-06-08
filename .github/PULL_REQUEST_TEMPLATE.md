## Summary

- 

## Changes

- 

## Verification

- [ ] Backend tests run or reason provided
- [ ] Frontend checks run or reason provided
- [ ] Legacy runtime read guard run or reason provided
- [ ] Documentation updated when behavior changed

## Risk Checklist

- [ ] No API keys, private manuscripts, local databases, uploads, or LLM traces committed
- [ ] Database schema changes use a new Alembic revision
- [ ] LLM module behavior and prompt changes are explicit
- [ ] No silent fallback, mock success path, or hidden degradation added
- [ ] No new legacy JSON / standalone SQLite runtime read paths added
