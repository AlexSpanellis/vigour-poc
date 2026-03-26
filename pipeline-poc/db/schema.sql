-- Vigour POC Database Schema
-- PostgreSQL

CREATE TABLE IF NOT EXISTS sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_name TEXT,
    session_date DATE NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clips (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID REFERENCES sessions(id),
    job_id      UUID UNIQUE NOT NULL,
    test_type   TEXT NOT NULL,
    video_path  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued',  -- queued, processing, complete, failed
    created_at  TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS results (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id          UUID REFERENCES clips(id),
    student_bib      INT,
    track_id         INT,
    test_type        TEXT NOT NULL,
    metric_value     NUMERIC(10, 3),
    metric_unit      TEXT,
    attempt_number   INT,
    confidence_score NUMERIC(4, 3),
    flags            TEXT[],
    raw_data         JSONB,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_results_student_bib ON results(student_bib);
CREATE INDEX IF NOT EXISTS idx_results_test_type ON results(test_type);
CREATE INDEX IF NOT EXISTS idx_clips_job_id ON clips(job_id);
