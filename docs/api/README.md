# API Documentation

This section contains API documentation and integration guides for the VLM Photo Engine.

## 📋 API Reference

### Core APIs
- **[API Outline](./api-outline.md)** - Complete API reference and endpoints
- **[Person Search API](./person-based-search-api.md)** - Person recognition and search endpoints

## 🚀 Quick Start

### Base URL
```
http://localhost:8001
```

### Authentication
Currently, the API runs locally without authentication. For production deployments, consider adding authentication layers.

## 📡 Key Endpoints

### Health Monitoring
```http
GET /health                 # System status
GET /health/caption         # Caption model status  
GET /health/lvface          # Face recognition status
```

### Photo Management
```http
POST /ingest/scan          # Scan directory for photos
GET /assets/{id}           # Get photo metadata
GET /assets/{id}/thumbnail # Get photo thumbnail
```

### Search
```http
POST /search               # Multi-modal search
GET /search/similar/{id}   # Find similar photos
```

### Person Management
```http
GET /people                # List detected people
GET /people/{id}/photos    # Get photos of specific person
POST /people/{id}/merge    # Merge person clusters
```

## 🔧 Integration Examples

### Python Client
```python
import requests

# Health check
response = requests.get("http://localhost:8001/health")
print(response.json())

# Search for photos
response = requests.post("http://localhost:8001/search", 
    json={"query": "sunset beach"})
photos = response.json()
```

### JavaScript/Node.js
```javascript
const axios = require('axios');

// Search with fetch
const searchPhotos = async (query) => {
    const response = await axios.post('http://localhost:8001/search', {
        query: query
    });
    return response.data;
};
```

### cURL Examples
```bash
# Health check
curl http://localhost:8001/health

# Search photos
curl -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "family vacation"}'

# Get people
curl http://localhost:8001/people
```

## 📊 Response Formats

### Standard Response
```json
{
  "status": "success",
  "data": { /* response data */ },
  "timestamp": "2025-08-16T10:30:00Z"
}
```

### Error Response
```json
{
  "status": "error", 
  "message": "Description of error",
  "code": "ERROR_CODE",
  "timestamp": "2025-08-16T10:30:00Z"
}
```

## 🎯 Search Query Format

### Text Search
```json
{
  "query": "sunset beach waves",
  "limit": 20,
  "offset": 0
}
```

### Person-Based Search
```json
{
  "query": "family dinner",
  "person_id": "person_123",
  "limit": 10
}
```

### Date Range Search
```json
{
  "query": "vacation photos",
  "date_from": "2024-01-01",
  "date_to": "2024-12-31"
}
```

## 🔍 Advanced Features

### Similarity Search
Find photos similar to a specific image:
```http
GET /search/similar/photo_id_123?limit=10
```

### Batch Operations
Process multiple photos at once:
```http
POST /assets/batch
{
  "asset_ids": ["id1", "id2", "id3"],
  "operations": ["generate_caption", "detect_faces"]
}
```

## 📈 Performance Considerations

- **Search Performance**: Target <500ms for most queries
- **Rate Limiting**: No current limits for local deployment
- **Caching**: Responses are cached for improved performance
- **Pagination**: Use `limit` and `offset` for large result sets

## 🔒 Security Notes

- API runs on localhost by default
- No authentication required for local deployment
- For remote access, implement authentication and HTTPS
- Consider API rate limiting for production use

---

*For detailed endpoint specifications, see the individual API documentation files.*
