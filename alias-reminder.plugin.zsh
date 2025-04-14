#!/usr/bin/env zsh
# alias-reminder.plugin.zsh
# Reminds you when you could have used an alias

# --- Debugging Function ---
# Simple function to log messages to stderr, with timestamps
_alias_reminder_log() {
  if [[ "$ALIAS_REMINDER_DEBUG" = "true" ]]; then
    emulate -L sh # Use sh emulation for simpler string handling
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    print -u2 "$timestamp: alias-reminder: $*"
  fi
}

# --- Check Dependencies ---
if ! command -v python3 >/dev/null; then
  _alias_reminder_log "%F{red}python3 command not found. Please install Python 3. Aborting plugin load.%f"
  return 1
fi

# --- Plugin Directory ---
typeset -g ALIAS_REMINDER_DIR="${${(%):-%x}:A:h}" # Get plugin directory robustly
_alias_reminder_log "Plugin directory: $ALIAS_REMINDER_DIR"

# --- Cache and Config ---
typeset -g ALIAS_REMINDER_CACHE_DIR="${HOME}/.cache/alias-reminder" # Use standard cache location
typeset -g ALIAS_REMINDER_ALIAS_FILE="${ALIAS_REMINDER_CACHE_DIR}/aliases.txt"
typeset -g ALIAS_REMINDER_STATS_FILE="${XDG_STATE_HOME:-$HOME/.local/state}/alias-reminder-stats.csv" # Use standard state location

_alias_reminder_log "Cache directory: $ALIAS_REMINDER_CACHE_DIR"
_alias_reminder_log "Alias file: $ALIAS_REMINDER_ALIAS_FILE"
_alias_reminder_log "Stats file: $ALIAS_REMINDER_STATS_FILE"

# Create directories if they don't exist
mkdir -p "$ALIAS_REMINDER_CACHE_DIR"
mkdir -p "$(dirname "$ALIAS_REMINDER_STATS_FILE")"

# Configuration with default values
: "${ALIAS_REMINDER_COOLDOWN:=3600}"        # Default: don't show the same reminder for 1 hour (in seconds)
: "${ALIAS_REMINDER_MIN_LENGTH:=5}"         # Default: only suggest for commands at least 5 chars long
: "${ALIAS_REMINDER_COLOR:=yellow}"         # Default: show reminders in yellow
: "${ALIAS_REMINDER_BOLD:=true}"            # Default: show alias names in bold
: "${ALIAS_REMINDER_STATS:=true}"           # Default: track stats about missed aliases
# New: Default value for debug mode.  Can be overridden in .zshrc
: "${ALIAS_REMINDER_DEBUG:=false}"

_alias_reminder_log "Cooldown: $ALIAS_REMINDER_COOLDOWN, Min Length: $ALIAS_REMINDER_MIN_LENGTH, Color: $ALIAS_REMINDER_COLOR, Bold: $ALIAS_REMINDER_BOLD, Stats: $ALIAS_REMINDER_STATS, Debug: $ALIAS_REMINDER_DEBUG"

# --- Python Script Path ---
typeset -g ALIAS_REMINDER_PYTHON_SCRIPT="${ALIAS_REMINDER_DIR}/alias_reminder.py"

_alias_reminder_log "Python script: $ALIAS_REMINDER_PYTHON_SCRIPT"

if [[ ! -f "$ALIAS_REMINDER_PYTHON_SCRIPT" ]]; then
  _alias_reminder_log "%F{red}Python script not found at ${ALIAS_REMINDER_PYTHON_SCRIPT}. Aborting plugin load.%f"
  return 1
fi

# --- Core Functions ---

# Function to export aliases to a file that Python can read
# Runs every time, potential bottleneck for large alias lists, but simple.
_alias_reminder_export_aliases() {
  _alias_reminder_log "Exporting aliases..."
  # Create a simple format: "alias_name:alias_definition"
  # Using 'alias -L' gives a more raw output which might be slightly more robust
  # than default 'alias' output, though sed is still needed.
  alias -L | command sed 's/^\([^=]*\)=\(.*\)/\1:\2/' >| "$ALIAS_REMINDER_ALIAS_FILE" \
   || {
     _alias_reminder_log "%F{red}Failed to export aliases.%f"
     return 1 # Explicitly return non-zero on failure
   }
  _alias_reminder_log "Aliases exported."
}

# Function to check for alias suggestions before executing a command
_alias_reminder_preexec() {
  emulate -L sh # Use sh emulation for simpler string handling
  local command="$1" #  First argument to preexec is the command about to be executed.

  # Export aliases to file
  _alias_reminder_export_aliases
  if [[ $? -ne 0 ]]; then
    _alias_reminder_log "%F{red}Failed to export aliases before checking command.%f"
    return # Don't proceed if alias export failed.
  fi

  # Extract the first part of the command (simple heuristic)
  local simple_cmd="${command%% \|*}" # Use \| instead of | because | is special in patterns
  simple_cmd="${simple_cmd%% >*}"
  simple_cmd="${simple_cmd%% <*}"
  simple_cmd="${simple_cmd%% >>*}"
  simple_cmd="${simple_cmd%% 2>*}"
  simple_cmd="${simple_cmd%% &>*}"
  simple_cmd="${simple_cmd%% &&*}"
  simple_cmd="${simple_cmd%% ;*}"
  # Remove leading/trailing whitespace just in case
  simple_cmd="${simple_cmd#"${simple_cmd%%[![:space:]]*}"}"
  simple_cmd="${simple_cmd%"${simple_cmd##*[![:space:]]}"}"

  _alias_reminder_log "Extracted simple command: $simple_cmd"

  # Don't run if the command is empty or internal/fast
  if [[ -z "$simple_cmd" ]] || [[ "$simple_cmd" = "fg" ]] || [[ "$simple_cmd" = "bg" ]]; then
    _alias_reminder_log "Command is empty or internal (fg/bg), skipping. simple_cmd=$simple_cmd"
    return
  fi

  # Call the Python script to check for alias suggestions
  # Pass all relevant configuration variables
  noglob python3 "$ALIAS_REMINDER_PYTHON_SCRIPT" \
    --alias-file "$ALIAS_REMINDER_ALIAS_FILE" \
    --cache-dir "$ALIAS_REMINDER_CACHE_DIR" \
    --stats-file "$ALIAS_REMINDER_STATS_FILE" \
    check "$simple_cmd" \
    --cooldown "$ALIAS_REMINDER_COOLDOWN" \
    --min-length "$ALIAS_REMINDER_MIN_LENGTH" \
    --color "$ALIAS_REMINDER_COLOR" \
    --bold "$ALIAS_REMINDER_BOLD" \
    --stats "$ALIAS_REMINDER_STATS" 
}

# --- Plugin Commands ---

# Function to display alias usage statistics
alias-reminder-stats() {
  _alias_reminder_log "Running alias-reminder-stats"
  noglob python3 "$ALIAS_REMINDER_PYTHON_SCRIPT" \
    --stats-file "$ALIAS_REMINDER_STATS_FILE" \
    stats
}

# Function to reset alias usage statistics
alias-reminder-reset-stats() {
  _alias_reminder_log "Running alias-reminder-reset-stats"
  noglob python3 "$ALIAS_REMINDER_PYTHON_SCRIPT" \
    --stats-file "$ALIAS_REMINDER_STATS_FILE" \
    reset-stats
}

# Function to clear the cache (will show reminders again)
alias-reminder-clear-cache() {
  _alias_reminder_log "Running alias-reminder-clear-cache"
  # Pass alias file path so it's not deleted
  noglob python3 "$ALIAS_REMINDER_PYTHON_SCRIPT" \
    --cache-dir "$ALIAS_REMINDER_CACHE_DIR" \
    --alias-file "$ALIAS_REMINDER_ALIAS_FILE" \
    clear-cache
}

# Function to suggest new aliases based on command history
alias-reminder-suggest() {
  _alias_reminder_log "Running alias-reminder-suggest"
  # Export current aliases first so suggestions don't include existing ones
  _alias_reminder_export_aliases
  if [[ $? -ne 0 ]]; then
    _alias_reminder_log "%F{red}Failed to export aliases before suggesting.%f"
    return 1
  fi
  noglob python3 "$ALIAS_REMINDER_PYTHON_SCRIPT" \
      --alias-file "$ALIAS_REMINDER_ALIAS_FILE" \
      suggest \
      --history-file "${HISTFILE:-$HOME/.zsh_history}"
}

# --- Hook Registration ---\nautoload -Uz add-zsh-hook
add-zsh-hook preexec _alias_reminder_preexec
_alias_reminder_log "Registered preexec hook."

# --- Cleanup (Optional but good practice) ---
#
