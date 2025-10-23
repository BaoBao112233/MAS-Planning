# MAS-Planning Deployment Guide

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose installed
- Google Cloud Project with Vertex AI enabled
- Service Account JSON file with appropriate permissions

### Setup Steps

1. **Clone and Navigate**
   ```bash
   git clone <repository-url>
   cd MAS-Planning
   ```

2. **Environment Configuration**
   ```bash
   # Copy environment template
   cp .env.example .env
   
   # Edit configuration (required)
   nano .env
   ```

3. **Service Account Setup**
   ```bash
   # Place your Google Cloud service account JSON file
   cp /path/to/your/service-account.json ./service-account.json
   ```

4. **Deploy**
   ```bash
   # Development mode (with hot reload)
   ./deploy.sh development
   
   # OR Production mode
   ./deploy.sh production
   ```

## 🔧 Deployment Commands

```bash
# Start services
./deploy.sh development    # Dev mode with hot reload
./deploy.sh production     # Production mode

# Monitor services
./deploy.sh status         # Check service health
./deploy.sh logs           # Show all logs
./deploy.sh logs mas-planning   # Show app logs only

# Manage services
./deploy.sh stop           # Stop all services
./deploy.sh restart        # Restart services
./deploy.sh clean          # Stop and cleanup Docker resources
```

## 🌐 Service Endpoints

After deployment, the following services will be available:

| Service | URL | Description |
|---------|-----|-------------|
| **MAS-Planning API** | http://localhost:8000 | Main application API |
| **Health Check** | http://localhost:8000/health | Service health status |
| **API Documentation** | http://localhost:8000/docs | FastAPI Swagger UI |
| **Redis Cache** | localhost:6379 | Conversation history storage |
| **MCP Server** | http://localhost:9031 | Device control server |

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MAS-Planning  │    │      Redis      │    │   MCP Server    │
│   (FastAPI)     │◄──►│   (Cache)       │    │ (Device Control)│
│   Port: 8000    │    │   Port: 6379    │    │   Port: 9031    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐
│   Vertex AI     │
│  (Gemini Pro)   │
└─────────────────┘
```

## 📋 Environment Variables

### Required Configuration

```bash
# Google Cloud Settings
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-east1
GOOGLE_APPLICATION_CREDENTIALS=service-account.json

# Application Settings
APP_NAME=MAS Planning System
APP_PORT=8000

# Redis Settings
REDIS_HOST=redis
REDIS_PORT=6379
TTL_SECONDS=3600

# MCP Server Settings
MCP_SERVER_URL=http://mcp-server:9031
```

### Optional Configuration

```bash
# Multi-Agent Settings
MAX_TURNS=20
MAX_MSG=12
LIMIT_MINUTES=10
DEBUG_MODE=false

# Resource Limits
CPU_LIMIT=2.0
MEMORY_LIMIT=2G
```

## 🔍 Monitoring & Debugging

### Health Checks
```bash
# Overall service status
./deploy.sh status

# Individual service health
curl http://localhost:8000/health
curl http://localhost:9031/health
```

### Logs
```bash
# All services
./deploy.sh logs

# Specific service
./deploy.sh logs mas-planning
./deploy.sh logs redis
./deploy.sh logs mcp-server

# Follow logs in real-time
docker-compose logs -f mas-planning
```

### Debug Mode
```bash
# Enable debug mode in .env
DEBUG_MODE=true

# Restart with debug logging
./deploy.sh restart
```

## 🛠️ Development

### Local Development Setup
```bash
# Start in development mode (with hot reload)
./deploy.sh development

# Code changes will automatically restart the application
```

### Custom Configuration
```bash
# Use custom docker-compose file
docker-compose -f docker-compose.custom.yml up

# Override specific settings
HOST_PORT=8080 ./deploy.sh production
```

## 🚨 Troubleshooting

### Common Issues

1. **Service Account Permission Issues**
   - Ensure service account has Vertex AI permissions
   - Check GOOGLE_APPLICATION_CREDENTIALS path

2. **Redis Connection Failed**
   - Verify Redis container is running: `docker-compose ps`
   - Check Redis logs: `./deploy.sh logs redis`

3. **MCP Server Not Responding**
   - Check MCP server logs: `./deploy.sh logs mcp-server`
   - Verify MCP_SERVER_URL configuration

4. **Port Already in Use**
   - Change HOST_PORT in .env file
   - Or stop conflicting services

### Reset Everything
```bash
# Complete cleanup and restart
./deploy.sh clean
./deploy.sh production
```

## 📊 Performance Tuning

### Resource Allocation
```bash
# In .env file
CPU_LIMIT=4.0          # Increase CPU limit
MEMORY_LIMIT=4G        # Increase memory limit
```

### Redis Optimization
```bash
# Increase Redis memory limit (in docker-compose.yml)
command: ["redis-server", "--maxmemory", "512mb"]
```

### Scaling
```bash
# Scale specific services
docker-compose up --scale mas-planning=2
```

## 🔐 Security Considerations

1. **Service Account**: Use minimal required permissions
2. **Network**: Configure firewall rules for production
3. **Environment Variables**: Never commit .env files
4. **Updates**: Regularly update Docker images

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Google Vertex AI](https://cloud.google.com/vertex-ai)
- [Redis Documentation](https://redis.io/documentation)
- [Docker Compose Reference](https://docs.docker.com/compose/)