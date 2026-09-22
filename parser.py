""" 
RBD format example:
@SYSTEM
TYPE = RBD

@NODES
# id, is_functional (If omitted, True by default)

@TOPOLOGY
# u -> v

-------------------

cRBD format example:
@SYSTEM
TYPE = CRBD

@NODES
# id, is_functional (Si se omite, el parser asume True por defecto)

@TOPOLOGY
# u -> v : color_1, color_2, ...

"""
from rbd import Node, RBD
from crbd import CRBD

class RBDParser:
    """
    Parser for reading RBD and cRBD topologies from text files.
    Supports dynamic loading of edges and coloring functions.
    """
    pass