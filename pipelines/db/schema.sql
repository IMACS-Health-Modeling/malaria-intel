-- ═══════════════════════════════════════════════════════════════════════════
-- Malaria Intel — PostgreSQL Schema v2
-- Multi-disease, global coverage, 1990-present
-- ═══════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS malaria;
SET search_path TO malaria, public;

-- ── Dimensions ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dim_country (
    iso3            CHAR(3)  PRIMARY KEY,
    iso2            CHAR(2),
    name            TEXT     NOT NULL,
    region          TEXT,                  -- WHO region: AFR, AMR, EMR, EUR, SEARO, WPR
    sub_region      TEXT,
    lat             FLOAT,
    lng             FLOAT,
    is_endemic      BOOLEAN  DEFAULT FALSE,
    is_pmi          BOOLEAN  DEFAULT FALSE,
    population      BIGINT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_disease (
    code            TEXT     PRIMARY KEY,  -- malaria, dengue, ebola, cholera, mpox, etc.
    name            TEXT     NOT NULL,
    category        TEXT,                  -- vector-borne, hemorrhagic, respiratory, bacterial, parasitic
    icd10_code      TEXT,
    plasmodium_spp  TEXT,                  -- pf, pv, pm, po (malaria only)
    who_don_keywords TEXT[]
);

CREATE TABLE IF NOT EXISTS dim_source (
    code            TEXT     PRIMARY KEY,
    name            TEXT     NOT NULL,
    url             TEXT,
    data_type       TEXT,                  -- api, scrape, download, foundation_bucket
    refresh_cadence TEXT,
    last_fetched    TIMESTAMPTZ
);

-- ── Burden (estimated + reported cases/deaths) ───────────────────────────

CREATE TABLE IF NOT EXISTS fact_burden (
    id              BIGSERIAL PRIMARY KEY,
    iso3            CHAR(3)  REFERENCES dim_country(iso3) ON DELETE RESTRICT,
    disease_code    TEXT     REFERENCES dim_disease(code)  ON DELETE RESTRICT,
    year            SMALLINT NOT NULL,
    source_code     TEXT     REFERENCES dim_source(code),
    metric          TEXT     NOT NULL,
    -- cases_estimated, deaths_estimated, incidence_per_1000, mortality_per_100k,
    -- daly, yld, yll, cases_reported, cases_confirmed, deaths_reported
    value           FLOAT,
    value_low       FLOAT,
    value_high      FLOAT,
    age_group       TEXT     DEFAULT 'all',
    sex             TEXT     DEFAULT 'both',
    is_modeled      BOOLEAN  DEFAULT TRUE,
    raw_s3_key      TEXT,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (iso3, disease_code, year, source_code, metric, age_group, sex)
);

CREATE INDEX IF NOT EXISTS idx_burden_country_year   ON fact_burden (iso3, year);
CREATE INDEX IF NOT EXISTS idx_burden_disease_year   ON fact_burden (disease_code, year);
CREATE INDEX IF NOT EXISTS idx_burden_metric         ON fact_burden (metric);
CREATE INDEX IF NOT EXISTS idx_burden_source         ON fact_burden (source_code);

-- ── Interventions (coverage, commodities, programs) ──────────────────────

CREATE TABLE IF NOT EXISTS fact_intervention (
    id              BIGSERIAL PRIMARY KEY,
    iso3            CHAR(3)  REFERENCES dim_country(iso3),
    year            SMALLINT NOT NULL,
    source_code     TEXT     REFERENCES dim_source(code),
    indicator       TEXT     NOT NULL,
    -- itn_use_pct, irs_coverage_pct, act_coverage_pct, rdt_positivity_pct,
    -- iptp3_coverage_pct, llin_distributed, indoor_rsp_spraying_pct
    value           FLOAT,
    unit            TEXT,                  -- pct, count, per_1000
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (iso3, year, source_code, indicator)
);

CREATE INDEX IF NOT EXISTS idx_intervention_iso3   ON fact_intervention (iso3, year);
CREATE INDEX IF NOT EXISTS idx_intervention_ind    ON fact_intervention (indicator);

-- ── Outbreak events (WHO DON, ProMED, ECDC alerts) ───────────────────────

CREATE TABLE IF NOT EXISTS fact_outbreak (
    id                      BIGSERIAL PRIMARY KEY,
    event_id                TEXT     UNIQUE NOT NULL,
    source                  TEXT     NOT NULL,  -- who_don, promedmail, reliefweb
    disease                 TEXT,
    disease_normalized      TEXT     REFERENCES dim_disease(code),
    event_type              TEXT,               -- arbovirus, hemorrhagic, bacterial, respiratory, parasitic, conflict
    country_iso3            CHAR(3),
    admin1                  TEXT,
    lat                     FLOAT,
    lng                     FLOAT,
    start_date              DATE,
    end_date                DATE,
    status                  TEXT,               -- ongoing, closed, under_investigation
    cases_reported          INTEGER,
    deaths_reported         INTEGER,
    severity_score          FLOAT,              -- 0-1
    overlap_with_malaria_zone FLOAT,            -- 0-1
    dci_score               FLOAT,              -- 0-1 Diagnostic Confusion Index
    narrative               TEXT,
    source_url              TEXT,
    raw_s3_key              TEXT,
    extracted_by            TEXT,               -- bedrock-haiku-4-5, manual, structured
    ingested_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbreak_country  ON fact_outbreak (country_iso3);
CREATE INDEX IF NOT EXISTS idx_outbreak_disease  ON fact_outbreak (disease_normalized);
CREATE INDEX IF NOT EXISTS idx_outbreak_date     ON fact_outbreak (start_date);
CREATE INDEX IF NOT EXISTS idx_outbreak_dci      ON fact_outbreak (dci_score) WHERE dci_score IS NOT NULL;

-- ── Funding flows ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fact_funding (
    id              BIGSERIAL PRIMARY KEY,
    iso3            CHAR(3)  REFERENCES dim_country(iso3),
    year            SMALLINT,
    source_code     TEXT     REFERENCES dim_source(code),
    channel         TEXT,                  -- pmi, global_fund, nih, pepfar, bilateral_oda, world_bank
    disease         TEXT,
    amount_usd      FLOAT,
    amount_type     TEXT,                  -- approved, disbursed, committed, allocated, spent
    currency_orig   TEXT     DEFAULT 'USD',
    program         TEXT,
    grant_id        TEXT,
    implementing_partner TEXT,
    ingested_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_funding_iso3    ON fact_funding (iso3, year);
CREATE INDEX IF NOT EXISTS idx_funding_channel ON fact_funding (channel, disease);

-- ── Drug resistance ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fact_drug_resistance (
    id              BIGSERIAL PRIMARY KEY,
    iso3            CHAR(3)  REFERENCES dim_country(iso3),
    disease_code    TEXT     DEFAULT 'malaria',
    year            SMALLINT,
    drug            TEXT,                  -- artemisinin, chloroquine, sp, lumefantrine, piperaquine
    resistance_marker TEXT,               -- kelch13, pfcrt, pfdhfr, pfmdr1
    mutation        TEXT,                  -- C580Y, F446I, R539T, etc.
    prevalence_pct  FLOAT,
    sample_size     INTEGER,
    data_source     TEXT,
    severity        TEXT,                  -- low, partial, full
    lat             FLOAT,
    lng             FLOAT,
    raw_s3_key      TEXT,
    ingested_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dr_iso3  ON fact_drug_resistance (iso3);
CREATE INDEX IF NOT EXISTS idx_dr_drug  ON fact_drug_resistance (drug, mutation);

-- ── Parasite rates (Malaria Atlas Project) ───────────────────────────────

CREATE TABLE IF NOT EXISTS fact_parasite_rate (
    id              BIGSERIAL PRIMARY KEY,
    iso3            CHAR(3)  REFERENCES dim_country(iso3),
    species         TEXT     NOT NULL,     -- pf, pv
    year            SMALLINT,
    survey_type     TEXT,                  -- community, health_facility, rdt, pcr, microscopy
    pr_mean         FLOAT,                 -- parasite rate 0-1
    pr_lower        FLOAT,
    pr_upper        FLOAT,
    sample_size     INTEGER,
    lat             FLOAT,
    lng             FLOAT,
    admin1          TEXT,
    raw_s3_key      TEXT,
    ingested_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_iso3    ON fact_parasite_rate (iso3);
CREATE INDEX IF NOT EXISTS idx_pr_species ON fact_parasite_rate (species, year);

-- ── Climate (NASA POWER monthly) ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fact_climate (
    id              BIGSERIAL PRIMARY KEY,
    iso3            CHAR(3)  REFERENCES dim_country(iso3),
    year            SMALLINT NOT NULL,
    month           SMALLINT NOT NULL,     -- 1-12
    temp_avg_c      FLOAT,
    temp_max_c      FLOAT,
    temp_min_c      FLOAT,
    rainfall_mm     FLOAT,
    humidity_pct    FLOAT,
    evi             FLOAT,
    source          TEXT     DEFAULT 'nasa_power',
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (iso3, year, month, source)
);

CREATE INDEX IF NOT EXISTS idx_climate_iso3 ON fact_climate (iso3, year);

-- ── Partners / Ecosystem ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dim_partner (
    id              SERIAL PRIMARY KEY,
    name            TEXT     NOT NULL,
    entity_type     TEXT,                  -- academia, cro, ngo, pharma, government, service_provider
    entity_type_raw TEXT,                  -- original label from source
    city            TEXT,
    state_code      CHAR(2),               -- US 2-letter abbreviation
    country_iso3    CHAR(3)  DEFAULT 'USA',
    notes           TEXT,                  -- role / contribution description
    active_year     SMALLINT,              -- reporting year (2026 = 2025-26 cycle)
    data_source     TEXT     DEFAULT 'mmv_us_partners',
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (name, active_year)
);

CREATE INDEX IF NOT EXISTS idx_partner_type ON dim_partner (entity_type);
CREATE INDEX IF NOT EXISTS idx_partner_year ON dim_partner (active_year);

-- ── Pipeline run log ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              BIGSERIAL PRIMARY KEY,
    pipeline_name   TEXT     NOT NULL,
    stage           TEXT     NOT NULL,     -- l0_ingest, l1_transform, l2_serve
    status          TEXT     NOT NULL,     -- running, success, failed
    records_processed INTEGER,
    errors          TEXT,
    s3_keys         TEXT[],
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ
);

-- ── Reference data ────────────────────────────────────────────────────────

INSERT INTO dim_disease (code, name, category, icd10_code, plasmodium_spp, who_don_keywords)
VALUES
    ('malaria',         'Malaria',                    'vector-borne',  'B50-B54', 'pf,pv,pm,po', ARRAY['malaria','plasmodium','falciparum','vivax']),
    ('dengue',          'Dengue',                     'vector-borne',  'A97',     NULL,          ARRAY['dengue','DENV','dengue fever']),
    ('ebola',           'Ebola Virus Disease',        'hemorrhagic',   'A98.4',   NULL,          ARRAY['ebola','EVD','Ebola virus']),
    ('marburg',         'Marburg Virus Disease',      'hemorrhagic',   'A98.3',   NULL,          ARRAY['marburg','MVD']),
    ('cholera',         'Cholera',                    'bacterial',     'A00',     NULL,          ARRAY['cholera','Vibrio cholerae']),
    ('mpox',            'Mpox (Monkeypox)',           'viral',         'B04',     NULL,          ARRAY['mpox','monkeypox','MPXV']),
    ('mers',            'MERS-CoV',                   'respiratory',   'B34.2',   NULL,          ARRAY['MERS','Middle East respiratory','coronavirus']),
    ('yellow_fever',    'Yellow Fever',               'vector-borne',  'A95',     NULL,          ARRAY['yellow fever']),
    ('zika',            'Zika Virus',                 'vector-borne',  'A92.5',   NULL,          ARRAY['Zika','ZIKV']),
    ('chikungunya',     'Chikungunya',                'vector-borne',  'A92.0',   NULL,          ARRAY['chikungunya','CHIKV']),
    ('rift_valley',     'Rift Valley Fever',          'vector-borne',  'A92.4',   NULL,          ARRAY['Rift Valley fever','RVF']),
    ('lassa',           'Lassa Fever',                'hemorrhagic',   'A96.2',   NULL,          ARRAY['Lassa','Lassa fever']),
    ('plague',          'Plague',                     'bacterial',     'A20',     NULL,          ARRAY['plague','Yersinia pestis']),
    ('meningitis',      'Meningitis (bacterial)',     'bacterial',     'A39',     NULL,          ARRAY['meningitis','meningococcal']),
    ('influenza_novel', 'Novel Influenza',            'respiratory',   'J09',     NULL,          ARRAY['influenza A','novel influenza','H5N1','H7N9','avian influenza'])
ON CONFLICT (code) DO NOTHING;

INSERT INTO dim_source (code, name, url, data_type, refresh_cadence)
VALUES
    ('who_gho',        'WHO Global Health Observatory OData API',      'https://ghoapi.azureedge.net/api',                         'api',              'monthly'),
    ('wmr_2025',       'WHO World Malaria Report 2025 Annexes',        'https://www.who.int/publications/m/item/annexes-world-malaria-report-2025', 'download', 'annual'),
    ('wmr_2024',       'WHO World Malaria Report 2024 Annexes',        'https://www.who.int/publications/m/item/annexes-world-malaria-report-2024', 'download', 'annual'),
    ('wmr_2023',       'WHO World Malaria Report 2023 Annexes',        'https://www.who.int/teams/global-malaria-programme/reports/world-malaria-report-2023', 'download', 'annual'),
    ('wmr_2022',       'WHO World Malaria Report 2022 Annexes',        'https://www.who.int/teams/global-malaria-programme/reports/world-malaria-report-2022', 'download', 'annual'),
    ('who_don',        'WHO Disease Outbreak News',                    'https://www.who.int/emergencies/disease-outbreak-news',     'scrape',           'daily'),
    ('global_fund_v4', 'Global Fund Data Service API v4',             'https://data-service.theglobalfund.org/api',                'api',              'monthly'),
    ('paho_plisa',     'PAHO PLISA Health Indicators Database',        'https://www3.paho.org/data/index.php/en/',                  'api',              'monthly'),
    ('cdc_mmwr',       'CDC MMWR Malaria Surveillance - United States','https://www.cdc.gov/malaria/php/surveillance-report/',      'scrape',           'annual'),
    ('ihme_gbd',       'IHME Global Burden of Disease 2023',          'https://ghdx.healthdata.org/gbd-2023',                     'foundation_bucket','annual'),
    ('map_project',    'Malaria Atlas Project',                        'https://malariaatlas.org',                                  'foundation_bucket','annual'),
    ('nasa_power',     'NASA POWER Climate Data',                      'https://power.larc.nasa.gov',                               'foundation_bucket','monthly'),
    ('nih_reporter',   'NIH RePORTER API v2',                         'https://api.reporter.nih.gov',                              'api',              'weekly'),
    ('usaspending',    'USAspending.gov API v2',                      'https://api.usaspending.gov',                               'api',              'monthly'),
    ('promedmail',     'ProMED Mail RSS',                              'https://www.promedmail.org',                                'rss',              'daily')
ON CONFLICT (code) DO NOTHING;
