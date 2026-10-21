import os

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
        - t: Mission time (hours, days, etc.) for reliability calculation.
        - filename: Output filename.
        Returns: the generated file content.
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
            
            # Each clause must end with 0
            if clause_literals:
                clause_line = " ".join(clause_literals) + " 0"
                lines.append(clause_line)

        wcnf_content = "\n".join(lines)
        
        os.makedirs("wmc_files", exist_ok=True)
        safe_filename = os.path.basename(filename)
        filepath = os.path.join("wmc_files", safe_filename)
        
        with open(filepath, "w") as f:
            f.write(wcnf_content)
            
        print(f"File {filepath} successfully generated")
        return wcnf_content

    def tseitin_to_logic_formula(self, t: float, filename: str = "model_tseitin.wcnf") -> str:
        """
        Converts the cRBD structure into a logic formula in DIMACS (WCNF) format
        using the Tseitin Transformation to prevent Path Explosion.
        """
        # Nodes Mapping (F_n) - Failure variables (1 to N)
        dimacs_mapping = {}
        var_counter = 1
        
        functional_nodes = sorted(self.functional_nodes, key=lambda n: n.id)
        for node in functional_nodes:
            dimacs_mapping[node] = var_counter
            var_counter += 1

        num_physical_vars = len(functional_nodes)

        # Construct Tseitin clauses for each color projection
        reach_counter = num_physical_vars + 1
        clauses = []

        for c in self.colors:
            # Auxiliary Variables (R_(n,color)) from N+1 onwards
            # Represents: "Did the success flow reach the output of this node?"
            c_reach_id = {}
            c_parents = {}
            proj_nodes, proj_edges = self._c_projection(c)

            all_nodes_sorted = sorted(list(proj_nodes), key=lambda n: n.id)
            for node in all_nodes_sorted:
                c_reach_id[node] = reach_counter
                reach_counter += 1
                
            # Parents Mapping for each node
            c_parents = {n: [] for n in proj_nodes}
            for u, v in proj_edges:
                c_parents[v].append(u)

            # Tseitin Clauses Construction: R_(n,color) <=> (-F_n AND (OR of R_(p,color) for all c_parents p))
            for node in all_nodes_sorted:
                R_nc = c_reach_id[node]

                if node.is_functional:
                    p_reaches = [c_reach_id[p] for p in c_parents[node]]
            
                    F_n = dimacs_mapping[node]
                    # Clause 1: If the node is reached, it must not have failed
                    clauses.append([-R_nc, -F_n])
                    # Clause 2: If the node is reached, at least one parent must have been reached
                    clauses.append([-R_nc] + p_reaches)
                    # Clause 3: If it didn't fail AND a parent is reached, then the node is reached
                    for pr in p_reaches:
                        clauses.append([F_n, -pr, R_nc])

                elif node == self.start:
                    # START is always reachable
                    clauses.append([R_nc])

                elif node == self.end:
                    # END is reachable if any of its c_parents are reachable
                    p_reaches = [c_reach_id[p] for p in c_parents[node]]
                    clauses.append([-R_nc] + p_reaches)
                    for pr in p_reaches:
                        clauses.append([-pr, R_nc])
                    # Final Condition: System Failure for color c
                    # We want the models where the flow does not reach END node for color c
                    clauses.append([-R_nc])

        num_total_vars = reach_counter - 1
        num_clauses = len(clauses)

        # DIMACS File Writing
        lines = []
        lines.append(f"c c DIMACS WCNF representation of RBD using Tseitin Transformation")
        lines.append(f"p cnf {num_total_vars} {num_clauses}")
        
        # Weights for physical components variables
        for node, var_id in dimacs_mapping.items():
            weight_fail, weight_success = node.get_wmc_weights(t)
            lines.append(f"c p weight {var_id} {weight_fail:.9f} 0")     
            lines.append(f"c p weight -{var_id} {weight_success:.9f} 0") 
                
        # Weights for logical auxiliary variables (R_n): 1 for both states
        for aux_var in range(num_physical_vars + 1, num_total_vars + 1):
            lines.append(f"c p weight {aux_var} 1.0 0")
            lines.append(f"c p weight -{aux_var} 1.0 0")

        for clause in clauses:
            clause_line = " ".join(map(str, clause)) + " 0"
            lines.append(clause_line)

        wcnf_content = "\n".join(lines)
        
        os.makedirs("wmc_files", exist_ok=True)
        safe_filename = os.path.basename(filename)
        filepath = os.path.join("wmc_files", safe_filename)
        
        with open(filepath, "w") as f:
            f.write(wcnf_content)
            
        print(f"File {filepath} successfully generated")
        return wcnf_content

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
        os.makedirs("diagrams", exist_ok=True)
        safe_filename = os.path.basename(filename)
        filepath = os.path.join("diagrams", safe_filename)

        try:
            dot.render(filepath, format='pdf', view=view, cleanup=True)
        except Exception as e:
            print(f"Error rendering graph. Details: {e}")
