-- FreshChain sample data for all tables
-- Run this in PostgreSQL against the same database used by DATABASE_URL.
-- This is intended for local/demo testing only.

BEGIN;

-- 1) inventory_batches
INSERT INTO inventory_batches (
    batch_id,
    product_name,
    quantity,
    unit,
    location,
    current_price,
    original_price,
    estimated_remaining_shelf_life_hours,
    demand_velocity_units_per_hour,
    status,
    created_at
) VALUES
    (
        'STB-042',
        'Strawberries',
        184,
        'units',
        'Main Store',
        180.0,
        180.0,
        31.0,
        4.2,
        'HEALTHY',
        NOW()
    ),
    (
        'STB-043',
        'Blueberries',
        92,
        'units',
        'Cold Room A',
        220.0,
        220.0,
        18.5,
        3.8,
        'RISK',
        NOW()
    ),
    (
        'STB-044',
        'Avocados',
        140,
        'units',
        'Fresh Cut Zone',
        150.0,
        150.0,
        42.0,
        5.1,
        'HEALTHY',
        NOW()
    ),
    (
        'STB-045',
        'Mangoes',
        210,
        'units',
        'Back Room',
        95.0,
        95.0,
        12.0,
        6.4,
        'CRITICAL',
        NOW()
    );

-- 2) sensor_readings
INSERT INTO sensor_readings (
    reading_id,
    batch_id,
    temperature_c,
    humidity_percent,
    ethylene_ppm,
    recorded_at,
    anomaly_flags
) VALUES
    (
        'sr-1001',
        'STB-042',
        4.2,
        65.0,
        0.6,
        NOW(),
        '[]'::json
    ),
    (
        'sr-1002',
        'STB-043',
        8.5,
        74.0,
        1.9,
        NOW(),
        '["HIGH_TEMPERATURE","HIGH_ETHYLENE"]'::json
    ),
    (
        'sr-1003',
        'STB-044',
        5.1,
        66.0,
        0.8,
        NOW(),
        '[]'::json
    ),
    (
        'sr-1004',
        'STB-045',
        10.2,
        81.0,
        2.5,
        NOW(),
        '["HIGH_TEMPERATURE","HIGH_HUMIDITY","HIGH_ETHYLENE"]'::json
    );

-- 3) store_profiles
INSERT INTO store_profiles (
    store_id,
    name,
    city,
    area,
    manager,
    created_at
) VALUES
    (
        'store-042',
        'Store #042',
        'Bengaluru',
        'Brookefield',
        'Store Manager',
        NOW()
    );

-- 4) network_nodes
INSERT INTO network_nodes (
    node_id,
    node_type,
    demand,
    risk,
    capacity,
    distance_km,
    destination_id
) VALUES
    (
        'store-042',
        'store',
        4.2,
        38,
        0.0,
        0.0,
        'hub-02'
    ),
    (
        'hub-02',
        'hub',
        0.0,
        0,
        320.0,
        2.4,
        NULL
    ),
    (
        'hub-07',
        'hub',
        0.0,
        0,
        480.0,
        8.6,
        NULL
    );

-- 5) decisions
INSERT INTO decisions (
    decision_id,
    batch_id,
    quality_assessment,
    pricing_assessment,
    logistics_assessment,
    selected_actions,
    evidence_summary,
    status,
    created_at
) VALUES
    (
        'dec-2001',
        'STB-043',
        '{"score": 62, "summary": "Temperature spike and ethylene elevated"}',
        '{"recommended_markdown_percent": 18.0, "price_action": "markdown"}',
        '{"route": "hub-02", "priority": "high"}',
        '["MARKDOWN", "REDISTRIBUTE"]',
        '["High temp detected", "Ethylene elevated", "Shelf life dropping"]',
        'PENDING',
        NOW()
    ),
    (
        'dec-2002',
        'STB-045',
        '{"score": 41, "summary": "Severe spoilage risk"}',
        '{"recommended_markdown_percent": 32.0, "price_action": "aggressive_markdown"}',
        '{"route": "hub-07", "priority": "critical"}',
        '["B2B_OFFLOAD", "MARKDOWN"]',
        '["Critical spoilage risk", "Customer demand weak", "Transfer recommended"]',
        'APPROVED',
        NOW()
    );

-- 6) agent_assessments
INSERT INTO agent_assessments (
    assessment_id,
    decision_id,
    batch_id,
    agent_name,
    result
) VALUES
    (
        'ass-3001',
        'dec-2001',
        'STB-043',
        'quality',
        '{"risk_level": "high", "score": 62}'::json
    ),
    (
        'ass-3002',
        'dec-2001',
        'STB-043',
        'pricing',
        '{"markdown_percent": 18.0, "recommended_price": 180.0}'::json
    ),
    (
        'ass-3003',
        'dec-2001',
        'STB-043',
        'logistics',
        '{"route": "hub-02", "eta_minutes": 18}'::json
    ),
    (
        'ass-3004',
        'dec-2002',
        'STB-045',
        'quality',
        '{"risk_level": "critical", "score": 41}'::json
    );

-- 7) actions
INSERT INTO actions (
    action_id,
    decision_id,
    batch_id,
    action_type,
    quantity,
    status,
    details,
    created_at
) VALUES
    (
        'act-4001',
        'dec-2001',
        'STB-043',
        'REDISTRIBUTE',
        42,
        'PENDING',
        '{"destination": "hub-02", "eta_minutes": 18}',
        NOW()
    ),
    (
        'act-4002',
        'dec-2001',
        'STB-043',
        'MARKDOWN',
        30,
        'PENDING',
        '{"markdown_percent": 18.0}',
        NOW()
    ),
    (
        'act-4003',
        'dec-2002',
        'STB-045',
        'B2B_OFFLOAD',
        70,
        'IN_PROGRESS',
        '{"destination": "secondary_buyer_network"}',
        NOW()
    );

-- 8) execution_records
INSERT INTO execution_records (
    execution_id,
    decision_id,
    batch_id,
    status,
    steps,
    transfer_destination,
    transfer_eta_min,
    created_at
) VALUES
    (
        'exec-5001',
        'dec-2001',
        'STB-043',
        'in_progress',
        '{"Create markdown": "done", "Transfer to hub": "in_progress", "Notify B2B buyer": "pending"}',
        'hub-02',
        18,
        NOW()
    ),
    (
        'exec-5002',
        'dec-2002',
        'STB-045',
        'queued',
        '{"Create markdown": "done", "Route offload": "queued", "Confirm buyer": "pending"}',
        'hub-07',
        32,
        NOW()
    );

COMMIT;
