#!/usr/bin/env python
# rc-pv2hvm, a script that converts Rackspace Cloud Servers from PV to HVM mode
# version: 0.0.1a
# Copyright 2018 Brian King
# License: Apache

import argparse
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
    cs_endpoints=[]
    #setting up api call
    url = ("https://identity.api.rackspacecloud.com/v2.0/tokens/%s/endpoints" % auth_token)
    headers = {'content-type': 'application/json', 'Accept': 'application/json',
               'X-Auth-Token': auth_token}
    raw_service_catalog = requests.get(url, headers=headers)
    the_service_catalog = raw_service_catalog.json()
    endpoints = the_service_catalog["endpoints"]
    for service in range(len(endpoints)):
        if "cloudServersOpenStack" == endpoints[service]["name"]:
            cs_endpoints.append( endpoints[service]["publicURL"])
    return cs_endpoints, headers

def find_cloud_server(auth_token, headers, cs_endpoints, cloud_server):
    print ("Determining which region your cloud server is in...")
    for endpoint in range(len(cs_endpoints)):
        potential_url = ( "%s/servers/%s" % (cs_endpoints[endpoint], cloud_server) )
        potential_server = requests.get(url=potential_url, headers=headers)
        if potential_server.status_code == 200:
            cs_object = potential_server
            return cs_object
            break
    #if we make it this far, the cloud server UUID is invalid
    print ("Error! Rackspace Cloud Server UUID %s was not found." % (cloud_server) )
    sys.exit()

def check_server_status(auth_token, headers, cs_object):
#Ensure server is in the proper state before we take an image
    vm_state = cs_object.json()["server"]["OS-EXT-STS:vm_state"]
    if vm_state != "active":
        print ("Error! Improper VM state. Expected 'active', got '%s'." % (vm_state))
        sys.exit()
    task_state = cs_object.json()["server"]["OS-EXT-STS:task_state"]
    if task_state is not None:
        print ("Error! Improper task state. Expected 'None', got '%s'." % (task_state) )
        sys.exit()
#Ensure we aren't trying to image an OnMetal or BFV. This won't catch all of them as 
# Performance, I/O and GP servers can also be BFV.
    invalid_flavors = [ "metal", "memory", "compute" ]
    for flavor in invalid_flavors:
        if flavor in cs_object.json()["server"]["flavor"]["id"]:
            print ("Error! Can't convert flavor '%s'." % (flavor) )
            sys.exit()
        
def create_server_image(auth_token, headers, cs_object):
#image the server so we can build another one
    print ("Creating image of server %s" % (cs_object.json()["server"]["name"]))
    cs_url = ("%s/action" % (cs_object.json()["server"]["links"][0]["href"]))
    image_creator = "rs-pv2hvm"
    rand_postpend = str(uuid.uuid4())
    image_name = ("%s-%s-%s" % (cs_object.json()["server"]["name"], image_creator, rand_postpend[0:7]))
    data = {
            "createImage" : {
                "name" : image_name,
                "metadata": {
                    "created_by": image_creator

                }
            }
            }
    image_create = requests.post(url=cs_url, headers=headers,data=json.dumps(data))
    image_create.raise_for_status()
    if image_create.ok:
        image_url = image_create.headers["Location"]
        return image_url
    #if we made it this far, somehow we never got the image URL.
    if not image_url:
        print ("Error! Did not receive image URL from Cloud Servers API. Exiting." )
        sys.exit()

def check_image_status(auth_token, headers, image_url):
    image_info = requests.get(url=image_url, headers=headers)
    image_status=image_info.json()["image"]["status"]
    while image_status == "SAVING":
        for x in range (0,100):
            image_info = requests.get(url=image_url, headers=headers,stream=True)
            image_status=image_info.json()["image"]["status"]
            print ("Checking image status" + "." * x)
            sys.stdout.write("\033[F")
            print ("Image status is %s" % (image_status))
            time.sleep(8)
            if image_status() == "ACTIVE":
            break
#     print ("Checking image status of %s " % 
    
      

#begin main function
@plac.annotations(
    cloud_server=plac.Annotation("UUID of Rackspace Cloud Server")
                )

def main(cloud_server):
    username,password = getset_keyring_credentials()
    auth_token = get_auth_token(username, password)
    cs_endpoints, headers = find_endpoints(auth_token)
    cs_object = find_cloud_server(auth_token, headers, cs_endpoints, cloud_server)
    check_server_status(auth_token, headers, cs_object)
    image_url = create_server_image(auth_token, headers, cs_object)
    check_image_status(auth_token, headers, image_url)

if __name__ == '__main__':
    import plac
    plac.call(main)
