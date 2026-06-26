-- Stronger user registration persistence

ALTER TABLE users
    ADD UNIQUE KEY uk_riot_id (riot_id);

ALTER TABLE player_cache
    DROP FOREIGN KEY fk_cache_user;

ALTER TABLE player_cache
    ADD CONSTRAINT fk_cache_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE weekly_snapshots
    DROP FOREIGN KEY fk_snapshots_user;

ALTER TABLE weekly_snapshots
    ADD CONSTRAINT fk_snapshots_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
