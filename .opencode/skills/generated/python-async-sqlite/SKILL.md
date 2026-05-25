---
name: python-async-sqlite
description: Safe patterns for using SQLite with asyncio in FastAPI and other async Python applications. Covers the async-to-thread trap, cursor thread-safety, and transaction rollback handling.
generated_from_knowledge:
  - 43ddee40-0354-471b-9029-37b551c5fb3a
  - b4bf4f8a-f45a-4e38-a80a-d4273fa888e7
  - bce3ec82-583e-48f8-ba06-2ab5a7c41931
confidence: 0.85
status: active
---

# Python Async SQLite Patterns

## Trigger

Use this skill when:
- Wrapping synchronous SQLite operations in asyncio.to_thread()
- Refactoring sync database code to async in FastAPI/Starlette
- Reviewing code that uses SQLite with asyncio
- Debugging "coroutine object has no attribute" errors from database calls

## Required Procedure

### 1. NEVER pass async functions to asyncio.to_thread()

**WRONG:**
```python
async def get_user(db, user_id):
    return await asyncio.to_thread(_fetch_user, db, user_id)  # OK if _fetch_user is sync

async def _fetch_user(db, user_id):  # async function!
    cursor = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()
```

**RIGHT:**
```python
def _fetch_user(db, user_id):  # MUST be sync
    cursor = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

async def get_user(db, user_id):
    return await asyncio.to_thread(_fetch_user, db, user_id)
```

### 2. Consolidate execute + fetch in a single to_thread call

This rule also applies to `executemany()` and any other operation that returns a cursor:

```python
# RIGHT — executemany consolidated
def _bulk_insert(db, rows):
    cursor = db.executemany("INSERT INTO users (name) VALUES (?)", rows)
    return cursor.rowcount

async def bulk_insert_users(db, rows):
    return await asyncio.to_thread(_bulk_insert, db, rows)
```

**WRONG:**
```python
async def get_user(db, user_id):
    # CURSOR IS NOT THREAD-SAFE — never do this
    cursor = await asyncio.to_thread(db.execute, "SELECT * FROM users WHERE id = ?", (user_id,))
    return await asyncio.to_thread(cursor.fetchone)  # cursor may be corrupted!
```

**RIGHT:**
```python
def _fetch_user(db, user_id):
    cursor = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

async def get_user(db, user_id):
    return await asyncio.to_thread(_fetch_user, db, user_id)
```

**OR using lambda:**
```python
async def get_user(db, user_id):
    return await asyncio.to_thread(
        lambda: db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    )
```

### 3. Use named functions with internal rollback for transactions

**WRONG:**
```python
async def create_user(db, user_data):
    def _create():
        db.execute("INSERT INTO users ...", user_data)
        db.commit()
    
    try:
        return await asyncio.to_thread(_create)
    except sqlite3.IntegrityError:
        # BUG: rollback runs in a NEW thread — not the same thread as the transaction!
        await asyncio.to_thread(db.rollback)
```

**RIGHT:**
```python
async def create_user(db, user_data):
    def _create():
        try:
            cursor = db.execute("INSERT INTO users ...", user_data)
            db.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            db.rollback()
            raise
    
    return await asyncio.to_thread(_create)
```

### 4. Set check_same_thread=False on connections used with to_thread

```python
db = sqlite3.connect(
    database_path,
    check_same_thread=False  # Required when connection is used across threads via to_thread
)
```

### 5. Update ALL callers when changing sync → async signatures

When you convert a sync function to async, every direct caller must be updated:

**WRONG:**
```python
# deps.py — converted to async
async def get_user_orgs(db, user_id):
    return await asyncio.to_thread(lambda: ...)

# vaults.py — caller NOT updated
orgs = get_user_orgs(db, user_id)  # Returns coroutine object, not result!
```

**RIGHT:**
```python
# vaults.py — caller updated with await
orgs = await get_user_orgs(db, user_id)
```

Always run a full-text search for the function name across the codebase after changing its signature.

## Forbidden Shortcuts

- NEVER split execute() and fetch*() across separate to_thread calls
- NEVER pass async functions to asyncio.to_thread()
- NEVER rely on exception handlers outside the to_thread lambda for rollback — the lambda runs in a different thread
- NEVER forget check_same_thread=False when creating connections for async use

## Known Existing Violations

Some production codebases (including RAGAPPv3's `vaults.py`) may still use the split execute/fetch pattern. These are **known technical debt** — the skill's rules represent the target state. When reviewing code with existing violations, flag them for cleanup but do not block new features on unrelated existing debt.

## Connection Pool Notes

When using `SQLiteConnectionPool` or similar pool implementations:
- Pool checkout (getting a connection) is typically sync and safe to wrap in `to_thread`
- The same consolidation rule applies: all DB operations on a checked-out connection must be in a single lambda
- `check_same_thread=False` should be set on connections created by the pool factory, not by consumers

## Common Error Signatures

| Error | Cause | Fix |
|-------|-------|-----|
| "coroutine object has no attribute 'fetchone'" | Async function passed to to_thread | Make the function synchronous |
| "SQLite objects created in a thread can only be used in that same thread" | Cursor split across to_thread calls | Consolidate into single lambda |
| "database is locked" | Multiple threads accessing connection without check_same_thread=False | Add check_same_thread=False |
| Partial transaction state after exception | Rollback not handled inside lambda | Move rollback into named function |

## Delegation Template

When delegating a task affected by this skill, include:

```
SKILLS: file:.opencode/skills/generated/python-async-sqlite/SKILL.md
```

## Reviewer Checks

- [ ] No async functions passed to asyncio.to_thread()
- [ ] All execute() + fetch*() pairs consolidated in single to_thread call
- [ ] Transaction rollbacks handled inside the lambda/function, not outside
- [ ] check_same_thread=False set on connections used with to_thread
- [ ] All callers updated when function signature changes sync→async

## Source Knowledge IDs

- 43ddee40-0354-471b-9029-37b551c5fb3a (hive) — NEVER pass async functions to asyncio.to_thread()
- b4bf4f8a-f45a-4e38-a80a-d4273fa888e7 (hive) — SQLite cursor objects are NOT thread-safe
- bce3ec82-583e-48f8-ba06-2ab5a7c41931 (swarm) — RAGAPPv3 SQLite async pattern with named rollback functions
