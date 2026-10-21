from collections import deque
from itertools import product
import copy
import math
import os

# Nodes

class Node:
    def __init__(self, id_name: str, is_functional: bool = True, 
                 is_up: bool = True, failure_rate: float = 0.0):
        self.id = id_name
        self.is_functional = is_functional
        self.is_up = is_up
        self.failure_rate = float(failure_rate) if is_functional else 0.0

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Node) and self.id == other.id

    def __repr__(self):
        type_str = "F" if self.is_functional else "NF"
        state_str = f"is up={self.is_up}, failure rate={self.failure_rate}"
        
        return f"Node({self.id}, {type_str}, {state_str})"

    def get_wmc_weights(self, t: float) -> tuple:
        """
        Calculates the reliability weights for a given mission time t using Exponential Distribution.
        Returns (weight_fail, weight_success)
        """
        # R(t) = P[X > t] = e^(-lambda * t) 
        reliability = math.exp(-self.failure_rate * t)
        
        # F(t) = P[X <= t] = 1 - R(t)
        unreliability = 1.0 - reliability 
        
        return (unreliability, reliability)

# RBDs

class RBD:
    def __init__(self, nodes: set, edges: set, start_node: Node, end_node: Node):
        self.nodes = set(nodes)
        self.edges = set(edges) # set of (Node, Node)
        self.start = start_node
        self.end = end_node
        
        self._validate()

    @property
    def functional_nodes(self):
        return {n for n in self.nodes if n.is_functional}

    def _validate(self):
        if not self._is_dag():
            raise ValueError("Invalid RBD: The graph contains cycles.")
        if not self._check_connectivity():
            raise ValueError("Invalid RBD: Functional nodes are structurally isolated.")
        if len(self.functional_nodes) < 1:
            raise ValueError("There must be at least one functional component.")
        if self.nodes - self.functional_nodes != {self.start, self.end}:
            raise ValueError("The system must contain exactly two non-functional nodes: START and END.")

    def _is_dag(self):
        """Verifies that the graph has no cycles using DFS."""
        
        # Build adjacency list
        graph = {n: [] for n in self.nodes}
        for u, v in self.edges:
            graph[u].append(v) 

        # State control: 
        # 0 = Unvisited; 1 = Visiting (Currently in our path); 2 = Done (Node and all its neighbors no-cyclic verified)
        state = {n: 0 for n in self.nodes}

        def has_cycle(node):
            # If we find a node we are currently visiting, a cycle exists
            if state[node] == 1: 
                return True  
            # If we find a node that is already done, skip
            if state[node] == 2: 
                return False 

            # Add node to current path
            state[node] = 1 
            
            # Explore its neighbors
            for neighbor in graph[node]:
                if has_cycle(neighbor):
                    return True
                    
            # All clear, mark node as done
            state[node] = 2 
            return False

        # Main part
        for node in self.nodes:
            if state[node] == 0:
                if has_cycle(node):
                    return False            

        # If the loop finishes without returning False, the graph is acyclic.
        return True

    def _check_connectivity(self):
        """Verifies that all nodes in the graph belong to a path between start and end (no isolated nodes)."""
        
        def _bfs(adj_list: dict, init: Node):
            visited = set([init])
            queue = deque([init])

            while queue:
                node = queue.popleft()
                for neighbor in adj_list[node]:
                    if neighbor not in visited:
                        queue.append(neighbor)
                        visited.add(neighbor)
            return visited

        # Build adjacency list
        graph = {n: [] for n in self.nodes}
        for u, v in self.edges:
            graph[u].append(v)

        # Build adjacency backwards
        reversed_edges = {e[::-1] for e in self.edges}
        reversed_graph = {n: [] for n in self.nodes}
        for u, v in reversed_edges:
            reversed_graph[u].append(v)

        from_start = _bfs(graph, self.start)
        from_end = _bfs(reversed_graph, self.end)

        return (from_start & from_end) == self.nodes

    @staticmethod
    def _rename_edges(edges_set, old_node, new_node):
        """ Apply G[old_node <- new_node]."""
        new_edges = set()
        for u, v in edges_set:
            src = new_node if u == old_node else u
            dst = new_node if v == old_node else v
            
            if src == dst:
                raise ValueError(
                    f"Invalid operation: Renaming created a self-loop on node '{src.id}'.")
                
            new_edges.add((src, dst))
            
        return new_edges

    def _graph_parallel_comp(self, other):
        """ Aux function to accomplish graph composition """
        # Create copies to avoid references
        selfc = copy.deepcopy(self)
        otherc = copy.deepcopy(other)

        # Create the new non-functional nodes
        new_start = Node("START", is_functional=False)
        new_end = Node("END", is_functional=False)

        # Delete old NF nodes
        nodes_self = selfc.nodes - {selfc.start, selfc.end}
        nodes_other = otherc.nodes - {otherc.start, otherc.end}

        # Create new nodes set
        new_nodes = nodes_self | nodes_other | {new_start, new_end}

        # Edge renaming
        e_self = self._rename_edges(selfc.edges, selfc.start, new_start)
        e_self = self._rename_edges(e_self, selfc.end, new_end)
        
        e_other = self._rename_edges(otherc.edges, otherc.start, new_start)
        e_other = self._rename_edges(e_other, otherc.end, new_end)

        raw_new_edges = e_self | e_other

        # Unify shared memory references
        # Map every Node ID to its single official memory instance in new_nodes
        node_map = {n.id: n for n in new_nodes}
        
        # Rebuild the edges so u and v strictly point to the official instances
        new_edges = {(node_map[u.id], node_map[v.id]) for u, v in raw_new_edges}

        return new_nodes, new_edges, new_start, new_end
        
    def __floordiv__(self, other):
        """ Parallel composition of RBDs: self // other"""
        if not isinstance(other, RBD):
            return NotImplemented

        new_nodes, new_edges, new_start, new_end = self._graph_parallel_comp(other)

        return RBD(new_nodes, new_edges, new_start, new_end)
    
    def _graph_serial_comp(self, other):
        # Create copies to avoid references
        selfc = copy.deepcopy(self)
        otherc = copy.deepcopy(other)

        # Create the new non-functional nodes
        new_start = Node("START", is_functional=False)
        new_end = Node("END", is_functional=False)

        # Create new bridge edges
        self_final_nodes = {n for n in selfc.nodes if (n, selfc.end) in selfc.edges}
        other_first_nodes = {n for n in otherc.nodes if (otherc.start, n) in otherc.edges}
        
        new_bridge_edges = set(product(self_final_nodes, other_first_nodes))

        # Delete old edges
        self_old_edges_deleted = {(u, v) for u, v in selfc.edges if v != selfc.end}
        other_old_edges_deleted = {(u, v) for u, v in otherc.edges if u != otherc.start}

        new_edges = self_old_edges_deleted | other_old_edges_deleted | new_bridge_edges

        # Delete old NF nodes
        new_nodes = ((selfc.nodes | otherc.nodes) - {selfc.end, otherc.start, selfc.start, otherc.end}) | {new_start, new_end}

        # Edge renaming
        new_edges = self._rename_edges(new_edges, selfc.start, new_start)
        new_edges = self._rename_edges(new_edges, otherc.end, new_end)

        return new_nodes, new_edges, new_start, new_end

    def __rshift__(self, other):
        """ Serial composition of RBDs: self >> other"""
        if not isinstance(other, RBD):
            return NotImplemented
        if not self.functional_nodes.isdisjoint(other.functional_nodes):
            raise ValueError("Systems cannot share functional nodes when composing in series.")

        new_nodes, new_edges, new_start, new_end = self._graph_serial_comp(other)

        return RBD(new_nodes, new_edges, new_start, new_end)

    # RBD to logic formula logic:
    def _decomposition_lemma(self, adj_list: dict, init: Node, dst: Node, 
                             previous_path: list = None, all_paths: list = None) -> list:
        """ Extracts every path from a DAG between init and dst using DFS.
        Returns a list containing all paths (lists of nodes). """
        # Protect against mutable default arguments
        if previous_path is None:
            previous_path = []
        if all_paths is None:
            all_paths = []

        # Create copy of the path for this specific branch
        current_path = previous_path + [init]

        # Base case: we reached dst
        if init == dst:
            all_paths.append(current_path)
        else:
            # Recursive case
            for neighbor in adj_list[init]:
                RBD._decomposition_lemma(self, adj_list, neighbor, dst, current_path, all_paths)

        return all_paths

    def to_logic_formula(self, t: float, filename: str = "model.wcnf") -> str:
        """
        Converts the RBD structure into a logic formula in DIMACS (WCNF) format,
        ready to be evaluated by the GPMC solver.
        Params: 
        - t: Mission time (hours, days, etc.) for reliability calculation.
        - filename: Output filename.
        Returns: the generated file content.
        """
        # Extract all paths from start to end
        graph = {n: [] for n in self.nodes}
        for u, v in self.edges:
            graph[u].append(v)

        all_paths = self._decomposition_lemma(graph, self.start, self.end)
        
        # Map functional nodes to DIMACS variables (numbers > 0)
        dimacs_mapping = {}
        var_counter = 1
        
        # Sorted by node ID to ensure deterministic variable mapping in every run
        functional_nodes = sorted(self.functional_nodes, key=lambda n: n.id)
        for node in functional_nodes:
            dimacs_mapping[node] = var_counter
            var_counter += 1

        num_vars = len(self.functional_nodes)
        num_clauses = len(all_paths)

        # Build DIMACS file content
        lines = []

        # Add comments to retrieve the mapping to original node IDs
        lines.append(f"c c DIMACS WCNF representation of RBD for mission time t={t}")
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
            
            # Each clause must end with a 0
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
        Converts the RBD structure into a logic formula in DIMACS (WCNF) format
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
        
        # Auxiliary Variables (R_n) from N+1 onwards
        # Represents: "Did the success flow reach the output of this node?"
        reach_id = {}
        reach_counter = num_physical_vars + 1
        
        all_nodes_sorted = sorted(list(self.nodes), key=lambda n: n.id)
        for node in all_nodes_sorted:
            reach_id[node] = reach_counter
            reach_counter += 1
            
        num_total_vars = reach_counter - 1

        # Parents Mapping for each node
        parents = {n: [] for n in self.nodes}
        for u, v in self.edges:
            parents[v].append(u)

        clauses = []
        
        # Tseitin Clauses Construction: R_n <=> (-F_n AND (OR of R_p for all parents p))
        for node in all_nodes_sorted:
            R_n = reach_id[node]

            if node.is_functional:
                p_reaches = [reach_id[p] for p in parents[node]]
        
                F_n = dimacs_mapping[node]
                # Clause 1: If the node is reached, it must not have failed
                clauses.append([-R_n, -F_n])
                # Clause 2: If the node is reached, at least one parent must have been reached
                clauses.append([-R_n] + p_reaches)
                # Clause 3: If it didn't fail AND a parent is reached, then the node is reached
                for pr in p_reaches:
                    clauses.append([F_n, -pr, R_n])

            elif node == self.start:
                # START is always reachable
                clauses.append([R_n])

            elif node == self.end:
                # END is reachable if any of its parents are reachable
                p_reaches = [reach_id[p] for p in parents[node]]
                clauses.append([-R_n] + p_reaches)
                for pr in p_reaches:
                    clauses.append([-pr, R_n])
            
        # Final Condition: System Failure
        # We want the models where the flow does not reach END node
        clauses.append([-reach_id[self.end]])

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
        """String representation of the RBD topology (Adjacency List in BFS order)."""
        header = f"RBD(Functional Nodes: {len(self.functional_nodes)}, Total Edges: {len(self.edges)})"
        
        # Build an adjacency dictionary using node IDs
        adj_list = {n.id: [] for n in self.nodes}
        for u, v in self.edges:
            adj_list[u.id].append(v.id)
            
        lines = [header, "Topology:"]
        
        # BFS traversal to determine a natural printing order
        visited = {self.start.id}
        queue = deque([self.start.id])
        bfs_order = []
        
        while queue:
            current_id = queue.popleft()
            bfs_order.append(current_id)
            
            # Sort neighbors alphabetically for deterministic queuing of siblings
            neighbors = sorted(adj_list[current_id])
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
                    
        # Create output lines following the BFS logical order
        for node_id in bfs_order:
            targets = adj_list[node_id]
            if targets:
                targets_str = ", ".join(sorted(targets))
                lines.append(f"  {node_id} -> [{targets_str}]")
                
        return "\n".join(lines)

    def draw(self, filename="rbd_diagram", view=True):
        """
        Generates and displays a visual representation of the RBD using Graphviz.
        Delegates ranking and topological sorting to Graphviz's native Sugiyama 
        algorithm for a much cleaner and readable layout.
        """
        try:
            import graphviz
        except ImportError:
            raise ImportError("The 'graphviz' package is required. Run: pip install graphviz")

        dot = graphviz.Digraph(comment='Reliability Block Diagram')
        
        # Global spacing adjustments
        dot.attr(rankdir='LR', ranksep='0.6', nodesep='0.5', splines='true') 
        dot.attr('node', fontname='Helvetica', fontsize='12', margin='0.1')

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

        # Add directed edges (Without color labels for standard RBDs)
        for u, v in self.edges:
            # minlen='2' ensures the spacing between nodes matches the CRBD visual exactly
            dot.edge(u.id, v.id, minlen='2')

        # Render the graph
        os.makedirs("diagrams", exist_ok=True)
        safe_filename = os.path.basename(filename)
        filepath = os.path.join("diagrams", safe_filename)

        try:
            dot.render(filepath, format='pdf', view=view, cleanup=True)
        except Exception as e:
            print(f"Error rendering graph. Details: {e}")
