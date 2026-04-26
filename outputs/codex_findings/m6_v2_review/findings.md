# Codex re-review of M-6 v2

## Verdict
GREEN

## Fix integration
- [x] Bundle hardening (fail-loud + INDEX + MANIFEST.SHA256)
- [x] Terminology fixed (ZIP not PDF)
- [x] Two-family banner: warning + violation states
- [x] Retrieval queries surfaced
- [x] Pre-generation gates surfaced (adequacy + corpus approval)
- [x] Tier band edge cases (zero max, residual rows)

## New issues
none

## Final word
GREEN to lock M-6. `INDEX.txt` reads procurement-grade on the demo run; extracted bundle digests matched `MANIFEST.SHA256`, and incomplete-run bundle generation failed loud with HTTP 500.
