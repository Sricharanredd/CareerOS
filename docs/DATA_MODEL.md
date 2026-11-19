# Data model

Physical schema after `alembic upgrade head`. All tables are InnoDB, `utf8mb4_0900_ai_ci`,
timestamps `DATETIME(6)` in UTC, primary keys `CHAR(36)` UUID.

## Auth

**owner** — `id`, `email` (unique), `password_hash`, `full_name`, `timezone`,
`currency`, `theme`, `last_login_at`, `created_at`, `updated_at`.
Exactly one row, created by the bootstrap CLI.

**session** — `id`, `owner_id → owner`, `refresh_hash` (unique), `family_id`, `user_agent`,
`ip`, `expires_at`, `revoked_at`, `replaced_by`, `last_used_at`, `created_at`.
Rotation writes a new row and marks the old one `revoked_at`/`replaced_by`.

## CRM core

**company** — `id`, `owner_id`, `name`, `website`, `industry`, `location`, `notes`,
`archived_at`, `created_at`, `updated_at`. `UNIQUE (owner_id, name)` under a
case-insensitive collation.

**job_description** — `id`, `owner_id`, `company_id → company`, `title`, `location`, `url`,
`raw_text` (LONGTEXT), `structured_json` (JSON), `seniority`, `employment_type`,
`required_skills` (JSON), `preferred_skills` (JSON), `responsibilities` (JSON),
`source_file_id → file_object`, `archived_at`, timestamps.
Index: `(owner_id, created_at)`, `(company_id)`.

**file_object** — `id`, `owner_id`, `storage_key` (unique), `original_name`, `mime`,
`size_bytes`, `sha256`, `kind`, `created_at`.

**resume** — `id`, `owner_id`, `name`, `headline`, `current_version_id → resume_version`
(deferred FK), `archived_at`, timestamps. `UNIQUE (owner_id, name)`.

**resume_version** — `id`, `resume_id → resume`, `file_id → file_object`, `version_no`,
`label`, `extracted_text` (LONGTEXT), `notes`, `created_at`.
`UNIQUE (resume_id, version_no)`. Immutable once written.

**application** — `id`, `owner_id`, `company_id`, `jd_id → job_description` (nullable),
`resume_version_id` (nullable), `title`, `location`, `employment_type`, `work_mode`,
`job_url`, `status`, `applied_on`, `salary_min`, `salary_max`, `salary_currency`,
`salary_period`, `source`, `notes`, `follow_up_on`, `rejection_reason`, `offer_amount`,
`offer_deadline`, `archived_at`, timestamps.
Indexes: `(owner_id, status)`, `(owner_id, applied_on)`, `(company_id)`, `(jd_id)`.

**application_event** — `id`, `application_id`, `type`, `from_status`, `to_status`,
`payload` (JSON), `created_at`. Append-only timeline.

## Scheduling

**interview** — `id`, `application_id`, `round_no`, `type`, `scheduled_at`, `timezone`,
`interviewer`, `location`, `link`, `prep_notes`, `outcome`, `feedback`, timestamps.

**follow_up** — `id`, `application_id`, `due_on`, `channel`, `status`, `done_at`, `notes`,
timestamps. Index `(status, due_on)`.

**task** — `id`, `owner_id`, `application_id` (nullable), `title`, `description`,
`priority`, `status`, `due_on`, `completed_at`, timestamps. Constraint:
`status <> 'done' OR completed_at IS NOT NULL`.

**time_entry** — `id`, `owner_id`, `task_id` (nullable), `started_at`, `ended_at`, `notes`.
Constraint: `ended_at > started_at`.

## Analysis

**analysis_job** — `id`, `owner_id`, `resume_version_id`, `jd_id` (nullable),
`jd_text_hash`, `status`, `input_hash`, `provider`, `model`, `prompt_version`, `attempts`,
`error_code`, `error_message`, `started_at`, `finished_at`, timestamps.
`UNIQUE (input_hash)` for idempotent submission.

**analysis_result** — `id`, `job_id` (unique), `score`, `summary`,
`alignment_explanation`, `findings_json` (JSON), `schema_version`, `created_at`.
Every finding carries `evidence_type` ∈ {`resume_evidence`, `jd_requirement`,
`inferred_recommendation`}.

## Audit

**audit_log** — `id`, `owner_id`, `action`, `entity`, `entity_id`, `created_at`.
No payload column: sensitive content never reaches the audit trail.

## Status workflow

```
saved ──► applied ──► screening ──► interviewing ──► offer ──► accepted
  │           │            │              │            │
  └───────────┴────────────┴──────────────┴────────────┴──► withdrawn
              └────────────┴──────────────┴────────────┴──► rejected / ghosted
```

`accepted`, `rejected`, `withdrawn`, `ghosted` are terminal. Invalid transitions are
rejected with `409 invalid_transition`.
