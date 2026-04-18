#!/bin/bash

# mhlver - One MHL tool to verify them all
readonly MHLVER_VERSION="1.1"

# Copyright (c) 2026 Luis Gómez Gutiérrez
# Licensed under the MIT License

# Colours used
readonly RED='\033[0;31m'
readonly ORANGE='\033[38;5;208m'
readonly RESET='\033[0m'

function show_help() {
	echo "mhlver v$MHLVER_VERSION. Find and verify source MHL files or directories"
	echo
	echo "Usage: mhlver [options] <path>"
	echo 
	echo "Options:"
	echo "  -d, --datestamp : Preprend datestamp for reporting"
    echo "  -s, --schema    : Validate XML Schema Definition (MHL v1 only)"
    echo "  -v, --verbose   : Verbose"
    echo "  -h, --help      : Show this help message"
	echo "  --version       : Print version"
	exit 0
}

function get_abs_path() {
    local user_path="${1:-.}"
    if [[ -d "$user_path" ]]; then
        (cd "$user_path" && pwd)
    elif [[ -f "$user_path" ]]; then
        echo "$(cd "$(dirname "$user_path")" && pwd)/$(basename "$user_path")"
    else
        echo "$user_path"
    fi
}

function log_success() {
    local msg=$1
    if $datestamp; then
        echo "[$(date '+%Y.%m.%d-%H:%M:%S')] ✅ $msg"
    else
        echo "✅ $msg"
    fi
}

function log_error() {
    local msg=$1
    if $datestamp; then
        echo -e "${RED}[$(date '+%Y.%m.%d-%H:%M:%S')] ❌ $msg${RESET}" >&2
    else
        echo -e "${RED}❌ $msg${RESET}" >&2
    fi
}

function verify_item() {
    local target=$1
    local script_dir
    script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

    # Legacy MHL (MHL 1.0)
    if [[ "$target" != *"/ascmhl/"* ]] && [[ "$(basename "$target")" != *"ascmhl"* ]]; then
        local output
        output=$(python3 "$script_dir/mhl_worker.py" "$target" 2>/dev/null)
        local exit_code=$?

        case $exit_code in
            0)
                log_success "MHL verified: $(basename "$target")"
                ;;
            10) # Non-compliant but Hashes match
                log_success "MHL verified: $(basename "$target")"
                if $schema_strict; then
                    echo -e "   ${ORANGE}└─ MHL file not compliant with XML Schema Definition. ${RESET}Read more: https://mediahashlist.org/download/MediaHashList_v1_1.xsd"
                fi
                ;;
            20) # Malformed / Can't even parse
                echo -e "${RED}Malformed XML: $(basename "$target") cannot be read.${RESET}"
                ;;
            30) # Hash Mismatch (Valid Schema)
                log_error "Verification failed: $(basename "$target")"
                [[ -n "$output" ]] && echo -e "${RED}${output}${RESET}"
                ;;
            40) # Hash Mismatch AND Schema Error
                log_error "Verification failed: $(basename "$target")"
                [[ -n "$output" ]] && echo -e "${RED}${output}${RESET}"
                if $schema_strict; then
                    echo -e "   ${ORANGE}└─ Schema non-compliant${RESET}"
                fi
                ;;
            *)
                echo -e "${RED}System error: $exit_code for $(basename "$target")${RESET}"
                ;;
        esac
    # ASC-MHL (MHL 2.0)
    else
        local grandparent
        grandparent=$(dirname "$(dirname "$target")")
        
        ascmhl-debug verify $verbose_flag "$grandparent"
        if [[ $? -eq 0 ]]; then
            log_success "ASC-MHL verified: $(basename "$grandparent")"
        else
            log_error "Manual verification required for $grandparent"
        fi
    fi
}

# Long-format flags
datestamp=false
verbose_flag=""
schema_strict=false

# Long-format flags
for arg in "$@"; do
    case "$arg" in
        --version) echo "$MHLVER_VERSION"; exit 0 ;;
        --help) show_help ;;
        --schema) schema_strict=true ;;
        --datestamp) datestamp=true ;;
        --verbose) verbose_flag="-v" ;;
    esac
done

# Short-format flags
while getopts "dvsh" option
do
    case $option in
        d) datestamp=true ;;
        v) verbose_flag="-v" ;;
        s) schema_strict=true ;;
        h) show_help ;;
        *) show_help ;;
    esac
done
shift "$((OPTIND-1))"

# Resolve source (Default to current directory)
src=$(get_abs_path "${1:-$(pwd)}")

if [[ ! -e "$src" ]]; then
    log_error "Argument should be a file or directory that exists in the filesystem"
    exit 2
fi

# --- Execution ---

if [ -f "$src" ]; then
    verify_item "$src"
elif [ -d "$src" ]; then
    lastgrandparent=""
    # find command avoids hidden/system files and sorts for consistency
    while read -r f; do
        parent=$(dirname "$f")
        grandparent=$(dirname "$parent")
        
        if [[ "$parent" == *"/ascmhl" ]]; then
            # Avoid redundant checks if multiple .mhl files exist in same ascmhl folder
            if [[ "$grandparent" != "$lastgrandparent" ]]; then
                $datestamp && echo '---'
                verify_item "$f"
                lastgrandparent="$grandparent"
            fi
        else
            $datestamp && echo '---'
            verify_item "$f"
        fi
    done < <(find "${src%/}" -mindepth 1 -type f -iname "*.mhl" ! -iname "._*" | sort)
fi