## 1. Architecture Diagram

### ASCII Version (for README)
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              UWash Architecture                              │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌───────────────┐                                     ┌───────────────────┐
  │   HARDWARE    │                                     │    FRONTEND       │
  │               │                                     │                   │
  │  ┌─────────┐  │      POST /machine/update           │  ┌─────────────┐  │
  │  │  ESP32  │  │ ──────────────────────────────────► │  │   React     │  │
  │  │   +     │  │         (X-API-Key header)          │  │  Dashboard  │  │
  │  │ SW-420  │  │                                     │  │  (Vercel)   │  │
  │  │ Sensor  │  │                                     │  └──────┬──────┘  │
  │  └─────────┘  │                                     │         │         │
  │               │                                     │         │ GET     │
  │  Detects      │                                     │         │ /api/   │
  │  vibration    │                                     │         │ status  │
  └───────────────┘                                     │         │         │
                                                        │         ▼         │
                         ┌──────────────────────────────┴─────────────────┐ │
                         │                                                │ │
                         │            RAILWAY BACKEND                     │ │
                         │                                                │ │
                         │  ┌────────────────┐    ┌───────────────────┐   │ │
                         │  │   Flask API    │    │   Telegram Bot    │   │ │
                         │  │   (Port 8080)  │    │   (Polling Mode)  │   │ │
                         │  │                │    │                   │   │ │
                         │  │  Endpoints:    │    │  Commands:        │   │ │
                         │  │  /machine/     │    │  /start           │   │ │
                         │  │    update      │    │  /select          │   │ │
                         │  │  /api/status   │    │  /status          │   │ │
                         │  │  /api/start-   │    │                   │   │ │
                         │  │    cycle       │    │  Sends alarm when │   │ │
                         │  └───────┬────────┘    │  timer expires    │   │ │
                         │          │             └─────────┬─────────┘   │ │
                         │          │                       │             │ │
                         │          ▼                       ▼             │ │
                         │  ┌─────────────────────────────────────────┐   │ │
                         │  │              SQLite Database            │   │ │
                         │  │  (Persisted via Railway Volume)         │   │ │
                         │  │                                         │   │ │
                         │  │  Tables: timers, house_preferences,     │   │ │
                         │  │          alarms                         │   │ │
                         │  └─────────────────────────────────────────┘   │ │
                         │                                                │ │
                         └────────────────────────────────────────────────┘ │
                                                        │                   │
                                                        └───────────────────┘

  ┌───────────────┐
  │    USERS      │
  │               │
  │  ┌─────────┐  │     Telegram Messages
  │  │  Phone  │  │ ◄────────────────────────────────────────────────────────
  │  │  with   │  │
  │  │Telegram │  │
  │  └─────────┘  │
  └───────────────┘
```

### Mermaid Code 
```mermaid
flowchart TB
    subgraph Hardware["Edge Hardware"]
        ESP[ESP32 + SW-420<br/>Vibration Sensor]
    end

    subgraph Railway["Railway Backend"]
        API[Flask API<br/>Port 8080]
        Bot[Telegram Bot<br/>Polling Mode]
        DB[(SQLite<br/>Database)]
        API --> DB
        Bot --> DB
    end

    subgraph Frontend["Vercel Frontend"]
        React[React Dashboard]
    end

    subgraph Users["End Users"]
        Phone[Telegram App]
        Browser[Web Browser]
    end

    ESP -->|POST /machine/update| API
    React -->|GET /api/status| API
    React -->|POST /api/start-cycle| API
    Bot <-->|Telegram API| Phone
    Browser --> React
```

- **Hardware Cost**: ~$10-15 per machine (ESP32 $5 + SW-420 sensor $2 + wiring)
- **Latency**: <1 second from vibration detection to dashboard update
- **Scalability**: Single backend can handle 100+ machines across multiple houses
- **Zero Modification**: No internal wiring to machines, fully reversible installation
