#!/usr/bin/env bash
# hvm.sh, makes OS layer changes needed to convert server to PV-HVM mode
# supported OS: RHEL/CentOS 6, Ubuntu 12/14
# version: 0.0.1b
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

#Supported OS: CentOS/RHEL6, Debian 7, Ubuntu 12/14
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
    # the ${BASH_SOURCE[${#BASH_SOURCE[@]} - 1]} var prints the name of the script in the logs
    printf "%s\n" "[$(date)] ${BASH_SOURCE[${#BASH_SOURCE[@]} - 1]}: Did not find supported OS/version combo\
    (RHEL/Cent6, Debian 7, or Ubuntu12/14). Exiting." >> /tmp/pv2hvm.log
    exit 1
fi

#Ubuntu requires grub packages to be installed, and grub itself to be installed

if [ ${os_distro} == "ubuntu" ]
    then
    printf "%s\n" "[$(date)] ${BASH_SOURCE[${#BASH_SOURCE[@]} - 1]}: -1 ]} Detected ${os_distro}. Installing grub and packages" >> /tmp/pv2hvm.log
    apt-get update >> /tmp/pv2hvm.log 2>&1
    apt-get install -qqy grub >> /tmp/pv2hvm.log
    /usr/sbin/grub-install /dev/xvda >> /tmp/pv2hvm.log
    if [ $? -ne 0 ]
        then
        printf %s "[$(date)] ${BASH_SOURCE[${#BASH_SOURCE[@]} - 1]} Couldn't run grub-install. let's try again" >> /tmp/pv2hvm.log
        apt-get update >> /tmp/pv2hvm.log 2>&1
        apt-get install -y grub >> /tmp/pv2hvm.log
        /usr/sbin/grub-install /dev/xvda >> /tmp/pv2hvm.log
    fi
    printf "%s\n" "[$(date)] ${BASH_SOURCE[${#BASH_SOURCE[@]} - 1]} Changing grub config" >> /tmp/pv2hvm.log
    #Ensure grub can find the boot partition when in HVM mode
    sed -i s/"(hd0)"/"(hd0,0)"/g /boot/grub/menu.lst
    #Ensure grub can find the console when in HVM mode
    sed -i s/"hvc0"/"tty0"/g /boot/grub/menu.lst
fi

if [ ${os_distro} == "debian" ] 
    then
    printf "%s\n" "[$(date)] ${BASH_SOURCE[${#BASH_SOURCE[@]} - 1]} Detected ${os_distro}. Installing grub and packages" >> /tmp/pv2hvm.log
    apt-get update >> /tmp/pv2hvm.log 2>&1
    apt-get install -qqy grub >> /tmp/pv2hvm.log
    /usr/sbin/grub-install /dev/xvda >> /tmp/pv2hvm.log
    #Ensure grub can find the boot partition when in HVM mode
    sed -i s/"(hd0)"/"(hd0,0)"/g /boot/grub/menu.lst
    #Ensure grub can find the console when in HVM mode
    sed -i s/hvc0/tty0/g /boot/grub/grub.cfg
fi

#RHEL/CentOS 6 require changes to grub. Heredoc is required because
#grub-install script is broken on these OSes.
if [ ${os_distro} == "centos" ] || [ ${os_distro} == "rhel" ] 
    then
    printf "%s\n" "[$(date)] ${BASH_SOURCE[${#BASH_SOURCE[@]} - 1]} Detected ${os_distro} 6. Changing grub config" >> /tmp/pv2hvm.log
    /sbin/grub --batch << EOF 
    device (hd0) /dev/xvda
    root (hd0,0)
    setup (hd0)
    quit
EOF
    printf "%s\n" "[$(date)] ${BASH_SOURCE[${#BASH_SOURCE[@]} - 1]} Changing grub config" >> /tmp/pv2hvm.log
    #Ensure grub can find the boot partition when in HVM mode
    sed -i s/"(hd0)"/"(hd0,0)"/g /boot/grub/grub.conf
    #Ensure grub can find the console when in HVM mode
    sed -i s/hvc0/tty0/g /boot/grub/grub.conf
fi

if [ ${os_distro} == "centos" ] || [ ${os_distro} == "rhel" ] || [ ${os_distro} == "ubuntu" ] 
    then
    printf "%s\n" "[$(date)] ${BASH_SOURCE[${#BASH_SOURCE[@]} - 1]} Removing pv-convert upstart job" >> /tmp/pv2hvm.log
    job_path="/etc/init/pv-convert.conf"
    rm -f /etc/init/pv-convert.conf
    if [ $? -ne 0 ]
        then
        printf "%s\n" "[$(date)] ${BASH_SOURCE[${#BASH_SOURCE[@]} - 1]} Problem removing pv-convert upstart job." >> /tmp/pv2hvm.log
        exit 1
    fi
fi

exit 0
