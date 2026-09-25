"""Mininet topology for h1 - s1 - s2 - h2.

This module is Linux/Mininet-only and is intentionally not imported by the web API
until a real network execution mode is enabled.
"""

def build_topology():
    from mininet.net import Mininet
    from mininet.node import Controller
    from mininet.topo import Topo

    class NetPulseTopo(Topo):
        def build(self):
            h1, h2 = self.addHost("h1"), self.addHost("h2")
            s1, s2 = self.addSwitch("s1"), self.addSwitch("s2")
            self.addLink(h1, s1)
            self.addLink(s1, s2)
            self.addLink(s2, h2)

    return Mininet(topo=NetPulseTopo(), controller=Controller)
