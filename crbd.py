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
        # Extract the c-projection psi_c(G) = (V_c, E_c) for a given color.
        proj_edges = {e for e in self.edges if color in self.coloring[e]}
        proj_nodes = {u for u, v in proj_edges} | {v for u, v in proj_edges} | {self.start, self.end}
        return proj_nodes, proj_edges

    @staticmethod
    def _translate_coloring(coloring_dict: dict, old_start: Node, old_end: Node, new_start: Node, new_end: Node) -> dict:
        """
        Applies renaming of START/END nodes to the keys of a coloring dictionary.
        Returns a new dictionary with the translated edges and copies of the color sets.
        """
        translated = {}
        for (u, v), colors in coloring_dict.items():
            src = new_start if u == old_start else u
            dst = new_end if v == old_end else v
            translated[(src, dst)] = set(colors)
        return translated

    def __floordiv__(self, other):
        """ Parallel composition of cRBDs: self // other """
        if not isinstance(other, CRBD):
            return NotImplemented
            
        # Must ensure that color sets are disjoint
        if not self.colors.isdisjoint(other.colors):
            raise ValueError("Systems cannot share colors when composing in parallel.")

        new_nodes, new_edges, new_start, new_end = self._graph_parallel_comp(other)
        new_colors = self.colors | other.colors

        # Rename both coloring functions 
        c_self = self._translate_coloring(self.coloring, self.start, self.end, new_start, new_end)
        c_other = self._translate_coloring(other.coloring, other.start, other.end, new_start, new_end)

        # New coloring function
        new_coloring = {}
        for e in new_edges:
            # get(e, set()) return colors set if e exists, empty set otherwise.
            colors_self = c_self.get(e, set())
            colors_other = c_other.get(e, set())
            
            new_coloring[e] = colors_self | colors_other
                
        return CRBD(new_nodes, new_edges, new_start, new_end, new_colors, new_coloring)
                
    def __rshift__(self, other):
        """ Serial composition of cRBDs: self >> other """
        if not isinstance(other, CRBD):
            return NotImplemented
        if not self.functional_nodes.isdisjoint(other.functional_nodes):
            raise ValueError("Systems cannot share functional nodes when composing in series.")

        new_nodes, new_edges, new_start, new_end = self._graph_parallel_comp(other)
        new_colors = self.colors | other.colors

        # Rename both coloring functions 
        c_self = self._translate_coloring(self.coloring, self.start, self.end, new_start, new_end)
        c_other = self._translate_coloring(other.coloring, other.start, other.end, new_start, new_end)

        # New coloring function
        new_coloring = {}
        for e in new_edges:
            # get(e, set()) return colors set if e exists, empty set otherwise.
            colors_self = c_self.get(e, set())
            colors_other = c_other.get(e, set())
            
            new_coloring[e] = colors_self | colors_other
                
        return CRBD(new_nodes, new_edges, new_start, new_end, new_colors, new_coloring)