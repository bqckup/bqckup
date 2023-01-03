#!/bin/bash

DOWNLOAD_LINK="https://downloads.bqckup.com"
BQCKUP_PATH="/etc/bqckup"
DISTRO=$(lsb_release -is)
DISTRO_VERSION=$(lsb_release -rs)
LATEST_VERSION=$(curl -s "$DOWNLOAD_LINK/latest")
CONFIG_FILE="$DOWNLOAD_LINK/bqckup.cnf.example"

if [ "$DISTRO" = "Ubuntu" ]; then
    sudo apt-get install sqlite3
    wget "$DOWNLOAD_LINK/$LATEST_VERSION/bqckup-debian.tar.gz"
    if [[ "$DISTRO_VERSION" < "18.04" ]]; then
        echo "Ubuntu 18.04 or higher is required to run Bqckup."
        exit 1
    fi
fi

if [ "$DISTRO" = "CentOS" ]; then
    sudo yum install sqlite3
    wget "$DOWNLOAD_LINK/$LATEST_VERSION/bqckup-centos.tar.gz"
fi

tar xvf "bqckup-debian.tar.gz"
rm "bqckup-debian.tar.gz"
sudo chmod +x "bqckup"
sudo mv "bqckup" "/usr/bin"
sudo curl -s "$CONFIG_FILE" -o "$BQCKUP_PATH/bqckup.cnf"
