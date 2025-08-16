# Captioning & Annotations

## Caption Generation
- Trigger: on-demand or background batch
- Model: BLIP2 initial; store text + model version
- Retry failed captions with backoff

## Enrichment
- Extract keywords (noun phrases) → candidate tags
- Summarize group of photos for event / album description (future)

## User Annotations
- Free-text field (stored separately from model caption)
- Edit caption: mark user_edited=true (preserve original for audit)

## Voice Input (Planned)
- Record audio → transcribe via local Whisper → treat as annotation

## Tagging
- Tags originate from: model (auto), user, system (person/time/event)
- Confidence stored for auto tags

## Feedback Loop
- User removes incorrect tag → add to negative examples set

## Storage
```
captions/{asset_id}.json
{
  "model": "blip2-xxx",
  "caption": "A dog running on the beach",
  "generated_at": "...",
  "user": {"edited": false, "text": null}
}
```
