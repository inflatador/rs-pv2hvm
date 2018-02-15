#!/usr/bin/env bash
# hvm.sh, makes OS layer changes needed to convert server to PV-HVM mode
# supported OS: RHEL/CentOS 6, Ubuntu 12/14
# version: 0.0.8a
# Copyright 2018 Brian King
# License: Apache

###############################################################################


# Requires xenstore-read 

if ! [ -x "$(command -v xenstore-read)" ]
    then
    printf "%s\n" "Error! xenstore-read not found in path. Install xenstore-utils 
            and try again."
    exit 1
fi

# Determine OS version using Xenstore commands.

os_distro=$(xenstore-read data/os_distro)
os_majorver=$(xenstore-read data/os_majorver)

#FIXME: Include Debian 7 

supported_distro=(centos debian rhel ubuntu)
supported_deb_vers=7
supported_rh_vers=6
supported_ubuntu_vers=(12 14)

supported=false

#Bail out if we don't find a supported distro
#FIXME: move into functions

if [ ${os_distro} == "debian" ]
    then
    if [ ${os_majorver} == ${supported_deb_vers} ]
        then
        supported=true
    fi
fi

if [ ${os_distro} == "centos" ] || [ ${os_distro} == "rhel" ] 
    then
    if [ ${os_majorver} == ${supported_rh_vers} ]
        then
        supported=true
    fi
fi

if [ ${os_distro} == "ubuntu" ]
then
    for vers in ${supported_ubuntu_vers[@]}; do
    if [ ${os_majorver} == "${vers}" ]
        then
        supported=true
        
    fi; done
fi


if [ ${supported} == "false" ]
    then
    printf "%s\n" "Did not find supported OS/version combo\
    (RHEL/Cent6 or Ubuntu12/14). Exiting." >> /tmp/conv.log
    exit 1
fi

#Ubuntu requires grub packages to be installed, and grub itself to be installed

if [ ${os_distro} == "ubuntu" ]
    then
    printf "%s\n" "Detected ${os_distro}. Installing grub and packages" >> /tmp/conv.log
    apt-get update >> /tmp/conv.log 2>&1
    apt-get install -qqy grub >> /tmp/conv.log
    /usr/sbin/grub-install /dev/xvda >> /tmp/conv.log
    if [ $? -ne 0 ]
        then
        printf %s "Couldn't run grub-install. let's try again" >> /tmp/conv.log
        apt-get update >> /tmp/conv.log 2>&1
        apt-get install -y grub >> /tmp/conv.log
        /usr/sbin/grub-install /dev/xvda >> /tmp/conv.log
    fi
    printf "%s\n" "Changing grub config" >> /tmp/conv.log
    #Ensure grub can find the boot partition when in HVM mode
    sed -i s/"(hd0)"/"(hd0,0)"/g /boot/grub/menu.lst
    #Ensure grub can find the console when in HVM mode
    sed -i s/"hvc0"/"tty0"/g /boot/grub/menu.lst
fi

if [ ${os_distro} == "debian" ] 
    then
    apt-get update >> /tmp/conv.log 2>&1
    apt-get install -qqy grub >> /tmp/conv.log
    /usr/sbin/grub-install /dev/xvda >> /tmp/conv.log
    #Ensure grub can find the boot partition when in HVM mode
    sed -i s/"(hd0)"/"(hd0,0)"/g /boot/grub/menu.lst
    #Ensure grub can find the console when in HVM mode
    sed -i s/hvc0/tty0/g /boot/grub/grub.cfg
fi

#RHEL/CentOS 6 require changes to grub.conf
if [ ${os_distro} == "centos" ] || [ ${os_distro} == "rhel" ] 
    then
    printf "%s\n" "Detected ${os_distro} 6. Changing grub config" >> /tmp/conv.log
    
    #Ensure grub can find the boot partition when in HVM mode
    sed -i s/"(hd0)"/"(hd0,0)"/g /boot/grub/grub.conf
    #Ensure grub can find the console when in HVM mode
    sed -i s/hvc0/tty0/g /boot/grub/grub.conf
fi

if [ ${os_distro} == "centos" ] || [ ${os_distro} == "rhel" ] 
    then
    printf "%s\n" "Cleaning up root's crontab" >> /tmp/conv.log
    backup_script_path="/var/spool/cron/root.bak*"
    if [ -s ${backup_script_path} ]
        then
        mv /var/spool/cron/root.bak* /var/spool/cron/root
        if [ $? -ne 0 ]
            then
            printf "%s\n" "Problem moving root's old crontab back into place. Try it manually." >> /tmp/conv.log
            exit 1
        fi
    fi
fi

exit 0
