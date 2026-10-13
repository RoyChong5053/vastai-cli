# VastAI CLI Tool

A comprehensive tool for managing VastAI instances with both manual and agent-friendly workflows.

## Features

- **Interactive Mode**: Rent instances with guided offer selection
- **Non-Interactive Mode**: Agent-friendly automation with JSON output
- **SSH Verification**: Ensures SSH connectivity before considering instance ready
- **Profile System**: Pre-configured software stacks (ComfyUI, llama.cpp, Ollama)
- **Setup Scripts**: Run custom configuration after instance creation
- **Monitoring & Cleanup**: Track running instances and prevent cost leaks

## Installation

### 系统环境修复与隔离（重要）
由于 `vastai` pip 包可能破坏系统 Python，强烈建议使用隔离环境：

```bash
# 使用 mamba 创建隔离环境（推荐）
mamba create -n vastai python=3.14 -y
mamba activate vastai
pip install vastai pyyaml

# 或使用提供的 environment.yml
mamba env create -f environment.yml
```

### 项目设置
```bash
# Clone the repository
git clone https://github.com/yourusername/vastai-cli-tool.git
cd vastai-cli-tool

# 使用包装脚本运行（自动激活环境）
./run.sh --help
```

## 使用方法
所有命令都应通过 `run.sh` 脚本运行，以确保使用正确的隔离环境：

```bash
# 显示帮助
./run.sh --help

# 交互模式
./run.sh

# 非交互模式（示例）
./run.sh --non-interactive --offer-id 123456 --no-confirm --no-monitor --output-format json
```

## Usage

### Interactive Mode (Default)

```bash
python3 main.py
```

Follow the prompts to select an offer and create an instance.

### Non-Interactive Mode (for Agents)

```bash
# Specify exact offer ID
python3 main.py --non-interactive --offer-id 123456 --no-confirm --no-monitor --output-format json

# Use criteria to auto-select best offer
python3 main.py --non-interactive --criteria '{"max_price_per_hour": 1.5, "gpu_name": "RTX 4090"}' --no-confirm --output-format json

# Run a setup script after creation
python3 main.py --non-interactive --criteria '{"max_price_per_hour": 2.0}' --setup-script ./ollama-setup.sh --no-confirm --output-format json
```

### Profiles

Use predefined configuration profiles:

```bash
# Use ComfyUI profile (default)
python3 main.py --profile comfyui

# Use llama.cpp profile
python3 main.py --profile llama-cpp

# Use Ollama profile
python3 main.py --profile ollama

# Use base profile for custom setup
python3 main.py --profile base
```

### Configuration Profiles

Profiles are stored in the `profiles/` directory:

- `base.yaml`: Minimal Ubuntu base
- `comfyui.yaml`: ComfyUI with automatic provisioning
- `llama-cpp.yaml`: Ubuntu with llama.cpp built from source
- `ollama.yaml`: Ubuntu with Ollama installed (see setup script)

To create a custom profile, copy an existing YAML file and modify it.

## Agent Integration Examples

See the `examples/` directory for complete agent workflows:

- `agent_comfyui.py`: Rents instance, verifies ComfyUI API, runs inference
- `agent_llama.py`: Sets up llama.cpp server, generates text
- `agent_ollama.py`: Uses Ollama setup script, pulls model, queries API
- `agent_cleanup.py`: Finds and destroys costly instances

## SSH Verification

The tool now verifies SSH connectivity before considering an instance fully ready. This prevents the "waiting instance" state where the instance appears running but SSH daemon hasn't started yet.

## Monitoring

The tool includes instance monitoring and cleanup features to prevent accidentally leaving instances running and incurring charges.

## License

MIT


## Quick Start

### 1. Installation

```bash
# Install VastAI CLI
pip install vastai

# Clone or copy the project
cp -r vastai-v2.1 vastai-v2.2
cd vastai-v2.2

# Set up your API key
vastai set api-key YOUR_API_KEY
```

### 2. Basic Usage

#### Main Instance Manager
```bash
python main.py
```

This will:
1. Fetch the latest VastAI offers
2. Filter them based on your criteria
3. Let you select an instance
4. Create the instance
5. Monitor it until it's ready
6. Provide cleanup options on exit

#### SSH Connection
```bash
python ssh_vastai.py
```

This will:
1. Load instance information from `instances.json`
2. Copy your SSH key to the instance (optional)
3. Connect to the instance with proper port forwarding

## Configuration

Edit `config.py` to customize the behavior:

### Basic Settings
```python
# Price filtering
MAX_PRICE_PER_HOUR = 5.0  # $ per hour
MIN_DISK_SIZE = 10        # GB
MAX_INTERNET_DOWN_COST_PER_TB = 5.0  # $ per TB download
MAX_INTERNET_UP_COST_PER_TB = 5.0    # $ per TB upload

# Default instance settings
DEFAULT_IMAGE = "vastai/comfy:cuda-12.9-auto"
DEFAULT_DISK_SIZE = 32
```

### Enhanced Settings (v2.2)
```python
# Retry settings
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # seconds

# Instance monitoring settings
MONITOR_INTERVAL = 30  # seconds
PING_TIMEOUT = 5  # seconds for ping checks

# SSH connection settings
SSH_TIMEOUT = 30  # seconds
SSH_RETRIES = 3

# Cleanup settings
AUTO_CLEANUP_ON_ERROR = True
CONFIRM_DESTROY_ON_EXIT = True

# Debug settings
DEBUG_MODE = False
VERBOSE_LOGGING = False
```

## Command Line Usage

### Main Instance Manager

```bash
python main.py
```

**Interactive Flow:**
1. **Fetch Offers**: Automatically fetches and filters VastAI offers
2. **Select Instance**: Choose from available offers with detailed information
3. **Confirm Creation**: Review instance details before creation
4. **Create Instance**: Instance creation with progress monitoring
5. **Monitor Status**: Real-time monitoring until instance is ready
6. **Cleanup**: Automatic cleanup check on exit

### SSH Connection

```bash
python ssh_vastai.py
```

**Interactive Flow:**
1. **Load Instance Info**: Automatically loads from `instances.json`
2. **Display Info**: Shows current instance status and connection details
3. **SSH Key Setup**: Optional SSH key copying to the instance
4. **Connect**: Establishes SSH connection with port forwarding

## Environment Support

The tool automatically detects and adapts to different environments:

### Hyprland + Kitty
- **Detection**: Automatically detected
- **SSH Command**: Uses `TERM=xterm-256color` for optimal compatibility
- **Features**: Full color support and enhanced terminal features

### Termux (Android)
- **Detection**: Automatically detected via environment variables
- **SSH Command**: Optimized for Android terminal
- **Features**: Mobile-friendly terminal settings

### Standard Terminals
- **Detection**: Default fallback
- **SSH Command**: Uses `TERM=xterm` for broad compatibility
- **Features**: Works with most common terminals

### Graphical Terminals
- **Detection**: Detected via TTY type
- **SSH Command**: Enhanced terminal settings
- **Features**: Better color and display support

## Error Handling

### Common Issues and Solutions

#### VastAI CLI Not Found
```bash
# Install VastAI CLI
pip install vastai

# Or follow instructions at https://vast.ai/docs/cli
```

#### API Key Issues
```bash
# Set your API key
vastai set api-key YOUR_API_KEY

# Verify it's set
vastai show api-keys
```

#### SSH Connection Fails
```bash
# Check instance status
vastai show instances

# Verify SSH key is set up
vastai show ssh-keys

# Check network connectivity
ping INSTANCE_IP
```

#### Instance Creation Fails
```bash
# Check budget
vastai show user

# Check instance requirements
# - Ensure sufficient budget
# - Check instance availability
# - Verify image exists
```

### Debug Mode

Enable debug mode for detailed troubleshooting:

```python
# In config.py
DEBUG_MODE = True
VERBOSE_LOGGING = True
```

This will:
- Enable detailed logging
- Show all CLI commands and responses
- Provide step-by-step execution details

## Advanced Usage

### Custom Instance Selection

You can modify the price filtering criteria in `config.py`:

```python
# More restrictive filtering
MAX_PRICE_PER_HOUR = 3.0  # Lower price limit
MIN_DISK_SIZE = 50        # More disk space
MAX_INTERNET_DOWN_COST_PER_TB = 2.0  # Lower internet costs
```

### Custom Environment Variables

Add custom environment variables for your instances:

```python
# In config.py
DEFAULT_ENV_VARS = [
    "-p 1111:1111",
    "-p 8080:8080",
    # Add your custom variables
    "-e CUSTOM_VAR=value",
    "-v /host/path:/container/path",
]
```

### Custom Docker Image

Use a different Docker image:

```python
# In config.py
DEFAULT_IMAGE = "your-custom-image:tag"
```

## Monitoring and Management

### Instance Status

Check instance status manually:
```bash
vastai show instances
vastai show instance INSTANCE_ID
```

### Instance Logs

Get instance logs:
```bash
vastai logs INSTANCE_ID
```

### Destroy Instance

Manually destroy an instance:
```bash
vastai destroy instance INSTANCE_ID
```

## File Structure

```
vastai-v2.2/
├── main.py              # Main instance manager
├── ssh_vastai.py        # SSH connection utility
├── instances_manager.py # Core instance management
├── price_checker.py     # Price fetching and filtering
├── config.py           # Configuration settings
├── utils.py            # Utility functions
├── instances.json      # Instance information (auto-created)
├── price-list.json     # Price data (auto-created)
├── vastai.log          # Main application logs
├── ssh_vastai.log      # SSH connection logs
├── README.md           # Project documentation
├── CHANGELOG.md        # Version history
└── USAGE.md           # This file
```

## Troubleshooting

### Logs

Check the log files for detailed error information:
- `vastai.log` - Main application logs
- `ssh_vastai.log` - SSH connection logs

### Common Error Messages

#### "No offers available"
- **Cause**: No instances meet your criteria
- **Solution**: Adjust filtering criteria in `config.py`

#### "Instance creation failed"
- **Cause**: Budget, quota, or image issues
- **Solution**: Check budget, increase quota, verify image

#### "SSH connection failed"
- **Cause**: Network issues or instance not ready
- **Solution**: Wait for instance to be ready, check network

#### "No instance ID found"
- **Cause**: Instance creation succeeded but ID extraction failed
- **Solution**: Check instance manually with `vastai show instances`

### Getting Help

1. **Check Logs**: Review log files for detailed error information
2. **Enable Debug Mode**: Set `DEBUG_MODE = True` in `config.py`
3. **Manual Verification**: Use VastAI CLI commands to verify manually
4. **Documentation**: Review this usage guide and README
5. **VastAI Documentation**: Visit https://vast.ai/docs

## Best Practices

### Security
- Never commit API keys to version control
- Use SSH keys for authentication
- Regularly rotate API keys
- Monitor instance usage and costs

### Cost Management
- Set appropriate price limits
- Monitor running instances
- Use cleanup features
- Set budgets in VastAI console

### Performance
- Choose appropriate instance types
- Use SSD storage when possible
- Monitor network performance
- Use direct connections when available

### Reliability
- Enable retry logic for critical operations
- Monitor instance health
- Have backup plans for critical workloads
- Test SSH connections regularly


## Overview
This project aims to be a versatile tool for managing VastAI instances, usable both manually by the user and automatically by AI agents. The current version provides core instance rental and SSH connection functionality. Future development will focus on:
1. Enhanced agent-friendliness (non-interactive mode, scripting capabilities)
2. Flexible software provisioning (ComfyUI, llama.cpp, ollama, etc.)
3. Improved modularity and error handling
4. Better integration with agent workflows

## Current State
- Manual instance rental with interactive offer selection
- SSH connection with environment detection (Hyprland+Kitty, Termux, etc.)
- Automatic ComfyUI provisioning via the `vastai/comfy` image
- Basic monitoring and cleanup features
- SSH verification during instance startup to prevent hanging on waiting state
- Profile-based configuration system (base, comfyui, llama-cpp profiles)
- Non-interactive mode with agent-friendly command-line arguments (--non-interactive, --offer-id, --criteria, etc.)
- Example Ollama setup script for agent workflows
- SSH key propagation delay fix to prevent permission denied errors

## Planned Enhancements

### 1. Agent-Friendly Non-Interactive Mode
**Goal:** Enable full automation for AI agents to rent and configure instances without user input.

**Tasks:**
- [ ] Add command-line arguments to `main.py` for:
  - `--non-interactive`: Skip all interactive prompts
  - `--offer-id <ID>`: Specify exact offer to use (bypassing selection)
  - `--criteria <JSON>`: JSON string of offer criteria (GPU type, max price, etc.)
  - `--no-confirm`: Skip instance creation confirmation
  - `--no-monitor`: Skip post-creation monitoring
  - `--timeout <SECONDS>`: Custom timeout for instance readiness
  - `--profile <name>`: Use predefined configuration profile (comfyui, llama.cpp, ollama, etc.)
  - `--output-format <json|text>`: Output machine-readable information for agent consumption
- [ ] Modify offer selection logic to automatically choose the best offer based on criteria when in non-interactive mode
- [ ] Add a machine-readable JSON output mode that provides:
  - Instance ID
  - Connection details (IP, SSH port, forwarded ports)
  - Service URLs (ComfyUI, Jupyter, etc.)
  - Status and any errors
- [ ] Ensure all functions in `main.py` can be imported and used as modules by other Python scripts (agents)

### 2. Flexible Software Provisioning Profiles
**Goal:** Support easy switching between different software stacks (ComfyUI, llama.cpp, ollama, custom) without code changes.

**Tasks:**
- [ ] Create a `profiles/` directory containing YAML/JSON configuration files for different software stacks
- [ ] Define initial profiles:
  - `comfyui.yaml`: Current ComfyUI setup (using `vastai/comfy` image)
  - `llama-cpp.yaml`: Profile for llama.cpp server (using appropriate image, e.g., `zanllp/llama.cpp` or similar)
  - `ollama.yaml`: Profile for Ollama service
  - `base.yaml`: Minimal base profile for custom installations
- [ ] Modify `config.py` to load profiles and override default settings (image, onstart command, environment variables)
- [ ] Add command-line argument `--profile` to select a provisioning profile
- [ ] Allow overriding profile settings via command line (e.g., `--image`, `--disk`, `--onstart-cmd`)
- [ ] Document how to create custom profiles

### 3. Post-Creation Agent Actions
**Goal:** Provide agents with ways to verify setup and run initial configuration tasks after instance creation.

**Tasks:**
- [ ] Add an optional `--setup-script <path|URL>` argument to `main.py` that:
  - Downloads (if URL) or reads a script
  - Executes it via SSH on the newly created instance
  - Returns success/failure status to the agent
- [ ] Implement a simple SSH execution utility (non-interactive) that can:
  - Run a single command and return output
  - Upload/download files
  - Execute a script with environment variables
- [ ] Add a `--wait-for-service <URL> [--timeout <SECONDS>]` option that polls a service URL until it's available or times out
- [ ] Create example setup scripts for:
  - Verifying ComfyUI API is responsive
  - Initializing a llama.cpp model
  - Pulling an Ollama model

### 4. Enhanced SSH Utilities for Agents
**Goal:** Make SSH connection more usable in automated scenarios (non-interactive command execution).

**Tasks:**
- [ ] Add a new mode to `ssh_vastai.py` (or create a separate utility) for:
  - `--command "<shell command>"`: Execute a command and exit
  - `--script <path>`: Upload and execute a script
  - `--upload <local>:<remote>`: Upload a file
  - `--download <remote>:<local>`: Download a file
  - `--port-forward <local>:<remote>`: Set up port forwarding and keep alive (for agent use)
- [ ] Ensure SSH utilities can be used without taking over the terminal (no `execvp` that blocks)
- [ ] Add proper error handling and timeout mechanisms for SSH operations
- [ ] Support SSH key agent forwarding for secure connections to internal services

### 5. Improved Error Handling and Recovery
**Goal:** Make the tool more robust for unattended agent operation.

**Tasks:**
- [ ] Add retry mechanisms with exponential backoff for transient failures (API calls, SSH connections)
- [ ] Implement better distinction between fatal errors and recoverable issues
- [ ] Add more detailed error codes and machine-readable error reporting
- [ ] Implement instance state recovery (e.g., if creation fails partially, clean up resources)
- [ ] Add health checks for critical operations (e.g., verify SSH key was actually added)

### 6. Configuration and Usability Improvements
**Goal:** Make the tool easier to configure and extend.

**Tasks:**
- [ ] Split `config.py` into multiple modules: `constants.py`, `profiles.py`, `environment.py`
- [ ] Add support for user configuration files (e.g., `~/.vastai_cli/config.yaml`) to override defaults
- [ ] Implement configuration validation with helpful error messages
- [ ] Add `--init-config` command to generate a sample user configuration file
- [ ] Improve documentation in `USAGE.md` with examples for both manual and agent use
- [ ] Add type hints throughout the codebase for better maintainability

### 7. Testing and Reliability
**Goal:** Ensure the tool works reliably across different environments and scenarios.

**Tasks:**
- [ ] Create a comprehensive test suite (unit and integration tests)
- [ ] Add automated tests for:
  - Offer filtering and selection logic
  - Instance creation and destruction flows
  - SSH connection and command execution
  - Profile loading and application
- [ ] Set up continuous integration (GitHub Actions) to test on multiple Python versions
- [ ] Add manual testing scenarios for different terminal environments (Hyprland, Termux, standard terminals)

### 8. Agent Integration Examples
**Goal:** Provide clear examples of how agents can use this tool.

**Tasks:**
- [ ] Create example agent scripts in `examples/` directory:
  - `agent_comfyui.py`: Rents instance, verifies ComfyUI API, runs a inference task
  - `agent_llama.py`: Rents instance, sets up llama.cpp server, generates text
  - `agent_ollama.py`: Rents instance, pulls model, queries Ollama API
  - `agent_cleanup.py`: Finds and destroys costly instances left running
- [ ] Document the agent usage pattern in `README.md` with code snippets
- [ ] Create a simple HTTP API wrapper (optional) that exposes instance management as REST endpoints for agents

## Non-Goals (for now)
- Graphical user interface
- Multi-cloud support (focus on VastAI only)
- Advanced orchestration (Kubernetes, Docker Swarm) - this tool is for single instance management

## Open Questions
1. Should we maintain backward compatibility with the current interactive-only behavior? (Yes, we'll keep it as default)
2. How should we handle authentication for agent use? (Rely on existing `vastai set api-key` setup)
3. What's the best way to distribute profiles? (Initially in the repo, later possibly from a central registry)
4. Should we add support for installing NVIDIA drivers or other system-level components? (Probably not, rely on VastAI images)

## Next Steps
1. Create the `todo.md` file (this document)
2. Implement the non-interactive mode and command-line arguments in `main.py`
3. Create the profiles system and initial profiles
4. Test the new agent mode with simple scenarios
5. Iterate based on feedback

## Notes for Development
- All changes should maintain the existing manual workflow as the default behavior
- Add comprehensive logging for debugging agent interactions
- Ensure that any new command-line arguments have sensible defaults
- Update `USAGE.md` and `README.md` as features are implemented
- Consider using a configuration library (like `pydantic`) for profile management in the future