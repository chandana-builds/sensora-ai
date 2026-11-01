# Database schema

Source of truth: `supabase/migrations/001_initial_schema.sql` and `supabase/migrations/003_m4_store.sql`.

| Table | Key columns |
|---|---|
| `profiles` | `id` (user id or anonymous client UUID), `display_name`, `is_anonymous`, `created_at` |
| `user_preferences` | `user_id` PK→profiles, `experience_level`, `speak_responses`, `speech_rate`, `larger_text`, `high_contrast`, `reduce_motion`, `save_transcripts`, `updated_at` |
| `troubleshooting_sessions` | `id`, `user_id`→profiles, `title`, `device_name`, `problem_description`, `experience_level`, `status` (active/resolved/unresolved/escalated/abandoned), `started_at`, `ended_at`, `updated_at` |
| `conversation_messages` | `id`, `session_id`→sessions, `role`, `content`, `input_mode`, `safety_level`, `created_at` |
| `troubleshooting_steps` | `id`, `session_id`, `step_number` (unique per session), `instruction`, `status`, `verification` (not_verified/user_confirmed/visually_verified), `outcome_note`, timestamps |
| `session_summaries` | `session_id` PK, `summary`, `unresolved_issues` jsonb, `generated_by` (user/system/ai), timestamps |

Deleting a session cascades to its messages, steps and summary. RLS is enabled with no policies and
anon/authenticated privileges are revoked: only the backend (service-role key) can touch the data.

For connecting Supabase Auth and database tables, see [SUPABASE_SETUP.md](SUPABASE_SETUP.md).
