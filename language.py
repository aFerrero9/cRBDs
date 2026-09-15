from collections import deque
from itertools import product
import copy

# Nodes

class Node:
    def __init__(self, id_name: str, is_functional: bool = True, is_up: bool = True):
        self.id = id_name
        self.is_functional = is_functional
        self.is_up = is_up

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Node) and self.id == other.id

    def __repr__(self):
            type_str = "F" if self.is_functional else "NF"
            state_str = f"is up={self.up}"
            
            return f"Node({self.id}, {type_str}, {state_str})"

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
        if self.start.is_functional or self.end.is_functional:
            raise ValueError("Invalid RBD: START or END are marked as functional nodes")

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

    def __floordiv__(self, other):
        """Parallel composition: self // other"""
        if not isinstance(other, RBD):
            return NotImplemented

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

        return RBD(new_nodes, e_self | e_other, new_start, new_end)

    def __rshift__(self, other):
        """Serial composition: self >> other"""
        if not isinstance(other, RBD):
            return NotImplemented
        if not self.functional_nodes.isdisjoint(other.functional_nodes):
            raise ValueError("Systems cannot share functional nodes.")

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

        return RBD(new_nodes, new_edges, new_start, new_end)