#!/bin/bash

DOWNLOAD_LINK="https://downloads.bqckup.com"
LATEST_VERSION=$(curl https://downloads.bqckup.com/latest.txt)
BQCKUP_PATH="/etc/bqckup"
DISTRO=$(lsb_release -is)
DISTRO_VERSION=$(lsb_release -rs)
CONFIG_FILE="https://raw.githubusercontent.com/bqckup/bqckup/1x/bqckup.cnf.example"
green=`tput setaf 2`
reset=`tput sgr0`

if [ "$DISTRO" = "Ubuntu" ]; then
    sudo apt-get install sqlite3 curl
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
sudo mkdir -p /etc/bqckup
sudo curl -o /etc/bqckup/bqckup.cnf "$CONFIG_FILE"

printf "\n##############################################\n"
printf "\nBqckup is installed\n"
printf "\nRun: ${green}bqckup gui-active${reset} to setup the apps\n"
printf "\n##############################################\n"