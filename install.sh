#!/bin/bash

# Define variables
REPO_URL="https://github.com/bqckup/bqckup"
INSTALL_DIR="/usr/bin"
APP_NAME="bqckup"

# Function to print messages
print_message() {
    local message="$1"
    printf "\n##############################################\n"
    printf "\n%s\n" "$message"
    printf "\n##############################################\n"
}

# Clone the repository
if git clone "$REPO_URL"; then
    cd "$APP_NAME" || { echo "Failed to enter directory $APP_NAME"; exit 1; }
else
    echo "Failed to clone repository from $REPO_URL"
    exit 1
fi

# Build and install the application
if make && make install; then
    if mv dist/"$APP_NAME" "$INSTALL_DIR"; then
        bqckup get-information
        print_message "$APP_NAME is installed successfully"
    else
        echo "Failed to move $APP_NAME to $INSTALL_DIR"
        exit 1
    fi
else
    echo "Build or install failed"
    exit 1
fi