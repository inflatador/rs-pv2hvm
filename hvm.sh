#!/usr/bin/env bash
# hvm.sh, makes OS layer changes needed to convert server to PV-HVM mode
# supported OS: RHEL/CentOS 6, Ubuntu 12/14
# version: 0.0.7a
# Copyright 2018 Brian King
# License: Apache

###############################################################################

# Requires xenstore-read 

if ! [ -x "$(command -v xenstore-read)" ]
    then
    printf "%s\n" "Error! xenstore-read not found in path. Install XenServer tools 
            and try again."
    exit 1
fi

# Determine OS version using Xenstore commands.

os_distro=$(xenstore-read data/os_distro)
os_majorver=$(xenstore-read data/os_majorver)

supported_distro=(ubuntu rhel centos)
supported_rh_vers=6
supported_ubuntu_vers=(12 14)

supported=false

#Bail out if we don't find a supported distro
#FIXME: move into functions

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

printf "%s\n" "Found supported OS ${os_distro} , making needed changes" >> /tmp/conv.log

#Ubuntu requires grub packages to be installed, and grub itself to be installed

if [ ${os_distro} == "ubuntu" ]
    then
    printf %s "Detected Ubuntu. Installing grub and packages" > /tmp/conv.log
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
    #Ensure grub can find the boot partition when in HVM mode
    sed -i s/"(hd0)"/"(hd0,0)"/g /boot/grub/menu.lst
    #Ensure grub can find the console when in HVM mode
    sed -i s/"hvc0/tty0"/g /boot/grub/menu.lst
        
fi

#RHEL/CentOS 6 require changes to grub.conf
if [ ${os_distro} == "centos" ] || [ ${os_distro} == "rhel" ] 
    then
    printf %s "Detected ${os_distro} 6. Changing grub config" >> /tmp/conv.log
    
    #Ensure grub can find the boot partition when in HVM mode
    sed -i s/"(hd0)"/"(hd0,0)"/g /boot/grub/grub.conf
    #Ensure grub can find the console when in HVM mode
    sed -i s/hvc0/tty0/g /boot/grub/grub.conf

fi

#Move the old rc.local files back into place and delete script when complete
#steps are OS-specific due to the divergent rc.local implementations

if [ ${os_distro} == "ubuntu" ]
    then 
    #Personality backs up the file it is replacing, let's move it back
    mv /etc/rc.local.bak.*.* /etc/rc.local 
    #Ubuntu doesn't normally have an /etc/rc.d directory at all
    rm /etc/rc.d/rc.local
    rmdir /etc/rc.d
    printf %s "Cleaning up rc.local files" >> /tmp/conv.log
fi

if [ ${os_distro} == "centos" ] || [ ${os_distro} == "rhel" ] 
    then
    printf %s "Cleaning up rc.local files" >> /tmp/conv.log
    
    #Redhat makes /etc/rc.local a symlink to /etc/rc.d/rc.local
    mv /etc/rc.d/rc.local.bak.*.* /etc/rc.d/rc.local
    if [ $? -ne 0 ]
      then
      printf %s "Problem cleaning up /etc/rc.d/rc.local. Try it manually." >> /tmp/conv.log
    fi
    rm -f /etc/rc.local
    if [ $? -ne 0 ]
      then
      printf %s "Problem cleaning up /etc/rc.local. Try it manually." >> /tmp/conv.log
    fi
    ln -s /etc/rc.d/rc.local /etc/rc.local
fi

exit 0