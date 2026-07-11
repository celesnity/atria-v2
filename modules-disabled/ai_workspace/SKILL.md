---
name: ai_workspace
description: Secure department document workspace for My Tasco (Tasco P1). A self-contained SQLite access database (users, roles, departments, classifications, access matrix, document metadata) seeded from the enterprise dataset, with department-based, role-aware access control and Manager+-only document upload. Use for enterprise knowledge browsing, permission checks, and secure file upload/retrieval — not for AI semantic search (deferred).
---

# AI Workspace — Secure Department Knowledge (Tasco P1)

Central, permission-aware document workspace. Every access decision is made in the
module's own SQLite database against the dataset's 4-tier security model
(Public / Internal / Confidential / Restricted) and 4 roles
(Employee / Manager / Director / Executive). Document files live on disk under
`data/uploads/`; the database is the authority for who may see what.

This slice covers the **secure workspace + upload** — it deliberately does NOT do AI
semantic search (that reuses the `enterprise_knowledge` module later).

## When to use

- Browse enterprise documents by department with correct, server-enforced permissions.
- Check whether a given user may access a given document (and why).
- Upload a new document into a department's shared workspace (Manager and above only).
- Demonstrate role-based access: sign in as different personas and see the view change.

## Access model (3-gate, department-isolated)

A document's knowledge space comes from its owning department: `COMP` → Company
Knowledge, `EXEC` → Executive Knowledge, any other → that department's Department
Knowledge. Access must pass all three gates (Executives bypass to full access):

1. Knowledge space — Company Knowledge → all employees; Department Knowledge → the
   owning department only; Executive Knowledge → Executives only.
2. Department — for Department Knowledge, the user's department must equal the
   document's.
3. Classification — `Public` is company-wide; `Restricted` is Executives only;
   `Internal`/`Confidential` add no cross-department access beyond gate 1–2.

Net effect: an employee sees **Company documents + their own department's
documents**; another department's documents — including its `Internal` ones — are
hidden. Confidential/Restricted are always protected. Executives see everything.

## Runbook

Run from `modules/ai_workspace/scripts/` as `python workspace.py <cmd>` (JSON to stdout).
First-time setup builds the DB + file store from the dataset:

```bash
python ../tools/seed_db.py          # seed 6 tables + 40 docs + file store (idempotent)

python workspace.py login --user U005 --password 12345678   # persona demo login (all users: 12345678)
python workspace.py whoami U004                              # identity + accessible classifications
python workspace.py folders --user U004                     # 8 department folders (locks + visible counts)
python workspace.py workspace --user U004 [--department ENG] # documents the user may access
python workspace.py can-access U004 DOC007                  # Allow/Deny + reason for one document
python workspace.py add-document --user U005 --file X.md --classification Confidential  # upload (Manager+)
python workspace.py read-document --user U013 --doc DOC041  # open a document (access-checked)
python workspace.py audit --limit 20                        # access / login / upload trail
python workspace.py health                                  # DB + uploads-dir probe
```

Environment overrides: `AIW_DB_PATH` (DB file), `AIW_UPLOADS_DIR` (file store),
`AIW_AUDIT_LOG` (audit trail).

## Guardrails (non-negotiable)

- Enforcement is **server-side**. Never rely on the UI hiding a control for security; every
  `workspace` / `folders` / `read-document` result is already filtered by the access predicate.
- **Upload is Manager and above only.** Employees are view-only. The uploader's department is
  taken from their account — never from user input; only `classification` is chosen at upload.
- Never widen access or return a document the predicate denies. `read-document` re-checks
  access at open time.
- The demo password `12345678` and trusted `user_id` are hackathon conveniences, not real
  authentication.

## Status

- ✅ SQLite access DB (6 tables) seeded from the dataset; FK-validated on seed.
- ✅ Department-secure browse (`folders`, `workspace`), per-document `can-access`, secure
  `read-document`, Manager+ `add-document` with on-disk file storage, audit trail, persona login.
- ⏳ Deferred: AI semantic search (Qdrant + `enterprise_knowledge` knowledge port), non-text
  file parsing, real authentication.
