# Kuku FM Promo Finder — Parser Phase

## Current scope
This first implementation parses the six supplied development screenplay files into structured episode, scene, and event records. It preserves original timestamps and event content, and deliberately retains overlapping event intervals.

It does **not** generate promo candidates, call an LLM, build embeddings, or infer visuals. Those are later phases.

## Run
```bash
python parser/screenplay_parser.py --input data/samples --output data/parsed_episodes.json
python -m unittest discover -s tests -v
```

## Parsed structure
- Episode metadata: episode number, logline, continuity notes
- Scene metadata: scene ID, heading, start/end timestamp
- Event records: event type/speaker label, start/end timestamp, numeric seconds, duration, raw content
- Parse validation: structural errors and boundary warnings

## Important implementation behavior
- `00:54.50` is parsed as 54.5 seconds.
- Overlapping CAMERA, ACTION, dialogue, and SOUND FX entries remain separate events.
- Event duration is not added across overlapping tracks.
- Source text is retained so downstream steps can cite exact screenplay evidence.
- Camera directions are text descriptions only; this parser does not verify actual footage.

## Next phase
Review parser output and edge cases before building structured retrieval and narrative-context RAG.
