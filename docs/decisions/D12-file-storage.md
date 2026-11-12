# D12 — Uploads on local disk

**Status:** accepted

**Decision.** Files are stored under `backend/storage/<org_id>/` with random names, checked by
content type, and served only through authenticated endpoints with
`Content-Disposition: attachment`. No object storage.
