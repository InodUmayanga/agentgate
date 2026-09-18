# Golden tasks

One file per skill. Each case has an `input`, the `expected_tools` the run
must call (order-insensitive prefix; extra read tools are allowed, extra
write tools are not), `expected_facts` that must appear in the output with a
valid `source_ref`, and `forbidden` outcomes. Deterministic checks run with
recorded tool results, so CI needs no model key; the optional judge rubric
runs only when `ANTHROPIC_API_KEY` is set.
