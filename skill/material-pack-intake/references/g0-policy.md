# G0 policy precedence

This policy is authoritative for all G0 intake documents.

1. Every new project must use `g0-start-form.md` before material registration.
2. BGM is never inferred from an empty folder. The user must choose exactly one: `provided`, `use_library_later`, or `no_bgm`.
3. `provided` requires an audio file and an explicit permitted-use statement. `use_library_later` leaves the audio folder empty and creates a downstream reminder. `no_bgm` leaves the audio folder empty and records the deliberate decision.
4. If a BGM is added later, update the material-pack version record with the file, hash, timestamp, and permitted-use scope; do not silently merge it.
5. Any older wording that says an absent audio folder means “no BGM” is superseded by this policy and must be read as “BGM decision not yet recorded.”
