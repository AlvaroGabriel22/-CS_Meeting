# Real raw data (not committed)

Drop the **real** department workbooks here to validate the parser against them:

```
real/
├── IQC_<week>.xlsx
├── OQC_<week>.xlsx
└── FIELD_<week>.xlsx
```

Then run:

```bash
cd backend
.venv/bin/python -m app.tools.inspect_raw tests/fixtures/real/IQC_W34.xlsx --department IQC
```

Any test placed in `tests/test_real_files.py` should **skip** when this folder is
empty, so the suite keeps running on a machine without the confidential files.

Everything currently in `tests/fixtures/build_fixtures.py` is *synthetic and
provisional* (ADR-0011): it reproduces the structures described in the
specification, not real data.

Files in this folder are gitignored.
