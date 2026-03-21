CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

DO $$
BEGIN
    CREATE TYPE event_format AS ENUM ('offline', 'online');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE event_status AS ENUM ('published', 'cancelled', 'completed');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE registration_status AS ENUM ('registered', 'cancelled');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email CITEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    university TEXT NULL,
    faculty TEXT NULL,
    telegram TEXT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_users_email_not_blank CHECK (btrim(email::TEXT) <> ''),
    CONSTRAINT chk_users_password_hash_not_blank CHECK (btrim(password_hash) <> ''),
    CONSTRAINT chk_users_full_name_not_blank CHECK (btrim(full_name) <> ''),
    CONSTRAINT chk_users_telegram_format CHECK (
        telegram IS NULL OR telegram ~ '^@?[A-Za-z0-9_]{5,32}$'
    ),
    CONSTRAINT chk_users_deleted_requires_inactive CHECK (
        deleted_at IS NULL OR is_active = FALSE
    )
);

CREATE TABLE IF NOT EXISTS tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    group_code TEXT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_tags_slug_format CHECK (
        slug = lower(slug)
        AND slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'
    ),
    CONSTRAINT chk_tags_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT chk_tags_group_code_not_blank CHECK (
        group_code IS NULL OR btrim(group_code) <> ''
    )
);

CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by_user_id UUID NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    photo_url TEXT NULL,
    contacts TEXT NOT NULL,
    format event_format NOT NULL,
    status event_status NOT NULL DEFAULT 'published',
    price_minor BIGINT NOT NULL DEFAULT 0,
    event_start_at TIMESTAMPTZ NOT NULL,
    registration_start_at TIMESTAMPTZ NOT NULL,
    registration_end_at TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER NOT NULL,
    max_participants INTEGER NULL,
    recurrence_rule TEXT NULL,
    cancelled_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    deleted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_events_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT chk_events_description_not_blank CHECK (btrim(description) <> ''),
    CONSTRAINT chk_events_contacts_not_blank CHECK (btrim(contacts) <> ''),
    CONSTRAINT chk_events_price_non_negative CHECK (price_minor >= 0),
    CONSTRAINT chk_events_duration_positive CHECK (duration_minutes > 0),
    CONSTRAINT chk_events_max_participants_positive CHECK (
        max_participants IS NULL OR max_participants > 0
    ),
    CONSTRAINT chk_events_registration_window CHECK (
        registration_start_at <= registration_end_at
    ),
    CONSTRAINT chk_events_registration_before_start CHECK (
        registration_end_at <= event_start_at
    ),
    CONSTRAINT chk_events_recurrence_not_blank CHECK (
        recurrence_rule IS NULL OR btrim(recurrence_rule) <> ''
    ),
    CONSTRAINT chk_events_status_timestamps CHECK (
        (status = 'published' AND cancelled_at IS NULL AND completed_at IS NULL)
        OR (status = 'cancelled' AND cancelled_at IS NOT NULL AND completed_at IS NULL)
        OR (status = 'completed' AND completed_at IS NOT NULL AND cancelled_at IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS event_tags (
    event_id UUID NOT NULL REFERENCES events(id) ON UPDATE RESTRICT ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, tag_id)
);

CREATE TABLE IF NOT EXISTS event_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON UPDATE RESTRICT ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    status registration_status NOT NULL DEFAULT 'registered',
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cancelled_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_event_registrations_event_user UNIQUE (event_id, user_id),
    CONSTRAINT chk_event_registrations_status_timestamps CHECK (
        (status = 'registered' AND cancelled_at IS NULL)
        OR (status = 'cancelled' AND cancelled_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_users_active
    ON users (id)
    WHERE deleted_at IS NULL AND is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_tags_group_code
    ON tags (group_code, name)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_events_public_feed
    ON events (event_start_at ASC, id ASC)
    WHERE deleted_at IS NULL AND status = 'published';

CREATE INDEX IF NOT EXISTS idx_events_creator
    ON events (created_by_user_id, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_events_status_start
    ON events (status, event_start_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_events_format_public
    ON events (format, event_start_at ASC, id ASC)
    WHERE deleted_at IS NULL AND status = 'published';

CREATE INDEX IF NOT EXISTS idx_event_tags_tag_event
    ON event_tags (tag_id, event_id);

CREATE INDEX IF NOT EXISTS idx_event_registrations_event_active
    ON event_registrations (event_id, created_at ASC)
    WHERE status = 'registered';

CREATE INDEX IF NOT EXISTS idx_event_registrations_user_active
    ON event_registrations (user_id, created_at DESC)
    WHERE status = 'registered';

DROP TRIGGER IF EXISTS trg_users_set_updated_at ON users;
CREATE TRIGGER trg_users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tags_set_updated_at ON tags;
CREATE TRIGGER trg_tags_set_updated_at
BEFORE UPDATE ON tags
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_events_set_updated_at ON events;
CREATE TRIGGER trg_events_set_updated_at
BEFORE UPDATE ON events
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_event_registrations_set_updated_at ON event_registrations;
CREATE TRIGGER trg_event_registrations_set_updated_at
BEFORE UPDATE ON event_registrations
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
