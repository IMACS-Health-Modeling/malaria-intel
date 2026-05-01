-- ═══════════════════════════════════════════════════════════════════════════
-- Malaria Intel — Schema migration v3
-- Adds: fact_insecticide_resistance, fact_vaccine_coverage
-- Adds: new dim_source entries for MalariaGEN, IR Mapper, WHO WIISE
-- ═══════════════════════════════════════════════════════════════════════════

SET search_path TO malaria, public;

-- ── Insecticide resistance (IR Mapper / IVCC) ─────────────────────────────

CREATE TABLE IF NOT EXISTS fact_insecticide_resistance (
    id                  BIGSERIAL PRIMARY KEY,
    iso3                CHAR(3)  REFERENCES dim_country(iso3) ON DELETE RESTRICT,
    year                SMALLINT NOT NULL,
    source_code         TEXT     REFERENCES dim_source(code),
    vector_species      TEXT     NOT NULL,  -- an_gambiae, an_arabiensis, an_funestus, an_stephensi
    insecticide_class   TEXT     NOT NULL,  -- pyrethroid, organochloride, carbamate, organophosphate
    insecticide         TEXT     NOT NULL,  -- permethrin, deltamethrin, ddt, bendiocarb, etc.
    test_method         TEXT,               -- who_tube, cdc_bottle, biochemical
    mortality_pct       FLOAT,              -- 0-100; <98% = suspected resistance
    resistance_status   TEXT,               -- susceptible, possible_resistance, confirmed_resistance
    sample_size         INTEGER,
    site_name           TEXT,
    lat                 FLOAT,
    lng                 FLOAT,
    admin1              TEXT,
    data_source         TEXT,               -- irmapper, who_gardiaa, manual
    publication_ref     TEXT,
    raw_s3_key          TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ir_iso3         ON fact_insecticide_resistance (iso3, year);
CREATE INDEX IF NOT EXISTS idx_ir_species      ON fact_insecticide_resistance (vector_species);
CREATE INDEX IF NOT EXISTS idx_ir_insecticide  ON fact_insecticide_resistance (insecticide_class, insecticide);
CREATE INDEX IF NOT EXISTS idx_ir_status       ON fact_insecticide_resistance (resistance_status);

-- ── Vaccine coverage + pipeline (WHO WIISE / WHO EPI) ────────────────────

CREATE TABLE IF NOT EXISTS fact_vaccine_coverage (
    id                  BIGSERIAL PRIMARY KEY,
    iso3                CHAR(3)  REFERENCES dim_country(iso3) ON DELETE RESTRICT,
    year                SMALLINT NOT NULL,
    source_code         TEXT     REFERENCES dim_source(code),
    vaccine_code        TEXT     NOT NULL,  -- rtss, r21, malaria_general
    -- coverage metrics
    coverage_pct        FLOAT,              -- 0-100; official WHO-UNICEF estimate
    doses_admin         BIGINT,             -- absolute doses administered
    target_population   BIGINT,             -- surviving infants or target cohort
    doses_per_schedule  SMALLINT,           -- 3-dose, 4-dose
    schedule_description TEXT,              -- "3 doses + booster at 15-18m"
    -- rollout status (vaccine pipeline layer)
    rollout_phase       TEXT,               -- approved, piloting, scaled_up, not_introduced
    intro_year          SMALLINT,           -- year vaccine first introduced
    pilot_country       BOOLEAN DEFAULT FALSE,
    -- supply / product info
    manufacturer        TEXT,               -- gsk, serum_institute
    product_name        TEXT,               -- Mosquirix, R21/Matrix-M
    raw_s3_key          TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (iso3, year, source_code, vaccine_code)
);

CREATE INDEX IF NOT EXISTS idx_vax_iso3    ON fact_vaccine_coverage (iso3, year);
CREATE INDEX IF NOT EXISTS idx_vax_code    ON fact_vaccine_coverage (vaccine_code);
CREATE INDEX IF NOT EXISTS idx_vax_phase   ON fact_vaccine_coverage (rollout_phase);

-- ── New dim_source entries ────────────────────────────────────────────────

INSERT INTO dim_source (code, name, url, data_type, refresh_cadence)
VALUES
    ('malariagen_pf8',       'MalariaGEN Pf8 Genomic Surveillance Release',
     'https://pf8-release.cog.sanger.ac.uk',              'download', 'on_release'),
    ('irmapper',             'IR Mapper Insecticide Resistance Database (IVCC)',
     'https://www.irmapper.com',                           'api',      'quarterly'),
    ('who_wiise',            'WHO WIISE Immunization Coverage Estimates',
     'https://immunizationdata.who.int',                   'api',      'annual'),
    ('who_vaccine_pipeline', 'WHO Global Vaccine Pipeline & Landscape',
     'https://www.who.int/teams/immunization-vaccines-and-biologicals', 'download', 'annual')
ON CONFLICT (code) DO NOTHING;
