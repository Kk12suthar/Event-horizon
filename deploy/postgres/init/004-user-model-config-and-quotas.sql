BEGIN;

ALTER TABLE instance01.agent_model_config
    ADD COLUMN IF NOT EXISTS user_id character varying(128);

-- Production model access is user-owned. Remove the legacy shared runtime row
-- so no deployment/provider key can be selected by future request code.
DELETE FROM instance01.agent_model_config WHERE user_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS agent_model_config_user_id_uq
    ON instance01.agent_model_config (user_id)
    WHERE user_id IS NOT NULL;

ALTER TABLE instance01.mtd_file
    ADD COLUMN IF NOT EXISTS size_bytes bigint NOT NULL DEFAULT 0;

ALTER TABLE instance01.mtd_file
    DROP CONSTRAINT IF EXISTS mtd_file_size_bytes_nonnegative;

ALTER TABLE instance01.mtd_file
    ADD CONSTRAINT mtd_file_size_bytes_nonnegative CHECK (size_bytes >= 0);

CREATE INDEX IF NOT EXISTS mtd_file_uploader_quota_idx
    ON instance01.mtd_file (uploaded_by, status)
    INCLUDE (size_bytes);

CREATE TABLE IF NOT EXISTS instance01.mtd_external_identity (
    provider character varying(32) NOT NULL,
    subject character varying(255) NOT NULL,
    user_id character varying(128) NOT NULL,
    email character varying(320) NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT NOW(),
    last_login_at timestamp with time zone NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider, subject),
    CONSTRAINT mtd_external_identity_user_fk
        FOREIGN KEY (user_id) REFERENCES instance01.mtd_users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS mtd_external_identity_user_idx
    ON instance01.mtd_external_identity (user_id);

COMMIT;
