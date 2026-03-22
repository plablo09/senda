---
date: 2026-03-22
topic: phase-4-content-hierarchy-auth
---

# Phase 4: Content Hierarchy, Auth & Access

## Problem Frame

Senda has a flat, auth-free content model (Documento, Dataset) that works for development but cannot support real teacher-student workflows. Teachers have no ownership over their content, students have no persistent identity, and there is no organizational structure grouping Lessons into Courses or Programmes. Phase 4 introduces the content hierarchy, authentication, and access model that make the platform usable in production — while maintaining a sharp anti-LMS boundary.

**Anti-LMS principle (standing constraint for all Phase 4 decisions):** Senda's scope is limited to content that requires code execution or LLM feedback. Everything else — syllabi, static readings, MCQ quizzes, gradebooks, discussion forums — belongs to Moodle or whatever LMS the teacher already uses.

---

## Requirements

### Content Hierarchy

- R1. Introduce three organizational levels: **Programme → Course → Lesson**.
  - **Programme**: top-level container, teacher-facing navigation only. No access control or enrollment at this level.
  - **Course**: the enrollment unit. Has members (enrolled students), an invite link, and an ordered list of Lessons.
  - **Lesson**: maps 1:1 to a Documento. No new content type; the existing block editor and render pipeline are unchanged.
- R2. A Documento that is not attached to any Lesson remains valid (drafts, standalone use). The hierarchy is additive, not a mandatory wrapper.
- R3. Teachers can create, edit, reorder, and delete Programmes, Courses, and Lessons from the teacher UI (in Spanish).

### Quiz Blocks

- R4. A quiz block is a regular exercise block with two optional teacher-authored fields: a **reference solution** (model answer code) and a **quality review** flag that enables LLM code assessment.
- R5. When a student runs a quiz block and their code executes without error, they may optionally request an **LLM quality review**. The LLM assesses the student's code for correctness of approach, conciseness, and idiomatic style — and gives a direct assessment (not Socratic). The student decides whether to request this; it is not automatic.
- R6. After attempting a quiz block, the student may choose to **reveal the teacher's reference solution**. This is always optional and student-initiated; it is never shown automatically.
- R7. On execution error, LLM Socratic feedback applies exactly as it does for regular exercises — unchanged behavior.
- R8. Quiz results are **not graded, not recorded server-side, and not passed to any external system**. This is formative self-check only. There is no pass/fail indicator.

### Authentication

- R9. Teachers authenticate with email + password. A teacher account owns the Programmes, Courses, and Lessons they create.
- R10. Students authenticate with email + password. Student accounts are created via Course invite link (see R12).
- R11. All write operations on Programmes, Courses, Lessons, and Datasets require an authenticated teacher session. Unauthenticated users can only access published student-facing Lesson artifacts (as today).
- R12. The auth model must be designed to accommodate future **Moodle LTI integration** without requiring a structural rewrite. Specifically: student identity should be representable as either a Senda-native account or an externally-asserted identity (LTI subject claim). This is a design constraint, not a Phase 4 deliverable.

### Access & Enrollment

- R13. A teacher can generate a **Course invite link**. Any user who follows the link is prompted to register or log in, then is automatically enrolled in that Course.
- R14. Enrollment is at **Course level only**. Programme membership is derived (a student enrolled in any Course within a Programme can see that Programme in their navigation).
- R15. Enrolled students can access all Lessons within their enrolled Courses. They cannot access Lessons in Courses they are not enrolled in.
- R16. A teacher can view the list of enrolled students for a Course (names/emails). No analytics or per-student progress in Phase 4.

### Database Migrations

- R17. Replace the current `Base.metadata.create_all` startup pattern with proper **Alembic migrations**. All schema changes in Phase 4 are introduced via migration files. This is a technical prerequisite, not a user-visible feature.

---

## Success Criteria

- A teacher can register, create a Programme and Course, author a Lesson with at least one quiz block, generate an invite link, and share it.
- A student can follow the invite link, register, access the Course, run exercises and quiz blocks, and receive pass/fail feedback and LLM hints.
- Unauthenticated access to a teacher's content management UI is rejected.
- A student not enrolled in a Course cannot access its Lessons.
- No grade data is stored or transmitted anywhere.

---

## Scope Boundaries

- **No Moodle LTI in Phase 4.** Auth is designed to be LTI-compatible, but no LTI implementation.
- **No teacher analytics UI in Phase 4.** The `ejecucion_errores` table continues to accumulate data; the analytics UI is deferred until real usage patterns are known.
- **No traditional quizzes** (MCQ, true/false, short answer). All quiz blocks are code-execution-based.
- **No grade passback or gradebook** of any kind.
- **No student roster management** beyond viewing the enrolled list. No manual add/remove in Phase 4.
- **No per-student progress tracking** server-side. Student progress remains local (IndexedDB or in-session) for Phase 4.
- **No OpenStack deploy or production infrastructure changes** in Phase 4 (moved to Phase 5).
- **Programme has no access logic.** It is navigation only.

---

## Key Decisions

- **Lesson = Documento (1:1):** The existing content model is unchanged. Hierarchy is an organizational layer on top, not a new content type.
- **Scope boundary rule:** If content does not require code execution or LLM feedback, it is out of Senda's scope.
- **Quiz = formative self-check only:** Adding grading would replicate LMS functionality Moodle already provides better.
- **Enrollment at Course level:** Programme is navigation; access control lives at Course level. This keeps the access model simple.
- **Analytics deferred:** Building analytics before real usage data exists produces metrics nobody uses. Instrument now, build UI later.
- **LTI-compatible auth design:** Student identity modeled to allow external assertion later without structural rewrite.

---

## Dependencies / Assumptions

- The existing block editor (BlockNote + FastAPI) is the authoring surface for quiz blocks. No new editor framework needed.
- The existing execution engine and LLM feedback service are reused unchanged for quiz block validation and hints.
- Alembic migrations are introduced as part of Phase 4 (R16) before any new schema is added.

---

## Outstanding Questions

### Resolve Before Planning

_(none — all blocking questions resolved)_

### Deferred to Planning

- [Affects R9, R10][Technical] Which auth library/approach for FastAPI (e.g., JWT with python-jose, FastAPI-Users, custom)? Needs to support future LTI subject claim mapping.
- [Affects R12][Needs research] LTI 1.3 subject claim structure — what fields are available to map to a Senda user identity without requiring a Senda account?
- [Affects R17][Technical] Alembic autogenerate setup with async SQLAlchemy — verify compatibility with current `asyncpg` + `DeclarativeBase` setup.
- [Affects R13][Technical] Invite link expiry and reuse policy (single-use vs. multi-use, TTL).
- [Affects R5][Technical] LLM quality review prompt design — direct assessment mode vs. existing Socratic hint mode; likely a separate prompt template.

---

## Next Steps

→ `/ce:plan` for structured implementation planning.
