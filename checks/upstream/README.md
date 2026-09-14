# External Slicer Regression Suite

The Linux x64 release gate runs every test in OrcaSlicer's
[orca-test-repo](https://github.com/OrcaSlicer/orca-test-repo) at commit
`4bac4c7539c21edcd6abec8a248c3e6ae18aaa2c`.
Update the pinned revision deliberately, with a fresh full regression run.

## Reference Schema Compatibility

`orca-test-repo-reference-schema.patch` fixes a test-parser mismatch, not an
application assertion. The suite's reference G-code/3MF was exported by a
newer upstream build and includes five string-vector settings not present in
TinManX1's source schema. Without a type, the parser reads a quoted empty
vector element as a literal pair of quote characters.

The patch falls back to the suite's own pinned schema snapshot for decoding
unknown reference fields. Live option definitions still take precedence.
It does not expose unsupported options to the CLI sweep, change expected
values, ignore differences, add skips, or add expected failures. Two added
tests verify those boundaries.

The upstream suite already marks known upstream defects as expected failures
and has platform/feature skips. These are not new TinManX1 exceptions. Its
bundled G-code validator is a Linux x86-64 executable; on a Mac it must be run
in Linux separately, or the full suite run on the Linux CI worker.
