# Datasheet: RAG Demo Dataset Contour

## Dataset Identity

- Name: `rag_documents`
- Purpose: synthetic and sample RAG-oriented knowledge base documents for demonstrating DQ observability checks
- Status: demo / MVP artifact
- Domain: not specified

## Intended Use

- Validate dirty-data checks on text and metadata
- Validate staleness and temporal drift checks on document update timestamps
- Demonstrate dataset versioning and publication gate behavior in LLMOps workflows

## Non-Intended Use

- Production retrieval corpus
- Domain-specific compliance evaluation
- Legal, medical, or other high-stakes decision support

## Data Composition

Required fields:
- `doc_id`
- `title`
- `text`
- `source`
- `language`
- `updated_at`

Optional fields:
- `sensitivity`
- `metadata`

Representative sample files:
- `datasets/samples/rag_documents_extended_v2.jsonl`
- `datasets/samples/rag_documents_recent_v2.jsonl`

Representative degraded files:
- `datasets/synthetic/rag_documents_dirty_v1.jsonl`
- `datasets/synthetic/rag_documents_stale_v1.jsonl`

## Collection And Generation

- Source: synthetic / handcrafted sample documents
- Collection process: manual construction for MVP validation scenarios
- Timestamp semantics: `updated_at` represents source document recency

## Quality Risks

- Dirty data:
  - duplicates
  - missing fields
  - invalid timestamps
  - malformed language values
  - text normalization issues
- Staleness:
  - missing recent updates
  - missing bucket coverage
  - temporal distribution shift

## DQ Controls

Implemented controls:
- schema validity
- completeness
- duplicate ratio
- pattern validity
- text length validity
- normalization ratio
- freshness
- update lag
- coverage by time buckets
- temporal PSI

Gate behavior:
- hard gate failure blocks publication
- soft gate warning allows progression with warnings

## Ethics And Limitations

- Demo corpus is not representative of any real organization or customer population
- Language coverage is minimal and intentionally simplified
- Conclusions from this contour should not be generalized to production datasets without domain-specific calibration
