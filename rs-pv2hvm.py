#!/usr/bin/env python
# rc-pv2hvm, a script that converts Rackspace Cloud Servers from PV to HVM mode
# version: 0.0.2a
# Copyright 2018 Brian King
# License: Apache

import argparse
import base64
from collections import defaultdict
import datetime
from getpass import getpass
import json
import keyring
import os
import plac
import re
import requests
import sys
import time
import uuid


def getset_keyring_credentials(username=None, password=None):
    """Method to retrieve credentials from keyring."""
    username = keyring.get_password("raxcloud", "username")
    if username is None:
        if sys.version_info.major < 3:
            username = raw_input("Enter Rackspace Username: ")
            keyring.set_password("raxcloud", 'username', username)
            print ("Username value saved in keychain as raxcloud username.")
        elif creds == "username":
            username = input("Enter Rackspace Username: ")
            keyring.set_password("raxcloud", 'username', username)
            print ("Username value saved in keychain as raxcloud username.")
    else:
        print ("Authenticating to Rackspace cloud as %s" % username)
    password = keyring.get_password("raxcloud", "password")
    if password is None:
        password = getpass("Enter Rackspace API key:")
        keyring.set_password("raxcloud", 'password' , password)
        print ("API key value saved in keychain as raxcloud password.")
    return username, password

def wipe_keyring_credentials(username, password):
    """Wipe credentials from keyring."""
    try:
        keyring.delete_password('raxcloud', 'username')
        keyring.delete_password('raxcloud', 'password')
    except:
        pass

    return True

# Request to authenticate using password
def get_auth_token(username,password):
    #setting up api call
    url = "https://identity.api.rackspacecloud.com/v2.0/tokens"
    headers = {'Content-type': 'application/json'}
    payload = {'auth':{'passwordCredentials':{'username': username,'password': password}}}
    payload2 = {'auth':{'RAX-KSKEY:apiKeyCredentials':{'username': username,'apiKey': password}}}

    #authenticating against the identity
    try:
        r = requests.post(url, headers=headers, json=payload)
    except requests.ConnectionError as e:
        print("Connection Error: Check your interwebs!")
        sys.exit()


    if r.status_code != 200:
        r = requests.post(url, headers=headers, json=payload2)
        if r.status_code != 200:
            print ("Error! API responds with %d" % r.status_code)
            print("Rerun the script and you will be prompted to re-enter username/password.")
            wipe_keyring_credentials(username, password)
            sys.exit()
        else:
            print("Authentication was successful!")
    elif r.status_code == 200:
        print("Authentication was successful!")

    #loads json reponse into data as a dictionary.
    data = r.json()
    #assign token and account variables with info from json response.
    auth_token = data["access"]["token"]["id"]
    return auth_token

def find_endpoints(auth_token):
    #init Cloud Servers endpoints as an empty list
    glance_endpoints=[]
    cs_endpoints=[]
    #setting up api call
    url = ("https://identity.api.rackspacecloud.com/v2.0/tokens/%s/endpoints" % auth_token)
    headers = {'content-type': 'application/json', 'Accept': 'application/json',
               'X-Auth-Token': auth_token}
    raw_service_catalog = requests.get(url, headers=headers)
    the_service_catalog = raw_service_catalog.json()
    endpoints = the_service_catalog["endpoints"]
    for service in range(len(endpoints)):
        if "cloudImages" == endpoints[service]["name"]:
            glance_endpoints.append(endpoints[service]["publicURL"])
        if "cloudServersOpenStack" == endpoints[service]["name"]:
            cs_endpoints.append(endpoints[service]["publicURL"])
    return glance_endpoints, cs_endpoints, headers

def find_glance_image_and_cs_endpoint(auth_token, headers, cs_endpoints, glance_endpoints, glance_image):
    print ("Determining which region your cloud server image is in...")
    for endpoint in range(len(glance_endpoints)):
        potential_url = ( "%s/images/%s" % (glance_endpoints[endpoint], glance_image) )
        potential_image = requests.get(url=potential_url, headers=headers)
        if potential_image.status_code == 200:
            glance_object = potential_image
            region = potential_url.split('//')[1].split('.')[0]
            print ("Found image %s in %s region" % (glance_image, region))
            break
    for endpoint in cs_endpoints:
        if region in endpoint:
            cs_endpoint = endpoint
            print cs_endpoint
    return glance_object, cs_endpoint, region

    #if we make it this far, the glance image UUID is invalid
    print ("Error! Rackspace Cloud Server Image UUID %s was not found." % (glance_image) )
    sys.exit()

def check_glance_image(auth_token, headers, glance_image, glance_object):
    # sanity checks
    print ("Verifying image status...")
    glance_image_type = (glance_object.json()["image_type"])
    # will not try to convert base image
    if glance_image_type != "snapshot":
        print ("Error! I won't convert a base image.")
        sys.exit(status=None)
    glance_status = (glance_object.json()["status"])
    if glance_status != "active":
        print ("Error! Wrong status for glance image %s. Expected 'active' ,\
        but found '%s'" % (glance_image, glance_status))
        sys.exit()
    # vm_mode is not always set. Without it, servers will build in PV mode.
    if "vm_mode" not in glance_object.json():
        glance_object.json()["vm_mode"] = ""
    else:
        image_vm_mode = glance_object.json()["vm_mode"]
        if image_vm_mode == "hvm":
            print(
            "Error! Image vm_mode already set to HVM, conversion not needed."
            )
            sys.exit()
    # Confirm the OS is supported
    image_os = (glance_object.json()["org.openstack__1__os_distro"])
    image_version = (glance_object.json()["org.openstack__1__os_version"])
    supported_os =('centos', 'redhat', 'ubuntu')
    supported = False
    for os in supported_os:
        if os in image_os:
            #Check RHEL/CentOS version. We don't do this with Ubuntu because
            # release upgrades make this value unreliable
            if image_os == 'com.redhat' or 'org.centos':
                if "6." in image_version:
                    supported = True
                else:
                    supported = False
            supported = True
    print (supported)
    if supported == False:
        print("Error! Image built from unsupported OS! Exiting.")
        sys.exit()

def determine_server_flavor(auth_token, headers, glance_image, glance_object):
    # for speed's sake, we will build General Purpose servers if possible
    min_disk = (glance_object.json()["min_disk"])
    if min_disk <= 160:
        disk_multiplier = 20
        flavor_type = "general"
        if (min_disk % disk_multiplier) != 0:
            print ("Error! min_disk value should be a multiple of 20.")
            sys.exit()
        flavor_memory = str(min_disk / disk_multiplier)
        flavor = flavor_type + "1-" + flavor_memory
        return flavor
    elif min_disk == 320:
        flavor = 6
        return flavor
    elif min_disk == 620:
        flavor = 7
        return flavor
    elif min_disk == 1200:
        flavor = 8
        return flavor
    print ("Error! Could not determine flavor to use.")
    sys.exit()

def build_server(auth_token, headers, cs_endpoint, glance_image, glance_object, flavor):
    print (cs_endpoint)
#The script to inject at boot time. Personality is really small, so we
#must call out to another script to complete our conversion.
dl_script='''
#!/usr/bin/env bash
# Download script to perform PV to HVM conversion
#this is injected into /etc/rc.local at boot time
wget -qO /tmp/hvm.sh http://e942b029c256ec323134-d1408b968928561823109cb66c47ebcd.r37.cf5.rackcdn.com/hvm.sh
/usr/bin/env bash /tmp/hvm.sh
#Only used for troubleshooting, does not need to be in final script
ssh-keygen -A
'''
personality = base64.b64encode(dl_script)
print (personality)
# '{"server": {"name": "bking-d6-conv01", "imageRef": "23e4e7cb-5900-4544-a06c-338658dd8802", "key_name": "rackesc", "flavorRef": "performance1-1", "max_count": 1, "min_count": 1, "networks": [{"uuid": "29b682af-0ef3-4ba8-83c6-8e2ea8e6d7ee"}, {"uuid": "00000000-0000-0000-0000-000000000000"}, {"uuid": "11111111-1111-1111-1111-111111111111"}], "personality": [{"path": "/etc/rc.d/rc.local", "contents": "IyEvdXNyL2Jpbi9lbnYgYmFzaAojIERvd25sb2FkIHNjcmlwdCB0byBwZXJmb3JtIFBWIHRvIEhWTSBjb252ZXJzaW9uCiN0aGlzIGlzIGluamVjdGVkIGludG8gL2V0Yy9yYy5sb2NhbCBhdCBib290IHRpbWUKd2dldCAtcU8gL3RtcC9odm0uc2ggaHR0cDovL2U5NDJiMDI5YzI1NmVjMzIzMTM0LWQxNDA4Yjk2ODkyODU2MTgyMzEwOWNiNjZjNDdlYmNkLnIzNy5jZjUucmFja2Nkbi5jb20vaHZtLnNoCi91c3IvYmluL2VudiBiYXNoIC90bXAvaHZtLnNoCiNPbmx5IHVzZWQgZm9yIHRyb3VibGVzaG9vdGluZywgZG9lcyBub3QgbmVlZCB0byBiZSBpbiBmaW5hbCBzY3JpcHQKc3NoLWtleWdlbiAtQQ=="}, {"path": "/etc/rc.local", "contents": "IyEvdXNyL2Jpbi9lbnYgYmFzaAojIERvd25sb2FkIHNjcmlwdCB0byBwZXJmb3JtIFBWIHRvIEhWTSBjb252ZXJzaW9uCiN0aGlzIGlzIGluamVjdGVkIGludG8gL2V0Yy9yYy5sb2NhbCBhdCBib290IHRpbWUKd2dldCAtcU8gL3RtcC9odm0uc2ggaHR0cDovL2U5NDJiMDI5YzI1NmVjMzIzMTM0LWQxNDA4Yjk2ODkyODU2MTgyMzEwOWNiNjZjNDdlYmNkLnIzNy5jZjUucmFja2Nkbi5jb20vaHZtLnNoCi91c3IvYmluL2VudiBiYXNoIC90bXAvaHZtLnNoCiNPbmx5IHVzZWQgZm9yIHRyb3VibGVzaG9vdGluZywgZG9lcyBub3QgbmVlZCB0byBiZSBpbiBmaW5hbCBzY3JpcHQKc3NoLWtleWdlbiAtQQ=="}]}}'

#begin main function
@plac.annotations(
    glance_image=plac.Annotation("UUID of Cloud Server image")
                )

def main(glance_image):
    username,password = getset_keyring_credentials()
    auth_token = get_auth_token(username, password)
    glance_endpoints, cs_endpoints, headers = find_endpoints(auth_token)
    glance_object, cs_endpoint, region = find_glance_image_and_cs_endpoint(auth_token, headers, cs_endpoints, glance_endpoints, glance_image)
    check_glance_image(auth_token, headers, glance_image, glance_object)
    flavor = determine_server_flavor(auth_token, headers, glance_image, glance_object)
    build_server(auth_token, headers, cs_endpoint, glance_image, glance_object, flavor)

if __name__ == '__main__':
    import plac
    plac.call(main)
