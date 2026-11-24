# RPI Agent Skill

Portable Research → Plan → Implement workflow pack for existing applications and greenfield systems.

## Contents
- `SKILL.md`: workflow instructions and depth selection.
- `playbooks/`: quick, standard, and deep progressive-depth guides.
- `templates/`: reusable Markdown records and a JSON change record.
- `tools/rpi/evidence_gate.py`: standard-library JSON evidence-presence validator.
- `tools/rpi/test_evidence_gate.py`: standard-library unit tests.
- `evals/adversarial-scenarios.md`: adversarial evaluation prompts and scoring.

## Run validator/tests
From repository root:

```sh
python tools/rpi/evidence_gate.py --record skills/rpi-workflow/templates/change-record.json
```

The starter template is intentionally incomplete and should fail until a change record is filled.

```sh
python -m unittest discover -s tools/rpi -p 'test_*.py'
```

Validator is deliberately conservative. It checks field structure and evidence presence only; it does not judge evidence truth, quality, security, or correctness.
