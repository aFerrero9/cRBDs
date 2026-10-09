from rbd import Node, RBD
from itertools import product

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
        edges = set()
        for (u, v), colors in coloring_dict.items():
            # First 2 conditions are for serial composition
            if old_start is None:
                src = u
                dst = new_end if v == old_end else v
            elif old_end is None:
                src = new_start if u == old_start else u
                dst = v    
            else:
                src = new_start if u == old_start else u
                dst = new_end if v == old_end else v
            edges.add((src, dst))
            translated[(src, dst)] = set(colors)
        return translated, edges

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
        c_self, _ = self._translate_coloring(self.coloring, self.start, self.end, new_start, new_end)
        c_other, _ = self._translate_coloring(other.coloring, other.start, other.end, new_start, new_end)

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

        new_nodes, new_edges, new_start, new_end = self._graph_serial_comp(other)
        new_colors = set(product(self.colors, other.colors))

        # Rename just self.start and other.end in coloring functions 
        c_self, r_self_edges = self._translate_coloring(
            self.coloring, old_start=self.start, old_end=None, new_start=new_start, new_end=None)
        c_other, r_other_edges = self._translate_coloring(
            other.coloring, old_start=None, old_end=other.end, new_start=None, new_end=new_end)

        # New coloring function (composite colors)
        new_coloring = {}
        for e in new_edges:
            if e in r_self_edges:
                new_coloring[e] = set(product(c_self[e], other.colors))
            elif e in r_other_edges:
                new_coloring[e] = set(product(self.colors, c_other[e]))
            else:
                u, v = e 
                new_coloring[e] = set(product(c_self[u, self.end], c_other[other.start, v]))
                
        return CRBD(new_nodes, new_edges, new_start, new_end, new_colors, new_coloring)

    def _decomposition_lemma(self, adj_list: dict, init: Node, dst: Node, 
                             previous_path: list = None, all_paths: list = None) -> list:
        """ Extracts every path from a DAG between init and dst using DFS.
        Returns a list containing all paths (lists of nodes). """
        if self._is_dag():
            return super()._decomposition_lemma(self, adj_list, init, dst, previous_path, all_paths)
        else:
            raise ValueError("Decomposition lemma only works for DAGs.")

    def to_logic_formula(self, t: float, filename: str = "model.wcnf") -> str:
        """
        Converts the cRBD structure into a logic formula in DIMACS (WCNF) format,
        ready to be evaluated by the GPMC solver.
        Params: 
            t: Mission time (hours, days, etc.) for reliability calculation.
            filename: Output filename.
        Returns: the generated filename.
        """
        # Extract all global paths from start to end across all color projections
        all_paths = []
        seen_paths = set()  # To avoid duplicated paths in all_paths
        
        for color in self.colors:
            proj_nodes, proj_edges = self._c_projection(color)
            
            # Construct adj_list for the projection
            graph = {n: [] for n in proj_nodes}
            for u, v in proj_edges:
                graph[u].append(v)
                
            all_c_paths = RBD._decomposition_lemma(self, graph, self.start, self.end)
            
            # Check for duplicated paths
            for path in all_c_paths:
                path_tuple = tuple(path)  # Tuples are hashable and can be added to sets
                if path_tuple not in seen_paths:
                    seen_paths.add(path_tuple)
                    all_paths.append(path)

        just_id = [[n.id for n in path] for path in all_paths]
        print(f"---Global paths: {just_id}")
        # Map functional nodes to DIMACS variables (numbers > 0)
        dimacs_mapping = {}
        var_counter = 1
        
        # Sorted by node ID to ensure deterministic variable mapping in every run.
        functional_nodes = sorted(self.functional_nodes, key=lambda n: n.id)
        for node in functional_nodes:
            dimacs_mapping[node] = var_counter
            var_counter += 1

        num_vars = len(self.functional_nodes)
        num_clauses = len(all_paths)

        # Build DIMACS file content
        lines = []

        # Add comments to retrieve the mapping to original node IDs
        lines.append(f"c c DIMACS WCNF representation of cRBD for mission time t={t}")
        lines.append(f"c c Nodes mapping:")
        for node, var_id in dimacs_mapping.items():
            lines.append(f"c c {node.id} -> {var_id}")
        
        # DIMACS standard header
        lines.append(f"p cnf {num_vars} {num_clauses}")
        
        # Declare weights for WMC (MCC2021 format)
        for node in dimacs_mapping:
            var_id = dimacs_mapping[node]
            
            weight_fail, weight_success = node.get_wmc_weights(t)
            
            # MCC2021 format: c p weight <literal> <weight> 0
            lines.append(f"c p weight {var_id} {weight_fail:.9f} 0")     # Positive literal (node fails)
            lines.append(f"c p weight -{var_id} {weight_success:.9f} 0") # Negative literal (node survives)

        # Build the clauses
        for path in all_paths:
            clause_literals = []
            for node in path:
                # Only add functional nodes
                if node in dimacs_mapping:
                    clause_literals.append(str(dimacs_mapping[node]))
            
            # Each clause must end with a '0'
            if clause_literals:
                clause_line = " ".join(clause_literals) + " 0"
                lines.append(clause_line)

        wcnf_content = "\n".join(lines)
        with open(filename, "w") as f:
            f.write(wcnf_content)
            
        print(f"File {filename} successfully generated")
        return filename

    def __repr__(self):
        """String representation of the cRBD topology and coloring function."""
        base_repr = super().__repr__()
        
        lines = base_repr.split("\n")
        
        lines[0] = lines[0].replace("RBD(", "CRBD(", 1)
        # Insert the number of colors right before the closing parenthesis
        lines[0] = lines[0].replace(")", f", Colors: {len(self.colors)})")
        
        # Add a newline and the title for the coloring function
        lines.append("\nEdge Coloring Mapping:")
        
        # Sort edges alphabetically for deterministic and clean reading
        sorted_edges = sorted(self.coloring.keys(), key=lambda e: (e[0].id, e[1].id))
        
        for u, v in sorted_edges:
            # Add each edge with its associated colors
            lines.append(f"  {u.id} -> {v.id} : {self.coloring[(u, v)]}")
            
        # Rejoin all lines with newlines (\n)
        return "\n".join(lines)

    def draw(self, filename="crbd_diagram", view=True):
        """
        Generates and displays a visual representation of the cRBD using Graphviz.
        Delegates ranking and topological sorting to Graphviz's native Sugiyama 
        algorithm for a much cleaner and readable layout.
        """
        try:
            import graphviz
        except ImportError:
            raise ImportError("The 'graphviz' package is required. Run: pip install graphviz")

        dot = graphviz.Digraph(comment='Colored Reliability Block Diagram')
        
        # Global spacing adjustments
        dot.attr(rankdir='LR', ranksep='0.6', nodesep='0.5', splines='true') 
        dot.attr('node', fontname='Helvetica', fontsize='12', margin='0.1')
        dot.attr('edge', fontname='Helvetica', fontsize='9', labelfontname='Helvetica', labelfontsize='9')

        # Add START and END explicitly at the absolute extremes
        with dot.subgraph() as s:
            s.attr(rank='source')
            s.node(self.start.id, self.start.id, shape='ellipse', style='filled', fillcolor='lightgray')
            
        with dot.subgraph() as s:
            s.attr(rank='sink')
            s.node(self.end.id, self.end.id, shape='ellipse', style='filled', fillcolor='lightgray')

        # Add all other functional nodes (Graphviz calculates optimal depths automatically)
        for node in self.nodes:
            if node not in (self.start, self.end):
                color = 'lightblue' if node.is_up else 'salmon'
                dot.node(node.id, node.id, shape='box', style='filled', fillcolor=color)

        # Add directed edges keeping your exact label logic and mutual cycle detection
        for u, v in self.edges:
            edge_colors = self.coloring.get((u, v), set())
            label_text = str(edge_colors) if edge_colors else ""
            
            # Logical detection of mutual cycles
            if (v, u) in self.edges:
                # Push the label towards the source node (u).
                # labeldistance moves the label slightly away from the node so it doesn't overlap.
                dot.edge(u.id, v.id, taillabel=label_text, labeldistance='2.5', minlen='2')
            else:
                # Normal behavior for edges without cycles (centered label)
                dot.edge(u.id, v.id, label=label_text, minlen='2')

        # Render the graph
        try:
            dot.render(filename, format='pdf', view=view, cleanup=True)
        except Exception as e:
            print(f"Error rendering graph. Details: {e}")


        


# MINITEST: two satellites mini version
""" if __name__ == "__main__":
    # Parallel example
   
    start_a = Node("START", is_functional=False)
    laser_a_1 = Node("LaserA", is_functional=True, is_up=True, failure_rate=0.002)
    laser_b_1 = Node("LaserB", is_functional=True, is_up=True, failure_rate=0.005)
    end_a = Node("END", is_functional=False)
    
    nodes_a = {start_a, laser_a_1, laser_b_1, end_a}
    edges_a = {(start_a, laser_a_1), (laser_a_1, laser_b_1), (laser_a_1, end_a), (laser_b_1, end_a)}
    
    colors_a = {"red"}
    coloring_a = {e: {"red"} for e in edges_a}
    
    satellite_a = CRBD(nodes_a, edges_a, start_a, end_a, colors_a, coloring_a)

    start_b = Node("START", is_functional=False)
    laser_b_2 = Node("LaserB", is_functional=True, is_up=True, failure_rate=0.005)
    laser_a_2 = Node("LaserA", is_functional=True, is_up=True, failure_rate=0.002)
    end_b = Node("END", is_functional=False)
    
    nodes_b = {start_b, laser_b_2, laser_a_2, end_b}
    edges_b = {(start_b, laser_b_2), (laser_b_2, laser_a_2), (laser_b_2, end_b), (laser_a_2, end_b)}
    
    colors_b = {"blue"}
    coloring_b = {e: {"blue"} for e in edges_b}
    
    satellite_b = CRBD(nodes_b, edges_b, start_b, end_b, colors_b, coloring_b)

    system = satellite_a // satellite_b

    print("\nGlobal System Architecture:")
    print(system)

    system.draw(filename="my_system_crbd", view=True)
"""

""" if __name__ == "__main__":
    # Series example
    
    start_a = Node("START", is_functional=False)
    laser_a_1 = Node("LaserA", is_functional=True, is_up=True, failure_rate=0.002)
    laser_b_1 = Node("LaserB", is_functional=True, is_up=True, failure_rate=0.005)
    end_a = Node("END", is_functional=False)
    
    nodes_a = {start_a, laser_a_1, laser_b_1, end_a}
    edges_a = {(start_a, laser_a_1), (laser_a_1, laser_b_1), (laser_a_1, end_a), (laser_b_1, end_a)}
    
    colors_a = {"red"}
    coloring_a = {e: {"red"} for e in edges_a}
    
    satellite_a = CRBD(nodes_a, edges_a, start_a, end_a, colors_a, coloring_a)

    start_b = Node("START", is_functional=False)
    laser_b_2 = Node("LaserC", is_functional=True, is_up=True, failure_rate=0.003)
    laser_a_2 = Node("LaserD", is_functional=True, is_up=True, failure_rate=0.004)
    end_b = Node("END", is_functional=False)
    
    nodes_b = {start_b, laser_b_2, laser_a_2, end_b}
    edges_b = {(start_b, laser_b_2), (laser_b_2, laser_a_2), (laser_b_2, end_b), (laser_a_2, end_b)}
    
    colors_b = {"blue"}
    coloring_b = {e: {"blue"} for e in edges_b}
    
    satellite_b = CRBD(nodes_b, edges_b, start_b, end_b, colors_b, coloring_b)

    system = satellite_a >> satellite_b

    print("\nGlobal System Architecture:")
    print(system)

    system.draw(filename="my_system_crbd", view=True)
"""
