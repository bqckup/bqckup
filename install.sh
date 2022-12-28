#!/bin/bash


DOWNLOAD_LINK="https://download.bqckup.com"

# Check the contents of the /etc/os-release file
if [ -f /etc/os-release ]; then
    # Extract the distribution name from the file
    distro=$(grep ^NAME /etc/os-release | cut -d'=' -f2 | sed -e 's/^"//' -e 's/"$//')
    if [ "$distro" = "Ubuntu" ]; then
        apt install sqlite3 wget -y 
    elif [ "$distro" = "CentOS Linux" ]; then
        yum install sqlite wget -y
    else
        echo "Bqckup doesn't support this OS yet"
    fi

# If the /etc/os-release file does not exist, check the contents of the /etc/redhat-release file
elif [ -f /etc/redhat-release ]; then
    yum install sqlite -y
else
    echo "Bqckup doesn't support this OS yet"
fi

wget "$DOWNLOAD_LINK"
sudo chmod +x bqckup
sudo mv bqckup /usr/bin/bqckup