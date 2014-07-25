#!/usr/bin/env python
#
# Copyright (c) 2014, Arista Networks, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#  - Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#  - Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#  - Neither the name of Arista Networks nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL ARISTA NETWORKS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
# BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
# IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# bgpvxlan 
#
#    Version 1.0  - 7/17/2014 
#    Written by: 
#       Jeremy Georges, Arista Networks
#
#    Revision history:
#       1.0 - initial release

"""  bgpvxlan
    The purpose of this script is to leverage BGP community attributes to share the loopback 
    address which is used for the VTEP. By setting a BGP community attribute and sharing this across the ASN,
    we can then parse the BGP routes and dynamically add our flood list based on the custom BGP Community attribute. 
    Since the current implementation does not allow the ability to create a reactor, I'll just use a polling mechanism to parse the BGP table.
    This should not be an issue as we're only adding/deleting VTEP's in the flood list; so if polling cycle is around 60 seconds, 
    this should not impact our deployment.
    The alternative would be to run this as an agent/daemon and then a simple while loop with a 'sleep' timer which could be easily used.
"""

VERSION='1.0'
DEFAULTCOMMUNITY='5555:5555'
DEFAULTUSER='admin'
DEFAULTPW='mypassword'

#***********************************************************************************
# Modules
#***********************************************************************************
import os
import re
import sys
import optparse
import syslog
from jsonrpclib import Server

#==========================================================
# Function Definitions
#==========================================================
def matchme(strg, pattern):
    search=re.compile(pattern).search
    return bool(search(strg))



#=====================================================
# Variables
#=====================================================

#==========================================================
# MAIN
#==========================================================

def main():
    usage = "usage: %prog [options] arg1 arg2"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option("-V", "--version", action="store_true",dest="version", help="The version")
    parser.add_option("-c", "--community", type="string", dest="bgpcommunity", help="Set the BGP Community Attribute to Parse in format: 16bit:16bit",metavar="bgpcommunity",default=DEFAULTCOMMUNITY)
    parser.add_option("-v", action="store_true", dest="verbose", help="Verbose logging")
    parser.add_option("-u", "--user", type="string", dest="USERNAME", help="Username for EAPI",metavar="username",default=DEFAULTUSER)
    parser.add_option("-p", "--password", type="string", dest="PASSWORD", help="Password for EAPI",metavar="password",default=DEFAULTPW)
    (options, args) = parser.parse_args()

    if options.version:
        print os.path.basename(sys.argv[0]), "  Version: ", VERSION 
        sys.exit(0)
    if options.bgpcommunity:
        print "Parsing for BGP Community: " , options.bgpcommunity
   
    syslog.openlog(ident="BGPVXLAN-AGENT",logoption=syslog.LOG_PID, facility=syslog.LOG_LOCAL0)
    syslog.syslog('Log processing initiated...')
    
    # General login setup
    #switch = Server( "https://admin:4me2know@127.0.0.1/command-api")
    switch = Server( "https://%s:%s@127.0.0.1/command-api" % (options.USERNAME,options.PASSWORD))
 
    #Lets go ahead and parse the BGP routes
    #create a list to store each one
    showroutes = switch.runCmds( 1,[ "enable","show ip bgp community %s" % options.bgpcommunity ],"text")
    syslog.syslog('Parsing bgp routes for community %s ' % options.bgpcommunity) 
    communities=showroutes[1] ["output"]
    currentbgpvtep=[]
    currentbgpvtep = re.findall("\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/32", communities) 
    #Lets strip out the /32 for our list
    currentbgpvtep = map(lambda currentbgpvtep:currentbgpvtep.replace("/32", ""),currentbgpvtep)
    #Create a set to remove dups
    currentbgpvtep = list(set(currentbgpvtep))
    print "Current advertised vteps: ", currentbgpvtep

    #Lets get the current vtep flood list 
    showconfig = switch.runCmds( 1,[ "enable","show running-config"])
    vxlanstuff = showconfig[1] ["cmds"] ["interface Vxlan1"] ["cmds"]
    syslog.syslog('Looking up currently configured vtep flood list')
    #We'll store the current vtep flood list in configvteplist
    configvteplist=[]
    for line in vxlanstuff:
        if matchme(line, 'vxlan flood vtep'): 
            configvteplist = re.findall("\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", line) 
    
    print "Currently Configured VTEPs to flood to: ", configvteplist


    #Now we have the currently configured VTEPs and the ones advertised into BGP.
    #Lets compare what we have configured with what's being advertised. That way we can remove them first.
    #Next, add new ones with our currentbgpvtep list.

   
    #check currently configured. Remove any that need to be removed.
    
    for vtep in configvteplist:
        if vtep in currentbgpvtep:
            print "VTEP %s is still valid" % vtep
        else:
            print "Deleting %s from flood list" % vtep
            syslog.syslog('Deleting %s from flood list' % vtep)
            removevtep = switch.runCmds( 1,[ "enable", "configure","interface Vxlan1", "vxlan flood vtep remove  %s" % vtep ])

    # Now lets check to see if we need to add anything based on our BGP advertised loopbacks.
    for vtep in currentbgpvtep:
        if vtep in configvteplist:
            print "VTEP %s is already configured" % vtep
        else:
            print "VTEP %s being added to our flood list" % vtep
            syslog.syslog('VTEP %s being added to our flood list' % vtep ) 
            addvtep = switch.runCmds( 1,[ "enable", "configure","interface Vxlan1", "vxlan flood vtep add  %s" % vtep ]) 

if __name__ == "__main__":
    main()
