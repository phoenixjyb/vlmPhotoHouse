# Person-Based Search API

This document describes the person-based search functionality in the VLM Photo Engine. The system allows you to find photos containing specific people using multiple search methods.

## Overview

The person-based search feature provides three main capabilities:

1. **Search by Person ID**: Find all photos containing a specific person
2. **Search by Person Name**: Find photos by searching for people by name
3. **Vector Search with Person Filter**: Combine semantic search with person filtering

## Prerequisites

Before using person-based search, ensure you have:

1. **Assets ingested** with photos containing faces
2. **Face detection** configured (MTCNN or other providers)
3. **Face embeddings** generated (Facenet, InsightFace, LVFace, etc.)
4. **Person clustering** completed to group faces into persons
5. **Person names** assigned for name-based searching

## API Endpoints

### 1. Search Photos by Person ID

Find all photos containing a specific person.

```http
GET /search/person/{person_id}
```

**Parameters:**
- `person_id` (path): The ID of the person to search for
- `page` (query, optional): Page number (default: 1)
- `page_size` (query, optional): Items per page (default: 20, max: 200)

**Example:**
```bash
curl "http://localhost:8000/search/person/123?page=1&page_size=10"
```

**Response:**
```json
{
  "api_version": "0.1.0",
  "page": 1,
  "page_size": 10,
  "total": 25,
  "person_id": 123,
  "person_name": "John Doe",
  "items": [
    {
      "id": 456,
      "path": "/photos/family_vacation.jpg"
    },
    {
      "id": 789,
      "path": "/photos/birthday_party.jpg"
    }
  ]
}
```

### 2. Search Photos by Person Name

Find photos by searching for people with matching names (case-insensitive partial match).

```http
GET /search/person/name/{name}
```

**Parameters:**
- `name` (path): The name to search for (partial matches supported)
- `page` (query, optional): Page number (default: 1)  
- `page_size` (query, optional): Items per page (default: 20, max: 200)

**Example:**
```bash
curl "http://localhost:8000/search/person/name/John"
```

**Response:**
```json
{
  "api_version": "0.1.0",
  "page": 1,
  "page_size": 20,
  "total": 18,
  "search_name": "John",
  "matched_persons": [
    {
      "id": 123,
      "name": "John Doe"
    },
    {
      "id": 456,
      "name": "Johnny Smith"
    }
  ],
  "items": [
    {
      "id": 789,
      "path": "/photos/wedding.jpg"
    }
  ]
}
```

### 3. Vector Search with Person Filter

Combine semantic vector search with person filtering.

```http
POST /search/person/vector
```

**Request Body:**
```json
{
  "text": "beach vacation sunset",
  "person_id": 123,
  "k": 10
}
```

**Parameters:**
- `text` (optional): Text query for semantic search
- `asset_id` (optional): Use another photo as query (alternative to text)
- `person_id` (optional): Filter results to only include this person
- `k`: Number of results to return (default: 10)

**Example:**
```bash
curl -X POST "http://localhost:8000/search/person/vector" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "family gathering",
    "person_id": 123,
    "k": 5
  }'
```

**Response:**
```json
{
  "api_version": "0.1.0",
  "query": {
    "text": "family gathering",
    "asset_id": null
  },
  "k": 5,
  "person_filter": {
    "person_id": 123,
    "person_name": "John Doe"
  },
  "results": [
    {
      "asset_id": 456,
      "score": 0.85,
      "path": "/photos/christmas_dinner.jpg"
    },
    {
      "asset_id": 789,
      "score": 0.72,
      "path": "/photos/thanksgiving.jpg"
    }
  ]
}
```

## Person Management API

Before searching, you need to manage persons. Here are key person management endpoints:

### List All Persons

```bash
curl "http://localhost:8000/persons"
```

### Rename a Person

```bash
curl -X POST "http://localhost:8000/persons/123/name" \
  -H "Content-Type: application/json" \
  -d '{"display_name": "John Doe"}'
```

### Merge Persons

```bash
curl -X POST "http://localhost:8000/persons/merge" \
  -H "Content-Type: application/json" \
  -d '{
    "target_id": 123,
    "source_ids": [456, 789]
  }'
```

### Assign Faces to Person

```bash
curl -X POST "http://localhost:8000/faces/assign" \
  -H "Content-Type: application/json" \
  -d '{
    "face_ids": [1, 2, 3],
    "person_id": 123
  }'
```

## Workflow Example

Here's a typical workflow for setting up and using person-based search:

### 1. Initial Setup

```bash
# Check system status
curl "http://localhost:8000/health"

# List current persons
curl "http://localhost:8000/persons"
```

### 2. Ingest Photos

```bash
# Ingest photos (using CLI)
python -m app.cli ingest-scan /path/to/photos
```

### 3. Process Faces

```bash
# Trigger face clustering
curl -X POST "http://localhost:8000/persons/recluster"

# Check clustering progress
curl "http://localhost:8000/persons/recluster/status"
```

### 4. Manage Persons

```bash
# List unassigned faces
curl "http://localhost:8000/faces?unassigned=true"

# Create a new person and assign faces
curl -X POST "http://localhost:8000/faces/assign" \
  -H "Content-Type: application/json" \
  -d '{
    "face_ids": [1, 2, 3],
    "create_new": true
  }'

# Name the person
curl -X POST "http://localhost:8000/persons/1/name" \
  -H "Content-Type: application/json" \
  -d '{"display_name": "John Doe"}'
```

### 5. Search Photos

```bash
# Find all photos of John Doe
curl "http://localhost:8000/search/person/1"

# Search by name
curl "http://localhost:8000/search/person/name/John"

# Semantic search with person filter
curl -X POST "http://localhost:8000/search/person/vector" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "outdoor activities",
    "person_id": 1,
    "k": 10
  }'
```

## Error Handling

### Common Error Responses

**Person Not Found (404):**
```json
{
  "detail": "person not found"
}
```

**No Results Found:**
```json
{
  "total": 0,
  "items": []
}
```

**Vector Index Not Available (503):**
```json
{
  "detail": "Vector index not initialized"
}
```

### Best Practices

1. **Always check person existence** before searching by ID
2. **Use pagination** for large result sets
3. **Handle empty results gracefully** when no photos match
4. **Combine search methods** for better user experience
5. **Cache person lists** to avoid repeated API calls

## Integration with Other Features

### Face Detection

Person search relies on face detection being configured:

```bash
# Check face detection status
curl "http://localhost:8000/health"

# Configure face detection provider
export FACE_DETECT_PROVIDER=mtcnn
```

### Face Embeddings

Ensure face embeddings are generated:

```bash
# Check embedding status
curl "http://localhost:8000/health"

# Configure face embedding provider
export FACE_EMBED_PROVIDER=facenet
```

### Vector Search

For semantic search capabilities:

```bash
# Check vector index status
curl "http://localhost:8000/health"

# Vector index is built automatically from image embeddings
```

## Performance Considerations

### Database Optimization

- Face detection and embeddings are indexed for fast queries
- Person assignments use foreign key constraints for referential integrity
- Search queries use optimized SQL with proper indexing

### Large Datasets

- Use pagination for large photo collections
- Consider result limits for vector search (default k=10)
- Person clustering may take time for large face counts

### Caching

- Person metadata is lightweight and can be cached
- Search results can be cached based on query parameters
- Face embeddings are cached in the database

## Security & Privacy

### Access Control

- All endpoints require appropriate authentication (when configured)
- Person data includes only assigned display names
- Face detection data is kept separate from person identity

### Data Privacy

- Face embeddings are numerical vectors, not images
- Original photos remain in configured storage location
- Person assignments can be modified or deleted at any time

## Troubleshooting

### No Persons Found

1. Check if face detection is running: `curl "http://localhost:8000/tasks?type=face_detect"`
2. Verify face embedding configuration: `curl "http://localhost:8000/health"`
3. Run person clustering: `curl -X POST "http://localhost:8000/persons/recluster"`

### Search Returns No Results

1. Verify person exists: `curl "http://localhost:8000/persons/{id}"`
2. Check if person has associated faces: `curl "http://localhost:8000/faces?person_id={id}"`
3. Ensure photos are properly ingested: `curl "http://localhost:8000/assets"`

### Vector Search Fails

1. Check vector index status: `curl "http://localhost:8000/health"`
2. Verify embedding configuration
3. Ensure assets have been processed for embeddings

This person-based search system provides a powerful foundation for organizing and finding photos by the people in them, enabling intuitive photo discovery and management.
