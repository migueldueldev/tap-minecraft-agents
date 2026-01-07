# TAP Minecraft Agents Framework

[![codecov](https://codecov.io/gh/migueldueldev/tap-minecraft-agents/graph/badge.svg?token=LHPRFURFMD)](https://codecov.io/gh/migueldueldev/tap-minecraft-agents)

A Python framework for creating autonomous Minecraft agents using the `mcpi` library. This project enables multiple specialized agents to explore, mine, and build structures collaboratively using a shared workspace.

## Features

- **Multi-Agent System**: Coordinate multiple specialized agents (Explorer, Miner, Builder).
- **Asynchronous Execution**: Built on `asyncio` for concurrent agent operations and responsiveness.
- **Shared Workspace**: A centralized knowledge base allowing agents to share terrain data, inventory and task status.
- **Chat Interface**: Control agents directly through Minecraft in-game chat commands.

## Prerequisites

- Python 3.8+
- Minecraft Pi Edition or a Bukkit/Spigot server with the Raspberry Juice plugin.
  - A comprehensive server setup is provided in the `AdventuresInMinecraft` directory.

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/migueldueldev/tap-minecraft-agents.git
   cd tap-minecraft-agents
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### 1. Start the Minecraft Server
Navigate to the server directory and launch the server script appropriate for your operating system:

**macOS**:
```bash
cd AdventuresInMinecraft/Server
./start.command
```

**Windows**:
```batch
cd AdventuresInMinecraft\Server
start.bat
```

**Linux**:
```bash
cd AdventuresInMinecraft/Server
./start.sh
```

### 2. Run the Agents Framework
Open a new terminal in the project root and execute the main program:

```bash
python MinecraftAgentsFramework/main.py
```

### 3. Interact via Chat
Join the Minecraft server (default IP: `localhost`) and use the chat window (`T`) to issue commands to the agents.

**Help Commands:**
*   `./explorer help` - Show commands list of ExplorerBot.
*   `./miner help` - Show commands list of MinerBot.
*   `./builder help` - Show commands list of BuilderBot.

## Agents Overview

### ExplorerBot
The primary role of ExplorerBot is to survey the environment. It detects the available regions, generates height maps and identifies safe flat surfaces for construction.

### MinerBot
The MinerBot is responsible of minable resources gathering. It implements various strategies (like vertical digging or vein searching) to efficiently collect materials required by the BuilderBot.

### BuilderBot
The BuilderBot is responsible for construction. It reads schematic files from the `schematics` folder and places blocks in the world. It coordinates with the MinerBot to ensure enough resources are available before building.

## Testing

This project uses `pytest` for testing. To run the test suite:

```bash
pytest
```
