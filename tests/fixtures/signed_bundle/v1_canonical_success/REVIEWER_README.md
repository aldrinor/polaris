# POLARIS audit bundle — reviewer guide (canonical-success fixture)

This bundle is the v1.0 SUCCESS-shape canonical fixture used by
I-cd-013a Inspector route tests. The active bundle producer emits
this file with `content_type="metadata"` alongside `metadata.json`;
downstream consumers MUST select `metadata.json` by explicit path.
