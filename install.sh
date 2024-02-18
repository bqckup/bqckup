#!/bin/bash

DOWNLOAD_LINK="https://downloads.bqckup.com"
LATEST_VERSION=$(curl https://downloads.bqckup.com/latest.txt)
BQCKUP_PATH="/etc/bqckup"
DISTRO=$(lsb_release -is)
DISTRO_VERSION=$(lsb_release -rs)
CONFIG_FILE="https://raw.githubusercontent.com/bqckup/bqckup/1x/bqckup.cnf.example"
green=`tput setaf 2`
reset=`tput sgr0`

if [ "$DISTRO" != "Ubuntu" ]; then
	echo "Currently only running on ubuntu"
	exit 1
fi

if [[ "$DISTRO_VERSION" < "18.04" ]]; then
	echo "Ubuntu 18.04 or higher is required to run Bqckup."
	exit 1
fi

sudo apt-get install sqlite3 curl -y
wget "$DOWNLOAD_LINK/ubuntu/$DISTRO_VERSION/latest.tar.gz" -O "/tmp/bqckup.tar.gz"

tar xvf /tmp/bqckup.tar.gz && \ 
    rm /tmp/bqckup.tar.gz && \
    sudo chmod +x bqckup && \
    mv bqckup /usr/bin && \
    sudo mkdir -p /etc/bqckup && \
    sudo curl -o /etc/bqckup/bqckup.cnf "$CONFIG_FILE"

bqckup get-information

printf "\n##############################################\n"
printf "\nBqckup is installed\n"
printf "\n##############################################\n"
