#!/bin/bash

# Set your Ollama API endpoint
OLLAMA_API_ENDPOINT="http://localhost:11434/api/generate"

# Default language for commit message
LANGUAGES="en"
# Default extra notes
EXTRA_NOTES=""

# ANSI color codes
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --lang=*) LANGUAGES="${1#*=}";;
        --notes=*) EXTRA_NOTES="${1#*=}";;
        *) echo "Unknown parameter passed: $1"; exit 1;;
    esac
    shift
done

# Check the status of the working directory
echo "Checking the status of the working directory..."
git status

# Get the difference between the working directory and the staging area
WORKING_DIFF=$(git diff)
# Get the difference between the staging area and HEAD
STAGED_DIFF=$(git diff --cached)

# Combine the differences
DIFF="${WORKING_DIFF}${STAGED_DIFF}"

# If there are no differences, exit
if [ -z "$DIFF" ]; then
    echo "No differences found."
    exit 0
fi

# Call Ollama's API to generate a commit message
generate_commit_message() {
    local LANGUAGES=$1
    local NOTES=$2
    RESPONSE=$(curl -s -X POST "$OLLAMA_API_ENDPOINT" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen2.5:14b",
        "prompt": "Analyze the following code changes and generate a concise Git commit message, providing it in the following languages: '$(echo $LANGUAGES | tr ',' ' ')'. Text only: \n\n'"$DIFF"'\n\n '$(echo $NOTES | tr ',' ' ')' '\n\n",
        "max_tokens": 500,
        "temperature": 0.7
    }')

    if [ $? -ne 0 ]; then
        echo "Error: Ollama API call failed due to network error."
        exit 1
    fi

    if [ -z "$RESPONSE" ]; then
        echo "Error: Ollama API returned an empty response."
        exit 1
    fi
    echo "$RESPONSE" | jq -r '.choices[0].message.content' | sed 's/^"\(.*\)"$/\1/'
}

    # Bug 修复：添加缺少的引号
    echo "$RESPONSE" | jq -r '.choices[0].message.content' | sed 's/^"\(.*\)"$/\1/'
}

# Get the generated commit message
COMMIT_MESSAGE=$(generate_commit_message "$LANGUAGES" "$EXTRA_NOTES")

# If no commit message is generated, exit
if [ -z "$COMMIT_MESSAGE" ]; then
    echo "Unable to generate commit message."
    exit 1
fi

# Add changes to the staging area
git add.

# Commit the changes
git commit -m "$COMMIT_MESSAGE"

echo "Commit complete with message: "
echo " "
echo "$COMMIT_MESSAGE"

