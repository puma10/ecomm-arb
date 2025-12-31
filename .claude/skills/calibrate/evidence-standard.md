# Evidence Standard

Detailed guide for the calibration evidence standard.

---

## Evidence Types

### Code Evidence
Point to specific file and line(s):
```
src/auth/validator.ts:42-50
```

Include what the code shows:
```
The validator uses bcrypt with cost factor 12, matching security requirements.
```

### Test/Verification Evidence
Command + result:
```
npm test auth → PASS (42/42 tests)
pytest tests/auth/ → PASS
```

Or test name + pass/fail:
```
test_password_hashing: PASS
test_token_expiry: FAIL (tokens never expire)
```

### Doc Evidence
URL + relevant excerpt (grounded):
```
https://docs.example.com/auth
> "Use PKCE for all OAuth flows. Authorization code without PKCE is deprecated."
```

### Measurement Evidence
Metric + how measured:
```
Response time: 150ms (p99)
Measured: load test with 1000 concurrent users, 10 minute sustained
```

### Discriminating Test
A test that would fail one option and pass another:
```
To determine if we need connection pooling:
- Run 100 concurrent DB queries
- Option A (no pooling): expect >5s latency
- Option B (pooling): expect <100ms latency
```

---

## Evidence Grades

| Grade | Meaning | When to Use |
|-------|---------|-------------|
| **VERIFIED** | Evidence exists and was checked | Code exists, test passes, doc confirmed |
| **GROUNDED** | Retrieved from authoritative source | Official docs, verified API |
| **ASSUMPTION** | No direct evidence | Mark confidence: HIGH/MED/LOW |
| **CONTESTED** | Multiple agents disagree | Preserve both positions |

---

## When Evidence is Required

| Claim Type | Evidence Required? |
|------------|-------------------|
| Architecture decision | YES - code or ADR |
| Security claim | YES - doc or test |
| Performance claim | YES - measurement |
| "This is best practice" | YES - doc link |
| "This won't work" | YES - test or reasoning |
| Minor implementation detail | NO |

---

## Assumption Handling

When you cannot provide evidence:

1. Mark as `ASSUMPTION`
2. Rate confidence: `HIGH` / `MED` / `LOW`
3. State what would verify or falsify it
4. If it affects architecture/security/correctness → apply stop/ask rule

Example:
```
ASSUMPTION (MED confidence):
The external API rate limits at 100 req/min.

Would verify: Check their docs or run a test.
Would falsify: Any evidence of different limit.

Impact: If lower, we need request queuing.
```

---

## Evidence in Templates

### Broadcast Analysis
```markdown
### My Evidence Pack
| Claim | Evidence | Type | Grade |
|-------|----------|------|-------|
| Auth is secure | `src/auth:42`, bcrypt cost 12 | Code | VERIFIED |
| API is fast | p99 < 100ms | Measurement | VERIFIED |
| DB will scale | No direct test | Assumption | MED |
```

### Challenge Response
```markdown
@Agent: REJECTED.
- My evidence: `tests/auth/test_tokens.py:30` shows tokens expire
- Your evidence: You cited line 25, which is setup code
- What would resolve: Run `pytest tests/auth/test_token_expiry.py -v`
```

### Decision
```markdown
## Decision: Use connection pooling

Evidence: Load test showed 5s latency without pooling, 80ms with.
Tradeoffs: +complexity, +infra cost, +reliability
Success: p99 < 100ms under load
Reversal: If pooler becomes single point of failure
```

---

## Common Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| "It's obvious" | Not evidence | State the evidence |
| Citing old docs | May be outdated | Add date, verify current |
| "I think..." | Opinion | Test or ground it |
| Line number without context | Can't verify | Include relevant code |
| Test name only | Can't reproduce | Include command |
