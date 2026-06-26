-- Initial schema for Ego Score Bot
-- All DATETIME fields stored and interpreted in MSK (Europe/Moscow)

CREATE TABLE users (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    discord_id    BIGINT UNSIGNED NOT NULL UNIQUE,
    riot_id       VARCHAR(100)    NOT NULL,
    registered_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'МСК',
    updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE player_cache (
    id             BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id        BIGINT          NOT NULL,
    week_start     DATE            NOT NULL,
    acs            FLOAT,
    kd_ratio       FLOAT,
    damage_delta   FLOAT,
    hs_percent     FLOAT,
    kast_percent   FLOAT,
    ego_score      FLOAT,
    current_rank   VARCHAR(50),
    rank_delta     TINYINT DEFAULT 0,
    contrib_acs    FLOAT,
    contrib_kd     FLOAT,
    contrib_dd     FLOAT,
    contrib_hs     FLOAT,
    contrib_kast   FLOAT,
    fetched_at     DATETIME        NOT NULL COMMENT 'МСК',
    is_stale       BOOLEAN         NOT NULL DEFAULT FALSE,
    UNIQUE KEY uk_user_week (user_id, week_start),
    INDEX idx_ego_score (week_start, ego_score DESC),
    INDEX idx_fetched_at (fetched_at),
    CONSTRAINT fk_cache_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE weekly_snapshots (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    week_start    DATE            NOT NULL,
    week_end      DATE            NOT NULL,
    `rank`        SMALLINT        NOT NULL,
    user_id       BIGINT          NOT NULL,
    riot_id       VARCHAR(100)    NOT NULL,
    current_rank  VARCHAR(50),
    ego_score     FLOAT           NOT NULL,
    acs           FLOAT,
    kd_ratio      FLOAT,
    damage_delta  FLOAT,
    hs_percent    FLOAT,
    kast_percent  FLOAT,
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'МСК',
    UNIQUE KEY uk_week_rank (week_start, `rank`),
    INDEX idx_week_start (week_start),
    INDEX idx_user_id (user_id),
    CONSTRAINT fk_snapshots_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE stat_bounds (
    stat_name  VARCHAR(50) PRIMARY KEY,
    min_val    FLOAT       NOT NULL,
    max_val    FLOAT       NOT NULL,
    updated_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'МСК'
);

CREATE TABLE bot_config (
    key_name   VARCHAR(100) PRIMARY KEY,
    key_value  VARCHAR(500) NOT NULL,
    updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
