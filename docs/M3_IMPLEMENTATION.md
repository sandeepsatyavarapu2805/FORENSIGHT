# M3 ingestion foundation

## Format support status

No genuine UFDR sample, container specification, or finalized parser reference is
currently present in `docs/` or `sample-data/`. Consequently, the production
parser registry intentionally contains no adapters. Uploads fail explicitly with
HTTP 415 until an adapter backed by a legitimate sample is added.

The `SyntheticParserAdapter` under `backend/tests/` is test-only. Its `.synthetic`
fixture markers are not a UFDR format and must never be presented as product
support.

## Implemented parser-neutral flow

1. An authorized investigator registers an Evidence Source.
2. The upload endpoint selects an adapter by its declared filename support.
3. The original input is copied in bounded chunks to a generated storage key
   while calculating size and SHA-256.
4. The selected adapter validates the stored source.
5. Investigator confirmation invokes the processing boundary.
6. Parser-neutral artifacts are normalized and inserted into immutable
   `evidence_items` records with source, case, parser, and original-record
   provenance.
7. Fatal, partial, and successful states remain persistent and visible.

Processing currently runs synchronously for bounded SIH fixtures inside a normal
FastAPI synchronous endpoint, which FastAPI executes in its worker thread pool.
The `process_source` service boundary can be moved to a dedicated worker later
without changing API or persistence contracts.

## Normalized evidence trade-off

M3 uses one common evidence table with an artifact type, common indexed
provenance/timestamp/application fields, searchable text, typed normalized JSON,
and preserved raw metadata. This avoids speculative tables for artifact classes
not demonstrated by a real sample while retaining typed rendering and future
filter/search capability. Imported evidence has read-only APIs; no update or
delete endpoint exists.

## Storage

Local prototype storage defaults to `backend/var/uploads` and is excluded from
Git. `UPLOAD_STORAGE_PATH` can point to persistent storage. PostgreSQL stores only
the generated storage key and forensic metadata, never uploaded bytes.
