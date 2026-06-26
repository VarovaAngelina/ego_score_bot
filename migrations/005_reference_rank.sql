-- Position at previous cache refresh (baseline for rank_delta arrows in /top)
ALTER TABLE player_cache
    ADD COLUMN reference_rank TINYINT NULL AFTER rank_delta;
