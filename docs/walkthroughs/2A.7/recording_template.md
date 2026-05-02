# Phase 2A Walkthrough — Recording Template

Same format as Phase 1.8 (`docs/walkthroughs/1.8/recording_template.md`).

For each input from `test_inputs.md`:

```
INPUT #N: <input>
EXPECTED: <one-line>
OBSERVED: <one-line>
LATENCY: <ms or qualitative>
SEVERITY: PASS | P3 | P2 | P1 | P0
NOTES: <observations / video timestamp>
```

End with summary block:
```
OVERALL: <pass count>/24
P0/P1/P2/P3 counts: <numbers>
RECOMMENDATION: ship / ship-with-fixes / halt
EVALUATOR: <name + date>
```

## File naming
- `.private/walkthroughs/2A.7_<initials>_<YYYY-MM-DD>.mp4` (gitignored)
- `outputs/audits/walkthroughs/2A.7_<initials>_<YYYY-MM-DD>.md` (TRACKED)

## GPG attestation per Plan v13 §C-private
After saving video, generate:
```bash
gpg --clearsign --digest-algo SHA256 --local-user <msn_fingerprint> \
    --output outputs/audits/attestations/2A.7_<initials>.md.asc \
    /tmp/attestation_payload.txt
```

Attestation payload format:
```
task_id: 2a.7
artifact_type: walkthrough_recording
artifact_path: .private/walkthroughs/2A.7_<initials>_<YYYY-MM-DD>.mp4
artifact_sha256: <sha256 of .mp4>
size_bytes: <bytes>
signed_by: <evaluator name>
signed_at: <ISO-8601 UTC>
canonical_pin_sha: <from docs/canonical_pin.txt>

ATTESTATION: I attest that the above-named recording exists at the stated
path with the stated SHA256, that I personally executed the walkthrough,
and that this attestation was generated within 24 hours of recording.
```
