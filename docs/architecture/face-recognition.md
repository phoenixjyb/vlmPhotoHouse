# Face Recognition Pipeline

## Steps
1. Detection: run RetinaFace on image (skip if no faces)
2. Crop & Align: normalize face region
3. Embedding: ArcFace model outputs 512-d vector
4. Clustering: assign to existing person cluster or mark as unknown
5. Labeling: user labels cluster; propagate person_id
6. Feedback: corrected labels stored; future active learning

## Incremental Clustering
- Maintain centroid + variance per cluster
- New face → compute distance to centroids
- Thresholds: T_assign, T_new_cluster

## Few-Shot Seeding
- User provides 3–5 examples per known person
- Initialize clusters with provided embeddings

## Ambiguity Handling
- Low margin between best & second best → queue for review

## Privacy
- All face embeddings stored locally only

## Open Questions
- Clustering algorithm choice (HDBSCAN vs incremental k-means)
- Handling aging & appearance variation
