#!/bin/bash
# Download script to perform PV to HVM conversion
#this is injected into /etc/rc.local at boot time
wget -qO /tmp/hvm.sh http://e942b029c256ec323134-d1408b968928561823109cb66c47ebcd.r37.cf5.rackcdn.com/hvm.sh
/bin/bash /tmp/hvm.sh