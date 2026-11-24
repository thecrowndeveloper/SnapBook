# RPI evidence gate

Run from repository root:

```bash
python tools/rpi/evidence_gate.py --record path/to/change-record.json
python -m unittest discover -s tools/rpi -p 'test_*.py'
```

Validator uses only Python standard library. It checks structural fields and evidence presence. It cannot verify that evidence is authentic, that tests actually ran, or that the implementation is safe.
