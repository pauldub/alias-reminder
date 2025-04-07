# Alias Reminder Plugin for Oh My Zsh

This Python-powered plugin reminds you when you could have used an alias instead of typing out a full command.

## Features

- 🔍 Intelligently detects when you type a command that has an alias
- 💡 Shows a friendly reminder with the alias you could have used
- 📊 Tracks statistics about which aliases you frequently miss
- 🔄 Suggests new aliases based on your command history
- 🧠 Smart command analysis that properly handles subcommands

## Requirements

- Python 3.x

## Installation

1.  Clone this repository into your Oh My Zsh custom plugins directory (replace `your-github-username/alias-reminder-ohmyzsh` with the actual repository URL if you forked it or if it's hosted elsewhere):

    ```bash
    # Example URL, replace if necessary
    git clone [https://github.com/your-github-username/alias-reminder-ohmyzsh](https://github.com/your-github-username/alias-reminder-ohmyzsh) ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/alias-reminder
    ```

2.  Enable the plugin by adding `alias-reminder` to your plugins array in your `.zshrc`:

    ```zsh
    plugins=(... alias-reminder)
    ```

3.  Restart your shell or reload your configuration: `source "${ZDOTDIR:-$HOME}/.zshrc"`

## Configuration

You can customize the plugin by setting these variables in your `.zshrc` *before* the `plugins=(...)` line:

```zsh
# How long to wait before showing the same reminder again (in seconds)
ALIAS_REMINDER_COOLDOWN=3600   # Default: 1 hour

# Only suggest for commands at least this many characters long
ALIAS_REMINDER_MIN_LENGTH=5    # Default: 5 characters

# Color of the reminder messages
ALIAS_REMINDER_COLOR="yellow"  # Options: red, green, yellow, blue, magenta, cyan

# Whether to show alias names in bold
ALIAS_REMINDER_BOLD=true       # Default: true

# Whether to track statistics about missed aliases
ALIAS_REMINDER_STATS=true      # Default: true
```

## Commands

The plugin provides several useful functions:

-   `alias-reminder-stats`: Show statistics about which aliases you frequently miss.
-   `alias-reminder-reset-stats`: Reset the statistics counter.
-   `alias-reminder-clear-cache`: Clear the reminder cooldown cache (will show all reminders again immediately).
-   `alias-reminder-suggest`: Suggest new aliases based on your command history.

## How It Works

The plugin uses a `preexec` hook in Zsh to capture the command you're about to run. It passes this command to a Python script. The Python script:

1.  Reads your current aliases (exported to a temporary file by the Zsh script).
2.  Parses the command, attempting to isolate the core command and subcommands from flags and arguments.
3.  Checks if the parsed command matches the definition of any existing alias *exactly* or if the typed command *starts with* the definition of an alias.
4.  If a shorter alias is found, it displays a reminder (respecting the configured cooldown period for that specific command/alias).
5.  Optionally logs the missed alias opportunity for statistics.

To avoid being annoying, it won't show the same reminder again until the cooldown period (default 1 hour) has passed for that specific suggestion.

## License

MIT
