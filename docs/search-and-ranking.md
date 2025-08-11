# Search & Ranking

## Query Types
- Natural language (text → embedding)
- Person filter (include/exclude)
- Tag filter (must/any/exclude)
- Time range
- Event / album scoping

## Processing Flow
1. Parse user query into: text_terms, filters
2. If text_terms → text embedding
3. Retrieve top K via vector similarity
4. Apply metadata filters (post-filter if small K, pre-filter candidate set if large)
5. Compute hybrid score
6. Re-rank & paginate

## Hybrid Score Example
```
score = w_img * sim_img + w_txt * sim_txt + w_person * person_bonus + w_recency * recency_decay
```

## Re-ranking Signals
- Exact tag matches
- Person match confidence
- Recency decay (exp(-Δt / τ))
- Event prominence (size, thematic match)

## Caching
- Embedding queries hashed by text + model_version
- Short-term LRU cache for frequent queries

## Future Enhancements
- Multi-vector queries (image + text combined)
- Pseudo-relevance feedback (expand tags from top results)
- Diversification to avoid near-duplicate clutter
