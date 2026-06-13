# Orpheus Poll to Playlist

<p align="center">
  <img src="https://img.shields.io/badge/Version-1.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/Python-3.10+-green?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react" alt="React">
  <img src="https://img.shields.io/badge/License-MIT-purple?style=for-the-badge" alt="License">
</p>

Web application that fetches the Album of the Month poll from Orpheus Network, downloads selected albums via qBittorrent, and automatically creates playlists in Navidrome.

## 📸 Demo



## 🚀 Quick Start

### Using Docker Compose (Recommended)

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/orpheus-poll-to-playlist.git
   cd orpheus-poll-to-playlist
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Update image references** (optional)
   
   Edit `docker-compose.yml` and replace `yourusername` with your GitHub username in the image references.

4. **Start the services**
   ```bash
   # Using pre-built images from GitHub Container Registry
   docker compose up -d
   
   # Or build locally
   docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
   ```

5. **Access the application**
   
   Open http://localhost:7575 in your browser

### Manual Installation

#### Prerequisites
- Python 3.10+
- Node.js 18+
- Valid Orpheus Network account with API key

#### Backend Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### Frontend Setup
```bash
cd frontend
npm install
npm run build
cd ..
```

#### Run
```bash
python run.py
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `ORPHEUS_API_KEY` | Your Orpheus API key | ✅ | - |
| `ORPHEUS_SESSION_COOKIE` | Session cookie for page scraping | ✅ | - |
| `APP_HOST` | Server bind address | ❌ | `0.0.0.0` |
| `APP_PORT` | Server port | ❌ | `7575` |
| `CACHE_TTL_MINUTES` | Cache expiration time | ❌ | `30` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | ❌ | `INFO` |
| `DEBUG` | Enable debug mode with hot-reload | ❌ | `false` |

### qBittorrent Integration

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `QBIT_URL` | qBittorrent WebUI URL | ❌ | - |
| `QBIT_USER` | qBittorrent username | ❌ | - |
| `QBIT_PASSWORD` | qBittorrent password | ❌ | - |
| `QBIT_CATEGORY` | Category for downloads | ❌ | `orpheus` |

### Navidrome Integration

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `NAVIDROME_URL` | Navidrome server URL | ❌ | - |
| `NAVIDROME_USER` | Navidrome username | ❌ | - |
| `NAVIDROME_PASSWORD` | Navidrome password | ❌ | - |

### Discord Notifications (poll-notifier)

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL | ❌ | - |
| `NOTIFIER_CRON_SCHEDULE` | Cron schedule for checks | ❌ | `0 9 * * *` |
| `NOTIFIER_RUN_ON_START` | Run check on start | ❌ | `true` |

### Getting Your Credentials

#### API Key
1. Log into Orpheus Network
2. Go to **User Settings** → **API Keys**
3. Create a new API key

#### Session Cookie
1. Log into Orpheus Network
2. Open Developer Tools (F12)
3. Go to **Application** → **Cookies**
4. Copy the `session` cookie value

## 🔌 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/poll` | Get cached poll albums |
| `POST` | `/api/poll/refresh` | Refresh poll from Orpheus |
| `POST` | `/api/album/{id}/search` | Search for album on Orpheus |
| `GET` | `/api/album/{id}/formats` | Get available torrent formats |
| `POST` | `/api/torrent/download` | Download a single torrent file |
| `POST` | `/api/torrent/batch-download` | Send multiple torrents to qBittorrent |
| `GET` | `/api/qbit/status` | Check qBittorrent connection |
| `GET` | `/api/downloads/status` | Get download progress |
| `POST` | `/api/playlist/create` | Create Navidrome playlist |
| `GET` | `/api/playlist/id` | Get saved playlist ID and URL |
| `GET` | `/api/cache/status` | Get cache status |

## 📁 Project Structure

```
orpheus-poll-to-playlist/
├── backend/
│   ├── __init__.py          # Package metadata & version
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration settings
│   ├── database.py          # SQLite database models
│   ├── orpheus_client.py    # Orpheus API client
│   └── navidrome_client.py  # Navidrome/Subsonic client
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main React component
│   │   ├── api.ts           # API client functions
│   │   ├── types.ts         # TypeScript types
│   │   ├── index.css        # Tailwind + custom styles
│   │   └── main.tsx         # Entry point
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
├── notifier/
│   ├── Dockerfile           # Notifier container
│   ├── poll_checker.py      # Discord notification script
│   ├── entrypoint.sh        # Cron setup script
│   └── requirements.txt
├── data/                    # SQLite database (auto-created)
├── downloads/               # Downloaded torrents (auto-created)
├── docker-compose.yml       # Docker Compose configuration (uses registry images)
├── docker-compose.build.yml # Override for local builds
├── Dockerfile               # Main application container
├── .github/
│   └── workflows/
│       └── docker.yml       # CI/CD pipeline
├── requirements.txt         # Python dependencies
├── run.py                   # Application entry point
├── .env.example             # Example environment config
└── README.md
```

## 🔧 Development

### Running in Development Mode

**Backend (with hot-reload):**
```bash
DEBUG=true python run.py
```

**Frontend (with HMR):**
```bash
cd frontend
npm run dev
```

The frontend dev server runs on port 3000 and proxies API requests to the backend.

### Building

```bash
# Build frontend
cd frontend && npm run build

# Build Docker image
docker build -t orpheus-poll-to-playlist .
```

## 🐳 Docker

### Using Pre-built Images
```bash
# Pull and run from GitHub Container Registry
docker compose up -d
```

### Build Locally
```bash
# Build and run locally
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

### View Logs
```bash
docker compose logs -f orpheus-poll
docker compose logs -f poll-notifier
```

### Stop Services
```bash
docker compose down
```

### Available Images

| Image | Description |
|-------|-------------|
| `ghcr.io/yourusername/orpheus-poll-to-playlist:latest` | Main application |
| `ghcr.io/yourusername/orpheus-poll-to-playlist-notifier:latest` | Discord notifier |

Tags available: `latest`, `main`, `v1.0.0`, `1.0`, `1`, `<sha>`

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This tool is for personal use only. Make sure to comply with Orpheus Network's rules and terms of service.

## 🙏 Acknowledgments

- UI design inspired by [autobrr](https://github.com/autobrr/autobrr) and [qui](https://github.com/autobrr/qui)
- Built with [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), and [Tailwind CSS](https://tailwindcss.com/)
