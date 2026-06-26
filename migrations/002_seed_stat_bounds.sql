-- Seed fallback normalization bounds

INSERT INTO stat_bounds (stat_name, min_val, max_val) VALUES
    ('acs', 50, 350),
    ('kd', 0.3, 3.0),
    ('dd', -80, 120),
    ('hs', 10, 45),
    ('kast', 30, 90)
ON DUPLICATE KEY UPDATE
    min_val = VALUES(min_val),
    max_val = VALUES(max_val);
