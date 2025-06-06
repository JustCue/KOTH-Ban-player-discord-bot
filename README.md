# Discord Moderation Bot

A customizable Discord moderation bot built in Python, designed to streamline ban/strike management, ban history tracking, and administrative setup. Utilizing slash commands and a modular “cogs” structure, this bot integrates with a MySQL (aiomysql) or PyMySQL database to store and retrieve player information and punishment records.

---

## Table of Contents

- [Features](#features)  
- [Prerequisites](#prerequisites)  
- [Installation](#installation)  
- [Configuration](#configuration)  
- [Running the Bot](#running-the-bot)  
- [Directory Structure](#directory-structure)  
- [Slash Commands & Usage](#slash-commands--usage)  
  - [/setup](#setup-command)  
  - [/ban](#ban-command)  
  - [/strike](#strike-command)  
  - [/history](#history-command)  
- [Environment Variables](#environment-variables)  
- [Contributing](#contributing)  
- [License](#license)  

---

## Features

- **Slash‐Command‐Based**  
  All core functionality is exposed via Discord “/” commands, eliminating the need for prefix‐based commands.

- **Modular Cogs**  
  - `admin_cog.py`: Administrative utilities (role checks, permission utilities, etc.).  
  - `ban_cog.py`: Slash commands for issuing bans (standard & custom), building ban forms, and logging pending bans.  
  - `history_cog.py`: Fetch and display ban/strike history for a given user.  
  - `setup_cog.py`: Initial guild setup for channels, roles, and configuration.

- **Ban History Tracking**  
  The `ban_history.py` module (and its associated database schema) maintains a record of bans/strikes issued to players, along with metadata (timestamps, moderator IDs, reasons, lengths).

- **Database Integration**  
  - Uses **aiomysql** (async MySQL client) or **PyMySQL** (sync) to connect to a MySQL‐compatible database.  
  - Contains `utils/db_utils.py` to handle connection pooling, query execution, and result parsing.  
  - `utils/config_manager.py`: Loads JSON or other configuration files for dynamic settings.  
  - `utils/permissions_utils.py`: Checks whether a user has one of the configured moderator roles before allowing certain commands.

- **Dynamic UI Components**  
  - `ui/shared_ui.py` defines reusable Discord UI classes (e.g., dropdowns, modals).  
  - Real‐time dropdown menus for selecting offenses, strikes, and transcript links.

- **Environment Configuration**  
  - `.env` support (via `python-dotenv`) for sensitive tokens, DB credentials, and channel IDs.  
  - `config.py` for hard‐coded role names or IDs, default bot prefix, and optional channel IDs for logs/pending bans.

- **Error Handling & Logging**  
  - Gracefully logs exceptions (e.g., missing permissions, database errors) back to Discord or console.  
  - Colorized output (via `colorama`) and tabulated data for debugging and developer convenience.

---

## Prerequisites

1. **Python 3.10 or higher**  
2. **MySQL 5.7+ or MariaDB** (for storing ban/strike records)  
3. **Docker (optional)**  
   - If you wish to run the bot inside a container, refer to the [Docker](#docker‐support) section below.

---

## Installation

1. **Clone this repository**  
   ```bash
   git clone https://github.com/<your‐username>/<repo‐name>.git
   cd <repo-name>
   ```

2. **Create a Python virtual environment (recommended)**  
   ```bash
   python3 -m venv venv
   source venv/bin/activate        # macOS/Linux
   .\venv\Scripts\activate      # Windows
   ```

3. **Install dependencies**  
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Set up your MySQL database**  
   - Create a database (e.g., `discord_moderation_db`).  
   - Execute the provided SQL schema (if available) or manually create tables:  
     ```sql
     CREATE TABLE bans (
       ban_id INT AUTO_INCREMENT PRIMARY KEY,
       player_buid VARCHAR(32) NOT NULL,
       moderator_id BIGINT NOT NULL,
       reason TEXT NOT NULL,
       length_minutes INT NOT NULL,
       timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
     );

     CREATE TABLE strikes (
       strike_id INT AUTO_INCREMENT PRIMARY KEY,
       player_buid VARCHAR(32) NOT NULL,
       moderator_id BIGINT NOT NULL,
       level INT NOT NULL,
       reason TEXT NOT NULL,
       timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
     );

     CREATE TABLE ban_history (
       history_id INT AUTO_INCREMENT PRIMARY KEY,
       player_buid VARCHAR(32) NOT NULL,
       details TEXT NOT NULL,
       timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
     );
     ```  
   - Adjust table names/columns to match any custom `db_utils.py` logic, if needed.

---

## Configuration

1. **Copy `.env.example` to `.env`** (or create a fresh `.env`) with the following keys:  
   ```bash
    # Discord Bot Configuration
      DISCORD_TOKEN=

    # Player/Game Server Database Configuration
     PLAYER_DB_HOST=your-game-server-host.com
     PLAYER_DB_PORT=3306
     PLAYER_DB_USER=your_game_db_username
     PLAYER_DB_PASSWORD=your_game_db_password
      PLAYER_DB_NAME=your_game_database_name

    #Ban Tracking Database Configuration (Sparked Host)
    BAN_DB_HOST=
    BAN_DB_PORT=3306
    BAN_DB_USER=
    BAN_DB_PASSWORD=
    BAN_DB_NAME=

    # Optional: Bot Configuration
    BOT_PREFIX=!
    DEBUG_MODE=False
    LOG_LEVEL=INFO
    MAX_SEARCH_RESULTS=15
    COMMAND_TIMEOUT=300

    # Your new line for the moderation channel
    PENDING_BAN_CHANNEL_ID=
   ```

2. **Edit `config.py`** to match your server’s role names or IDs:  
   ```python
   # config.py

   # Replace with actual role names (case‐sensitive) or Discord Role IDs (as integers)
   MODERATOR_ROLES_CONFIG = ["Moderator", "Admin", 123456789012345678]

   # If you wish to send pending ban requests or logs to specific channels, set these IDs:
   LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", 0))
   PENDING_BAN_CHANNEL_ID = int(os.getenv("PENDING_BAN_CHANNEL_ID", 0))

   # If you want to temporarily support prefix commands:
   BOT_PREFIX = os.getenv("BOT_PREFIX", "!")
   ```

3. **Review `utils/config_manager.py`** to ensure it points to any JSON or YAML configuration files you require (if you decide to store additional settings outside of environment variables).

---

## Running the Bot

Once you have installed dependencies and configured the environment:

```bash
# Activate your virtual environment if not already active:
source venv/bin/activate        # macOS/Linux
.\venv\Scripts\activate      # Windows

# Run the bot:
python main.py
```

- On first run, the bot will attempt to sync slash commands globally (may take a few minutes).  
- Any errors during startup (e.g., missing environment variable, DB connection errors) will be printed to the console with a traceback. Address them before proceeding.

---

## Directory Structure

```
repo‐name/
├── .env                        # Environment variables (gitignored)
├── ban_history.py              # Ban/strike history tracking logic
├── config.py                   # Role/channel configuration
├── main.py                     # Entry point: initializes bot, loads cogs
├── punishments.py              # Defines punishments & strike logic
├── requirements.txt            # Python dependencies

├── cogs/                       # “Cogs” (modules) for modular commands
│   ├── __init__.py
│   ├── admin_cog.py            # Role checks and administrative utilities
│   ├── ban_cog.py              # Ban‐related slash commands & forms
│   ├── history_cog.py          # “/history” slash command to retrieve ban history
│   └── setup_cog.py            # Guild setup commands (e.g., creating channels)

├── ui/                         # Reusable Discord UI components
│   ├── __init__.py
│   └── shared_ui.py            # Dropdowns, modals, and helper classes

└── utils/                      # Utility functions and DB helpers
    ├── __init__.py
    ├── config_manager.py       # Loads additional configuration files (JSON)
    ├── db_utils.py             # Database connection pooling & query execution
    └── permissions_utils.py    # “is_moderator” helper and other permission checks
```

---

## Slash Commands & Usage

Below is a brief overview of the primary slash commands. Exact command names and options may be found in each cog’s source code (`cogs/ban_cog.py`, `cogs/history_cog.py`, etc.).

### `/setup`
- **Purpose**: Creates or configures required channels and roles in the guild (e.g., Pending‐Ban channel).
- **Usage**:  
  ``` 
  /setup 
  ```
- **Behavior**:  
  1. Checks if the user has a configured “Administrator” or “Head Admin” role.  
  2. Creates a “pending‐bans” channel (if not already present).  
  3. Posts an informational embed describing how to use the ban/strike system.

### `/ban`
- **Purpose**: Initiate a ban request for a target player (with optional transcript link and reason).  
- **Options**:  
  - `player_buid`: (String) The unique BUID of the player to ban.  
  - `offense`: (String or dropdown) Reason for ban (must match configured offenses).  
  - `length_minutes`: (Integer) Duration of ban in minutes (0 for indefinite).  
  - `transcript_link`: (String, optional) A link to the evidence/transcript (auto‐extracted if a transcript file is attached).  
- **Usage**:  
  ```
  /ban player_buid: "12345" offense: "Cheating" length_minutes: 1440 transcript_link: "http://..."
  ```
- **Behavior**:  
  1. Verifies the invoking user is in a “moderator” role.  
  2. Presents a confirmation embed (Pending Ban) in the designated channel.  
  3. On moderator & admin approval (via buttons), writes to `ban_history` and logs to the configured log channel.

### `/strike`
- **Purpose**: Issue a strike (warning level) to a user.  
- **Options**:  
  - `player_buid`: (String) The BUID of the player.  
  - `level`: (Integer) Strike level (e.g., 1, 2, 3).  
  - `reason`: (String) Reason for issuing the strike.  
- **Usage**:  
  ```
  /strike player_buid: "12345" level: 2 reason: "Repeated misconduct"
  ```
- **Behavior**:  
  1. Verifies the invoking user is in a “moderator” role.  
  2. Adds a new record to the strikes table via `utils/db_utils.py`.  
  3. Responds with a confirmation embed and optionally logs to a separate channel.

### `/history`
- **Purpose**: Fetch and display all bans and strikes for a given player.  
- **Options**:  
  - `player_buid`: (String) The BUID of the player.  
- **Usage**:  
  ```
  /history player_buid: "12345"
  ```
- **Behavior**:  
  1. Queries `ban_history`, `bans`, and `strikes` tables for all entries related to that BUID.  
  2. Formats results into a Discord embed or paginated view (if many records).  
  3. Sends the embed in the channel where the command was invoked.

---

## Environment Variables

Place these in a file named `.env` at the root of your project (do **not** commit `.env` to GitHub). Make sure to replace placeholders with your actual values:

```dotenv
# Discord Bot Token
DISCORD_TOKEN=your_discord_bot_token_here

# MySQL / MariaDB Database Credentials
PLAYER_DB_HOST=localhost
PLAYER_DB_PORT=3306
PLAYER_DB_USER=your_db_username
PLAYER_DB_PASSWORD=your_db_password
PLAYER_DB_NAME=your_database_name

# Channel IDs (optional—configure in config.py if used)
PENDING_BAN_CHANNEL_ID=123456789012345678
LOG_CHANNEL_ID=123456789012345678

# Bot Prefix (only if you want to enable prefix commands alongside slash commands)
BOT_PREFIX=!
```

---

## Docker Support

If you prefer containerized deployment, use the provided `Dockerfile` (or create one if missing). Below is a sample `Dockerfile` snippet:

```Dockerfile
# Use official Python image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose a port if needed (not strictly necessary for Discord bots)
EXPOSE 8080

# Set environment variables (you can override these at runtime)
ENV DISCORD_TOKEN=${DISCORD_TOKEN}
ENV PLAYER_DB_HOST=${PLAYER_DB_HOST}
ENV PLAYER_DB_PORT=${PLAYER_DB_PORT}
ENV PLAYER_DB_USER=${PLAYER_DB_USER}
ENV PLAYER_DB_PASSWORD=${PLAYER_DB_PASSWORD}
ENV PLAYER_DB_NAME=${PLAYER_DB_NAME}
ENV PENDING_BAN_CHANNEL_ID=${PENDING_BAN_CHANNEL_ID}
ENV LOG_CHANNEL_ID=${LOG_CHANNEL_ID}
ENV BOT_PREFIX=${BOT_PREFIX:-!}

# Run the bot
CMD ["python", "main.py"]
```

1. **Build the image**  
   ```bash
   docker build -t discord-moderation-bot .
   ```

2. **Run the container** (make sure to pass your .env variables)  
   ```bash
   docker run -d --name mod-bot \
     -e DISCORD_TOKEN="${DISCORD_TOKEN}" \
     -e PLAYER_DB_HOST="${PLAYER_DB_HOST}" \
     -e PLAYER_DB_PORT="${PLAYER_DB_PORT}" \
     -e PLAYER_DB_USER="${PLAYER_DB_USER}" \ 
     -e PLAYER_DB_PASSWORD="${PLAYER_DB_PASSWORD}" \ 
     -e PLAYER_DB_NAME="${PLAYER_DB_NAME}" \ 
     -e PENDING_BAN_CHANNEL_ID="${PENDING_BAN_CHANNEL_ID}" \ 
     -e LOG_CHANNEL_ID="${LOG_CHANNEL_ID}" \ 
     discord-moderation-bot
   ```

3. **Optional: Push to Docker Hub**  
   ```bash
   docker tag discord-moderation-bot your-dockerhub-username/discord-moderation-bot:latest
   docker push your-dockerhub-username/discord-moderation-bot:latest
   ```

---

## Contributing

1. **Fork the repository**  
2. **Create a new branch**:  
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** and ensure code style is consistent (`flake8`, `black`, etc.).  
4. **Run tests** (if tests are added) or manually test features in a private Discord server.  
5. **Submit a pull request** describing your changes in detail.

Please follow these guidelines:

- Adhere to existing code style (PEP 8, consistent indentation, clear docstrings).  
- Update `requirements.txt` if you add new dependencies.  
- If you introduce new environment variables, update this README accordingly.  

---

## License

This project is licensed under the [MIT License](LICENSE) (or choose another license as appropriate). Feel free to modify or redistribute under the terms of that license.

---

> _Created by [Your Name](https://github.com/your‐username) • Last updated: June 5, 2025_
