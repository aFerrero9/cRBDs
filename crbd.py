from rbd import Node, RBD

class CRBD(RBD):
    def __init__(self, nodes: set, edges: set, start_node: Node, end_node: Node, colors: set, coloring: dict):
        # New attributes for cRBD
        self.colors = set(colors)
        self.coloring = {e: set(c) for e, c in coloring.items()}

        # Call parent constructor to initialize the base cRBD attributes
        super().__init__(nodes, edges, start_node, end_node)

    def _validate(self):
        """
        In a valid cRBD, the following must hold:
        for every color c in C, the c-projection psi_c(G) is a valid RBD.
        """ 
        # Check that every projection is a valid RBD
        for color in self.colors:
            proj_nodes, proj_edges = self._c_projection(color)
            
            try:
                # Instantiating an RBD will run _validate() (DAG and connectivity) on this projection
                RBD(proj_nodes, proj_edges, self.start, self.end)
            except ValueError as e:
                raise ValueError(f"Invalid cRBD on color '{color}': {e}")

    def _c_projection(self, color):
        """
        Constructs the c-projection psi_c(G) = (V_c, E_c) for a given color.
        """
        proj_edges = {e for e in self.edges if color in self.coloring[e]}
        proj_nodes = {u for u, v in proj_edges} | {v for u, v in proj_edges} | {self.start, self.end}
        return proj_nodes, proj_edges

    def __floordiv__(self, other):
        """
        Parallel composition for cRBDs.
        Must ensure that color sets are disjoint: C_A intersection C_B = empty set
        """
        pass
    def __rshift__(self, other):
        """
        Serial composition for cRBDs.
        Must combine the coloring functions using the Cartesian product of C_A and C_B
        """
        pass 