-- Track weekly match count used in /ego and profile displays.

ALTER TABLE player_cache
    ADD COLUMN matches_played SMALLINT UNSIGNED NOT NULL DEFAULT 0 AFTER contrib_kast;
