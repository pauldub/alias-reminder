#!/usr/bin/env python3
# alias_reminder.py - Python implementation of alias reminder

import argparse
import datetime
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Regex to parse Zsh history lines (handles standard format)
# : <timestamp>:<duration>;<command>
HISTORY_LINE_REGEX = re.compile(r"^: \d+:\d+;(.*)")

# Regex for characters often problematic in filenames
FILENAME_INVALID_CHARS_REGEX = re.compile(r'[<>:"/\\|?*]')

# Global variable to control debug logging
DEBUG = os.environ.get('ALIAS_REMINDER_DEBUG', 'false').lower() == 'true'

def sanitize_filename(name: str) -> str:
    """Replace invalid filename characters with underscores."""
    return FILENAME_INVALID_CHARS_REGEX.sub("_", name)

def get_all_aliases(alias_file_path: Path) -> Dict[str, str]:
    """Get all aliases defined in the alias file."""
    aliases: Dict[str, str] = {}
    if not alias_file_path.is_file():
        if DEBUG:
            print(f"Debug: Alias file not found: {alias_file_path}", file=sys.stderr)
        return aliases

    try:
        with alias_file_path.open('r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or ':' not in line: # Use '=' as separator check from alias -L
                    if DEBUG:
                        print(f"Debug: Skipping line (no '='): {line}", file=sys.stderr)
                    continue

                # Split at the first equals sign
                parts = line.split(':', 1)
                if len(parts) != 2:
                    if DEBUG:
                        print(f"Debug: Malformed alias line: {line}", file=sys.stderr)
                    continue

                alias_name = parts[0].strip().split('alias ', 1)[1]
                alias_cmd = parts[1].strip()

                # Remove surrounding quotes if present (handle single and double)
                if len(alias_cmd) >= 2:
                    if alias_cmd.startswith("'") and alias_cmd.endswith("'"):
                        alias_cmd = alias_cmd[1:-1]
                        if DEBUG:
                            print(f"Debug: Removed single quotes: {alias_cmd}", file=sys.stderr)
                    elif alias_cmd.startswith('"') and alias_cmd.endswith('"'):
                         alias_cmd = alias_cmd[1:-1]
                         # Basic handling for escaped chars within double quotes if needed
                         # alias_cmd = alias_cmd.encode().decode('unicode_escape') # More complex
                         if DEBUG:
                            print(f"Debug: Removed double quotes: {alias_cmd}", file=sys.stderr)

                if alias_name: # Ensure alias name is not empty
                    aliases[alias_name] = alias_cmd
                    if DEBUG:
                        print(f"Debug: Added alias: {alias_name} -> {alias_cmd}", file=sys.stderr)
                else:
                    if DEBUG:
                        print(f"Debug: Empty alias name in line: {line}", file=sys.stderr)
    except OSError as e:
        print(f"Error reading aliases from {alias_file_path}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error reading aliases: {e}", file=sys.stderr)

    if DEBUG:
        print(f"Debug: Loaded {len(aliases)} aliases.", file=sys.stderr)
    return aliases

def is_likely_flag_or_path(arg: str) -> bool:
    """Check if an argument looks like a flag or file path (heuristic)."""
    # Check if it's a flag (starts with - or --, and isn't just '-')
    if arg.startswith('-') and arg != '-':
        if DEBUG:
            print(f"Debug: {arg} looks like a flag.", file=sys.stderr)
        return True

    # Check if it looks like a path (contains /, ., ~, or starts with $)
    # Improve check for '.' to avoid matching simple words like 'v1.0' as paths unless they also contain '/'
    if '/' in arg or '~' in arg or arg.startswith('$'):
        if DEBUG:
            print(f"Debug: {arg} looks like a path.", file=sys.stderr)
        return True
    if '.' in arg and re.search(r'\.\w{1,5}$', arg) and not arg.startswith('.'): # Common file extensions
        if DEBUG:
            print(f"Debug: {arg} looks like a path (file extension).", file=sys.stderr)
        return True

    if DEBUG:
        print(f"Debug: {arg} is not a flag or path.", file=sys.stderr)
    return False

def extract_command_without_flags(command: str) -> str:
    """
    Extract the command without likely flags or file paths.
    Example: 'git status --verbose file.txt' -> 'git status'
    """
    parts = command.split()
    cmd_parts: List[str] = []

    if not parts:
        if DEBUG:
            print("Debug: Command is empty.", file=sys.stderr)
        return ""

    # Always include the first part (the command itself)
    cmd_parts.append(parts[0])
    if DEBUG:
        print(f"Debug: First command part: {parts[0]}", file=sys.stderr)

    # Add subsequent parts until we hit something that looks like a flag or path
    for part in parts[1:]:
        if is_likely_flag_or_path(part):
            if DEBUG:
                print(f"Debug: Stopping at potential flag/path: {part}", file=sys.stderr)
            break
        cmd_parts.append(part)
        if DEBUG:
            print(f"Debug: Adding command part: {part}", file=sys.stderr)

    extracted_cmd = ' '.join(cmd_parts)
    if DEBUG:
        print(f"Debug: Extracted command: {extracted_cmd}", file=sys.stderr)
    return extracted_cmd

def log_statistic(stats_file: Path, command: str, alias: str):
    """Append a missed alias event to the statistics file."""
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d,%H:%M:%S")
        # Basic CSV escaping (replace comma with semicolon for simplicity here)
        safe_command = command.replace(',', ';')
        safe_alias = alias.replace(',', ';')
        with stats_file.open('a', encoding='utf-8') as f:
            f.write(f"{timestamp},{safe_command},{safe_alias}\n")
        if DEBUG:
            print(f"Debug: Logged statistic: {safe_command}, {safe_alias}", file=sys.stderr)
    except OSError as e:
        print(f"Error writing to stats file {stats_file}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error logging stats: {e}", file=sys.stderr)


def check_cooldown(cache_dir: Path, cache_key: str, cooldown_secs: int) -> bool:
    """
    Check if the cooldown period for a given cache key has passed.
    Returns True if the suggestion SHOULD be shown, False otherwise.
    Updates the cache file timestamp if the suggestion is shown.
    """
    # Sanitize cache_key to be a valid filename component
    safe_cache_key = sanitize_filename(cache_key)
    if not safe_cache_key: # Handle empty result after sanitization
        safe_cache_key = "default_key"

    cache_file = cache_dir / safe_cache_key
    if DEBUG:
        print(f"Debug: Checking cooldown for {cache_file}", file=sys.stderr)

    now = time.time()
    if cache_file.exists():
        try:
            file_mtime = cache_file.stat().st_mtime
            if now - file_mtime < cooldown_secs:
                if DEBUG:
                    print(f"Debug: Cooldown active. Time remaining: {cooldown_secs - (now - file_mtime)}", file=sys.stderr)
                return False  # Cooldown active, don't show
            else:
                if DEBUG:
                    print("Debug: Cooldown expired.", file=sys.stderr)
        except OSError as e:
            print(f"Warning: Could not read cache file timestamp {cache_file}: {e}", file=sys.stderr)
            # Proceed as if cooldown passed to avoid blocking reminders due to FS errors
    else:
        if DEBUG:
            print("Debug: Cache file does not exist.", file=sys.stderr)

    # If cooldown passed or file didn't exist, update timestamp and allow showing
    try:
        # Use touch-like behavior to update mtime or create file
        with cache_file.open('a'):
            os.utime(cache_file, (now, now))
        if DEBUG:
            print("Debug: Cache file updated.", file=sys.stderr)
    except OSError as e:
        print(f"Warning: Could not update cache file {cache_file}: {e}", file=sys.stderr)
        # Still allow showing the reminder

    return True # Cooldown passed or cache updated, show the reminder


def print_suggestion(alias_name: str, alias_cmd: str, typed_cmd: str, color: str, bold: bool, remaining_args: Optional[str] = None):
    """Formats and prints the alias suggestion message."""
    color_codes = {
        'black': '30', 'red': '31', 'green': '32', 'yellow': '33',
        'blue': '34', 'magenta': '35', 'cyan': '36', 'white': '37',
    }
    color_code = color_codes.get(color.lower(), '33') # Default to yellow

    bold_start = "\033[1m" if bold else ""
    bold_end = "\033[22m" if bold else "" # Use 22m to specifically turn off bold
    color_start = f"\033[0;{color_code}m"
    color_reset = "\033[0m"

    if remaining_args is not None:
        # Partial match suggestion
        suggested = f"{alias_name} {remaining_args}".strip()
        original = typed_cmd
        print(f"{color_start}Tip: You could have used '{bold_start}{suggested}{bold_end}{color_start}' instead of '{bold_start}{original}{bold_end}{color_start}'.{color_reset}")
        if DEBUG:
            print(f"Debug: Partial match suggestion: {suggested} instead of {original}", file=sys.stderr)
    else:
        # Exact match suggestion
        suggested = alias_name
        original = alias_cmd # Show the command the alias replaces
        print(f"{color_start}Tip: You could have used the alias '{bold_start}{suggested}{bold_end}{color_start}' instead of '{bold_start}{original}{bold_end}{color_start}'.{color_reset}")
        if DEBUG:
            print(f"Debug: Exact match suggestion: {suggested} instead of {original}", file=sys.stderr)


def check_alias_suggestion(
    command: str,
    cooldown: int,
    min_length: int,
    color: str,
    bold: bool,
    stats_enabled: bool,
    alias_file: Path,
    cache_dir: Path,
    stats_file: Path):
    """Check if a command has an alias and suggest it, handling exact and partial matches."""

    if DEBUG:
        print(f"Debug: Checking command: {command}", file=sys.stderr)
        print(f"Debug: Alias file: {alias_file}, Cache dir: {cache_dir}, Stats file: {stats_file}", file=sys.stderr)

    aliases = get_all_aliases(alias_file)
    if not aliases or not command:
        if DEBUG:
            print("Debug: No aliases or empty command, returning.", file=sys.stderr)
        return

    # 1. Check for exact matches (typed command == alias definition)
    cmd_without_flags = extract_command_without_flags(command)
    if len(cmd_without_flags) < min_length:
        if DEBUG:
            print(f"Debug: Command too short ({len(cmd_without_flags)} < {min_length}), returning.", file=sys.stderr)
        return # Skip if core command is too short

    exact_matches: List[Tuple[str, str]] = []
    for alias_name, alias_cmd in aliases.items():
        if cmd_without_flags == alias_cmd:
            # Only consider if alias is actually shorter than command
            if len(alias_name) < len(alias_cmd):
                exact_matches.append((alias_name, alias_cmd))

    if exact_matches:
        # Sort by length of alias name (shortest wins)
        exact_matches.sort(key=lambda x: len(x[0]))
        best_alias, best_replacement = exact_matches[0]
        # Check cooldown using the *command* as the key
        cache_key = f"exact_{best_replacement}"
        if check_cooldown(cache_dir, cache_key, cooldown):
            print_suggestion(best_alias, best_replacement, command, color, bold)
            if stats_enabled:
                log_statistic(stats_file, best_replacement, best_alias)
            return # Don't check for partial matches if an exact match was suggested
        else:
            if DEBUG:
                print("Debug: Exact match found, but cooldown active.", file=sys.stderr)
    else:
        if DEBUG:
            print("Debug: No exact match found.", file=sys.stderr)

    # 2. Check for partial matches (typed command starts with alias definition + space)
    # Find all potential partial matches
    partial_matches: List[Tuple[str, str, str]] = [] # (alias_name, alias_cmd, remaining_args)
    for alias_name, alias_cmd in aliases.items():
        # Check if command starts with alias_cmd followed by a space, or is exactly alias_cmd
        # This prevents matching 'ls' for alias 'lsf' when user types 'ls'
        if command == alias_cmd or command.startswith(alias_cmd + ' '):
            remaining_args = command[len(alias_cmd):].strip()
            if remaining_args and len(alias_name) < len(alias_cmd):
                partial_matches.append((alias_name, alias_cmd, remaining_args))

    if partial_matches:
        # Sort by the length of the alias, shortest alias first
        partial_matches.sort(key=lambda x: len(x[0]))
        best_alias, best_alias_cmd, best_remaining_args = partial_matches[0]
        cache_key = f"partial_{best_alias_cmd}_{best_remaining_args}" # Include remaining args in key
        if check_cooldown(cache_dir, cache_key, cooldown):
            print_suggestion(best_alias, best_alias_cmd, command, color, bold, best_remaining_args)
            if stats_enabled:
                log_statistic(stats_file, command, best_alias)
        else:
            if DEBUG:
                print("Debug: Partial match found, but cooldown active.", file=sys.stderr)
    else:
        if DEBUG:
            print("Debug: No partial match found.", file=sys.stderr)
    # 3. "Fuzzy" matching (command starts with a *part* of an alias definition) - EXPERIMENTAL
    #   This is more complex and might lead to false positives, so it's disabled for now.
    #   The idea is to find aliases where the *start* of the alias definition
    #   matches the start of the typed command, even if there are extra parts in the alias.
    #   Example:
    #   alias ll='ls -l'
    #   User types: ls -lAh
    #   Match 'll' because 'ls' (from 'ls -l') matches the start of the typed command
    fuzzy_matches = []
    for alias_name, alias_cmd in aliases.items():
        alias_parts = alias_cmd.split()
        if alias_parts and command.startswith(alias_parts[0]):
            remaining_text = command[len(alias_parts[0]):].strip()
            fuzzy_matches.append((alias_name, alias_cmd, remaining_text))

    if fuzzy_matches:
        fuzzy_matches.sort(key=lambda x: len(x[0])) # Shortest alias first
        best_alias, best_alias_cmd, best_remaining_text = fuzzy_matches[0]
        cache_key = f"fuzzy_{best_alias_cmd}_{best_remaining_text}"
        if check_cooldown(cache_dir, cache_key, cooldown):
            print_suggestion(best_alias, best_alias_cmd, command, color, bold, best_remaining_text)
            if stats_enabled:
                log_statistic(stats_file, command, best_alias)
        else:
             if DEBUG:
                print("Debug: Fuzzy match but cooldown active.", file=sys.stderr)

def show_stats(stats_file: Path):
    """Display alias usage statistics from the stats file."""
    if not stats_file.is_file():
        print("No statistics file found.")
        return

    alias_counts: Counter[str] = Counter()
    total_count = 0
    try:
        with stats_file.open('r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 3:
                    total_count += 1
                    alias_name = parts[2]
                    alias_counts[alias_name] += 1
    except OSError as e:
        print(f"Error reading stats file: {e}")
        return

    if total_count == 0:
        print("No alias usage statistics available.")
        return

    print("Alias Usage Statistics:")
    for alias, count in alias_counts.most_common():
        percentage = (count / total_count) * 100
        print(f"  {alias}: {count} times ({percentage:.2f}%)")
    print(f"  Total missed aliases: {total_count}")


def reset_stats(stats_file: Path):
    """Reset alias usage statistics by deleting the stats file."""
    if stats_file.is_file():
        try:
            stats_file.unlink()
            print("Alias usage statistics reset.")
        except OSError as e:
            print(f"Error deleting stats file: {e}")
    else:
        print("No statistics file found to reset.")

def clear_cache(cache_dir: Path, alias_file: Path):
    """Clear the cooldown cache, excluding the aliases file."""
    if not cache_dir.is_dir():
        print("Cache directory does not exist.")
        return

    for item in cache_dir.iterdir():
        if item.is_file() and item != alias_file:
            try:
                item.unlink()
                print(f"Deleted cache file: {item}")
            except OSError as e:
                print(f"Error deleting cache file {item}: {e}")
    print("Cooldown cache cleared.")

def suggest_aliases(alias_file: Path, history_file: Path):
    """Suggest new aliases based on command history (simplified)."""
    if not alias_file.is_file():
        print("Alias file not found.")
        return

    if not history_file.is_file():
        print("History file not found.")
        return

    existing_aliases = get_all_aliases(alias_file)
    command_counts: Counter[str] = Counter()

    try:
        with history_file.open('r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                match = HISTORY_LINE_REGEX.search(line)
                if match:
                    command = match.group(1).strip()
                    command = extract_command_without_flags(command) # Extract base command
                    if command:  # only count non-empty commands
                         command_counts[command] += 1
    except OSError as e:
        print(f"Error reading history file: {e}")
        return

    # Filter commands that appear frequently and are long enough, and are not already aliases
    suggested_commands = {cmd: count for cmd, count in command_counts.items()
                           if count >= 5 and len(cmd) >= 10 and cmd not in existing_aliases} #Example filter

    if not suggested_commands:
        print("No new alias suggestions found.")
        return

    print("Suggested Aliases:")
    for cmd, count in suggested_commands.items():
        # Generate shorter, more concise alias names
        words = cmd.split()
        if len(words) > 1:
            # Create an alias using first letters of each word
            alias_name = ''.join(word[0] for word in words)
            # For commands with common prefixes like git/bundle/docker, use more letters from the second part
            if words[0] in ['git', 'bundle', 'docker', 'gh', 'be']:
                # Use first word + first letter(s) of remaining words
                alias_name = words[0] + ''.join(word[0] for word in words[1:])
                # For very common patterns, make them even shorter
                if words[0] == 'git':
                    alias_name = 'g' + ''.join(word[0] for word in words[1:])
                elif words[0] == 'bundle' and words[1] == 'exec':
                    alias_name = 'be' + (''.join(word[0] for word in words[2:]) if len(words) > 2 else '')
        else:
            # For single-word commands, truncate to a reasonable length
            alias_name = cmd[:8]
            
        # Ensure alias name is valid and not too long
        alias_name = alias_name.replace('-', '').replace(':', '')[:12]  # Max 12 chars for brevity
        print(f"  alias {alias_name}='{cmd}'  # Count: {count}")
    print("Consider adding these to your .zshrc file.")



def main():
    """Main function to parse arguments and call the appropriate functions."""
    global DEBUG

    default_alias_file = Path("~/.config/alias-reminder/aliases.txt").expanduser()
    default_cache_dir = Path("~/.cache/alias-reminder").expanduser()
    default_stats_file = Path("~/.local/state/alias-reminder-stats.csv").expanduser()
    default_histfile = Path("~/.zsh_history").expanduser()

    parser = argparse.ArgumentParser(description="Alias Reminder Plugin for Zsh",
                                     formatter_class=argparse.RawTextHelpFormatter) # Better help formatting
    parser.add_argument('--alias-file', type=Path, default=default_alias_file,
                        help='Path to the alias file ( Colon separated alias name and alias definition).')
    parser.add_argument('--cache-dir', type=Path, default=default_cache_dir,
                        help='Path to the cache directory.')
    parser.add_argument('--stats-file', type=Path, default=default_stats_file,
                        help='Path to the statistics file.')
    parser.add_argument('--debug', action='store_true', help='Enable debug output to stderr') # Added debug argument

    # Subparsers for different actions
    subparsers = parser.add_subparsers(dest='subcommand', help='Subcommand to execute')

    # Subparser for the 'check' command (for preexec hook)
    check_parser = subparsers.add_parser('check', help='Check for alias suggestions for a given command.')
    check_parser.add_argument('typed_command', type=str, help='The command typed by the user.')
    check_parser.add_argument('--cooldown', type=int, default=3600,
                        help='Cooldown time in seconds before showing the same suggestion again.')
    check_parser.add_argument('--min-length', type=int, default=5,
                        help='Minimum length of the command to check for aliases.')
    check_parser.add_argument('--color', type=str, default='yellow',
                        choices=['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white'],
                        help='Color of the suggestion message.')
    check_parser.add_argument('--bold', type=str, default='true', choices=['true', 'false'],
                        help='Whether to display the alias name in bold.')
    check_parser.add_argument('--stats', type=str, default='true', choices=['true', 'false'],
                        help='Whether to track statistics about missed aliases.')
    if DEBUG:
        print("Debug: Added 'check' subparser", file=sys.stderr)

    # Subparser for the 'stats' command
    stats_parser = subparsers.add_parser('stats', help='Show alias usage statistics.')
    if DEBUG:
        print("Debug: Added 'stats' subparser", file=sys.stderr)

    # Subparser for the 'reset-stats' command
    reset_stats_parser = subparsers.add_parser('reset-stats', help='Reset alias usage statistics.')
    if DEBUG:
        print("Debug: Added 'reset-stats' subparser", file=sys.stderr)

    # Subparser for the 'clear-cache' command
    clear_cache_parser = subparsers.add_parser('clear-cache', help='Clear the cooldown cache.')
    if DEBUG:
        print("Debug: Added 'clear-cache' subparser", file=sys.stderr)

    # Subparser for the 'suggest' command
    suggest_parser = subparsers.add_parser('suggest', help='Suggest new aliases based on command history.')
    suggest_parser.add_argument('--history-file', type=Path, default=default_histfile, help='Path to the shell history file.')
    if DEBUG:
        print("Debug: Added 'suggest' subparser", file=sys.stderr)

    args = parser.parse_args()

    if DEBUG:
        print(f"Debug: Parsed arguments: {args}", file=sys.stderr)

    # Convert boolean args from string
    enable_bold = args.bold.lower() == 'true' if hasattr(args, 'bold') else False
    enable_stats = args.stats.lower() =='true' if hasattr(args, 'stats') else False
    if DEBUG:
        print(f"Debug: enable_bold: {enable_bold}, enable_stats: {enable_stats}", file=sys.stderr)

    # Execute the chosen subcommand
    if args.subcommand == 'check':
        check_alias_suggestion(
            args.typed_command,
            args.cooldown,
            args.min_length,
            args.color,
            enable_bold,
            enable_stats,
            args.alias_file,
            args.cache_dir,
            args.stats_file
        )
    elif args.subcommand == 'stats':
        show_stats(args.stats_file)
    elif args.subcommand == 'reset-stats':
        reset_stats(args.stats_file)
    elif args.subcommand == 'clear-cache':
        clear_cache(args.cache_dir, args.alias_file)
    elif args.subcommand == 'suggest':
        suggest_aliases(args.alias_file, args.history_file)
    elif args.debug: #handle the debug argument.
        DEBUG = True
        print("Debug mode enabled via --debug flag", file=sys.stderr)
    else:
        parser.print_help()  # If no subcommand was provided

if __name__ == "__main__":
    main()
