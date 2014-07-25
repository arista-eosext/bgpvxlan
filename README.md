bgpvxlan
========
Use BGP Community Attribute to advertise VTEP Loopback addresses using BGP Community Attribute to Advertise VTEPs 
for VXLAN with Head End Replication

##Author
Jeremy Georges - Arista Networks 
jgeorges@arista.com

##Description

The purpose of this document and script is to outline the possibility of using BGP’s Community Attribute to mark a loopback address/prefix as a VTEP in a VXLAN network. 

Many large ECMP deployments already use BGP and its rich policy control for advertising routes between Leaf and Spine layers. Therefore, this rich control and extensible protocol can be leveraged to ‘tag’ specific route prefixes as they are advertised to their peers. The BGP community attributes are simply values attached to a route that is sent to the BGP peers. These values have special meanings to the peers and cause specific actions to be taken, depending on the values assigned.

 


In the (attached) Proof of Concept topology, each Leaf switch is a separate Autonomous System. The Spine layer is also a separate ASN so features of BGP such as MED can be used to manipulate routes during a maintenance window, for example.

Each Leaf switch has a loopback address defined and this is also the source interface specified in the vxlan configuration. By using route-maps, we can take this specific interface route (loopback interface) and add a BGP community string that can be used by all other leaf routers to learn their neighboring VTEP addresses. Then a simple EOS script can run using the scheduler every minute to verify if that BGP route, with the appropriate Community is added in the VTEP flood list.


After testing with vEOS with the above topology, this works very well, with a worst case VTEP update time of 1 minute. Since this flood list is only changed when we either a VTEP loses all routes to a VTEP Loopback, or if a new VTEP comes on line, the one minute add/removal time is negligible. 



Here is an example of when one of the Leaf switches (leaf3) is down. You can see that we only have one BGP route with the Community of 5555:5555, which was used for this proof of concept. Therefore, the script only added this remote loopback address to the ‘Vxlan flood vtep’ list.

```
vxlan-leaf1(config)#show ip bgp community 5555:5555
BGP routing table information for VRF default
Router identifier 192.168.254.3, local AS number 65001
Route status codes: s - suppressed, * - valid, > - active, E - ECMP head, e - ECMP
                    S - Stale
Origin codes: i - IGP, e - EGP, ? - incomplete
AS Path Attributes: Or-ID - Originator ID, C-LST - Cluster List, LL Nexthop - Link Local Nexthop

      Network             Next Hop         Metric  LocPref Weight Path
 * >E 192.168.254.4/32    10.1.1.1         0       100     0      65535 65002 i  
 *  e 192.168.254.4/32    10.1.1.9         0       100     0      65535 65002 i  


vxlan-leaf1(config)#show run section interface Vxlan1
interface Vxlan1
   vxlan source-interface Loopback0
   vxlan udp-port 4789
   vxlan vlan 100 vni 10000
   vxlan vlan 200 vni 20000
   vxlan flood vtep 192.168.254.4
```

After bringing up Leaf-switch 3, it begins to advertise its loopback address and the arbitrary BGP Community 5555:5555. Notice the syslog entry from the script which parses the BGP routes and sees the new /32 route with the correct community now advertised.
```
Jul 18 04:27:40 vxlan-leaf1 BGPVXLAN-AGENT[1740]: Log processing initiated...
Jul 18 04:27:41 vxlan-leaf1 BGPVXLAN-AGENT[1740]: Parsing bgp routes for community 5555:5555 
Jul 18 04:27:42 vxlan-leaf1 BGPVXLAN-AGENT[1740]: Looking up currently configured vtep flood list
Jul 18 04:27:42 vxlan-leaf1 BGPVXLAN-AGENT[1740]: VTEP 192.168.254.5 being added to our flood list
```

```
vxlan-leaf1(config)#show ip bgp community 5555:5555
BGP routing table information for VRF default
Router identifier 192.168.254.3, local AS number 65001
Route status codes: s - suppressed, * - valid, > - active, E - ECMP head, e - ECMP
                    S - Stale
Origin codes: i - IGP, e - EGP, ? - incomplete
AS Path Attributes: Or-ID - Originator ID, C-LST - Cluster List, LL Nexthop - Link Local Nexthop

      Network             Next Hop         Metric  LocPref Weight Path
 * >E 192.168.254.4/32    10.1.1.1         0       100     0      65535 65002 i  
 *  e 192.168.254.4/32    10.1.1.9         0       100     0      65535 65002 i  
 * >E 192.168.254.5/32    10.1.1.1         0       100     0      65535 65003 i  
 *  e 192.168.254.5/32    10.1.1.9         0       100     0      65535 65003 i  
```




The script automatically adds the remote vtep address in the flood list.
```
vxlan-leaf1(config)#show run section interface Vxlan1
interface Vxlan1
   vxlan source-interface Loopback0
   vxlan udp-port 4789
   vxlan vlan 100 vni 10000
   vxlan vlan 200 vni 20000
   vxlan flood vtep 192.168.254.4 192.168.254.5
```

This provides a feasible mechanism to advertise VTEP loopback address throughout a datacenter by leveraging BGP.


The general configuration for the route-map and BGP is not difficult and can be augmented to any existing ECMP design.

Config snippet below:
```
interface Loopback0
   ip address 192.168.254.3/32
!
interface Management1
   ip address 192.168.56.102/24
!
interface Vxlan1
   vxlan source-interface Loopback0
   vxlan udp-port 4789
   vxlan vlan 100 vni 10000
   vxlan vlan 200 vni 20000
   vxlan flood vtep 192.168.254.4 #Note these are dynamic with script!!!
!
ip prefix-list MYLOOPBACK seq 10 permit 192.168.254.3/32
!
route-map MYTVTEP permit 10
!
route-map MYVTEP permit 10
   match ip address prefix-list MYLOOPBACK
   match interface Loopback0
   set community internet 5555:5555 
!
router bgp 65001
   router-id 192.168.254.3
   maximum-paths 2 ecmp 2
   neighbor 10.1.1.1 remote-as 65535
   neighbor 10.1.1.1 send-community
   neighbor 10.1.1.1 route-map MYVTEP out
   neighbor 10.1.1.1 maximum-routes 12000 
   neighbor 10.1.1.9 remote-as 65535
   neighbor 10.1.1.9 send-community
   neighbor 10.1.1.9 route-map MYVTEP out
   neighbor 10.1.1.9 maximum-routes 12000 
   network 192.168.254.3/32
```


For more details on VXLAN configuration in EOS, please refer to the Arista EOS documentation found at:
http://www.arista.com/en/support/docs



