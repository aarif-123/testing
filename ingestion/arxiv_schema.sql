-- ============================================================
-- 🚀 GRAPH RAG DUAL-STORE SAFE SCHEMA
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- 📄 TABLE: arxiv_papers (UNIFIED STORE)
-- ============================================================
CREATE TABLE IF NOT EXISTS arxiv_papers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 🔥 MULTI-STORE SUPPORT
    source_store TEXT NOT NULL,         -- 'arxiv', 'dblp'
    source_id TEXT NOT NULL,            -- arxiv_id or dblp_id

    -- 🔥 GLOBAL ID (ANTI SPLIT-BRAIN)
    global_entity_id TEXT,              -- normalized identity

    -- Core fields
    title TEXT NOT NULL,
    abstract TEXT,

    authors TEXT[],
    categories TEXT[],
    published TIMESTAMPTZ,
    url TEXT,

    -- Ranking
    n_citation INT DEFAULT 0,

    -- Embedding (FORCE SAME MODEL)
    embedding VECTOR(768),
    embedding_model TEXT DEFAULT 'bge-base-en',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- 🔥 UNIQUE CONSTRAINT (CRITICAL)
    UNIQUE(source_store, source_id)
);

-- ============================================================
-- ⚡ INDEXES
-- ============================================================
CREATE INDEX idx_source_lookup
ON arxiv_papers(source_store, source_id);

CREATE INDEX idx_global_entity
ON arxiv_papers(global_entity_id);

CREATE INDEX idx_categories
ON arxiv_papers USING GIN(categories);

CREATE INDEX idx_title_fts
ON arxiv_papers USING GIN(to_tsvector('english', title));

CREATE INDEX idx_embedding
ON arxiv_papers
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- ============================================================
-- 📚 TABLE: CHUNKS
-- ============================================================
CREATE TABLE IF NOT EXISTS arxiv_chunks (
    id BIGSERIAL PRIMARY KEY,

    paper_id UUID REFERENCES arxiv_papers(id) ON DELETE CASCADE,

    chunk TEXT NOT NULL,
    chunk_index INT NOT NULL,

    embedding VECTOR(768),
    embedding_model TEXT DEFAULT 'bge-base-en',

    chunk_hash TEXT UNIQUE,
    section_type TEXT DEFAULT 'body',

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chunk_embedding
ON arxiv_chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_chunk_paper
ON arxiv_chunks(paper_id);

-- ============================================================
-- 🔗 TABLE: CITATIONS (GRAPH BACKUP)
-- ============================================================
CREATE TABLE IF NOT EXISTS arxiv_citations (
    id BIGSERIAL PRIMARY KEY,

    source_paper UUID REFERENCES arxiv_papers(id) ON DELETE CASCADE,
    target_source_id TEXT,
    target_store TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_citation_source
ON arxiv_citations(source_paper);

-- ============================================================
-- 👤 TABLE: AUTHORS (GLOBAL ENTITY LAYER)
-- ============================================================
CREATE TABLE IF NOT EXISTS authors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name TEXT NOT NULL,
    normalized_name TEXT,   -- lower(trim(name))

    global_author_id TEXT,  -- future ORCID / hash

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_author_normalized
ON authors(normalized_name);

-- ============================================================
-- 🔗 PAPER-AUTHOR RELATION
-- ============================================================
CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id UUID REFERENCES arxiv_papers(id) ON DELETE CASCADE,
    author_id UUID REFERENCES authors(id) ON DELETE CASCADE,

    PRIMARY KEY (paper_id, author_id)
);

-- ============================================================
-- 🔍 HYBRID SEARCH (MULTI-STORE SAFE)
-- ============================================================
CREATE OR REPLACE FUNCTION hybrid_search_arxiv(
    query_text TEXT,
    query_embedding VECTOR(768),
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id BIGINT,
    paper_id UUID,
    source_store TEXT,
    chunk TEXT,
    title TEXT,
    score FLOAT
)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    WITH vector_matches AS (
        -- Step 1: Broad vector retrieval (Fast via HNSW index)
        SELECT
            c.id,
            c.paper_id,
            c.chunk,
            (1 - (c.embedding <=> query_embedding))::FLOAT AS vector_score
        FROM arxiv_chunks c
        ORDER BY c.embedding <=> query_embedding
        LIMIT match_count * 10
    )
    SELECT
        vm.id,
        vm.paper_id,
        p.source_store,
        vm.chunk,
        p.title,
        -- Step 2: keyword ranking only on top candidates
        (vm.vector_score * 0.7 + 
         COALESCE(ts_rank_cd(to_tsvector('english', vm.chunk), plainto_tsquery('english', query_text)), 0) * 0.3
        )::FLOAT AS score
    FROM vector_matches vm
    JOIN arxiv_papers p ON vm.paper_id = p.id
    ORDER BY score DESC
    LIMIT match_count;
END;
$$;

-- ============================================================
-- 🔄 AUTO UPDATE TIMESTAMP
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_arxiv_papers
BEFORE UPDATE ON arxiv_papers
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();