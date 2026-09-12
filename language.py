from collections import deque
from itertools import product

# Nodes

class Node:
    def __init__(self, id_name: str, is_functional: bool = True):
        self.id = id_name
        self.is_functional = is_functional

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Node) and self.id == other.id

    def __repr__(self):
        type_str = "F" if self.is_functional else "NF"
        return f"Node({self.id}, {type_str})"


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
        """Verifies that all nodes in the graph belong to a valid path between start and end."""
        
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

    def _rename_edges(self, edges_set, old_node, new_node):
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

    def __or__(self, other):
        """ Parallel composition: self || other"""
        if not isinstance(other, RBD):
            return NotImplemented

        # Crete new nodes for renaming
        new_start = Node(f"START_{self.start.id}_{other.start.id}", is_functional=False)
        new_end = Node(f"END_{self.end.id}_{other.end.id}", is_functional=False)

        # (V_A U V_B)
        new_nodes = self.nodes.union(other.nodes)
        new_nodes.discard(self.start)
        new_nodes.discard(other.start)
        new_nodes.discard(self.end)
        new_nodes.discard(other.end)
        new_nodes.update([new_start, new_end])

        # Edge renaming
        e_a = self._rename_edges(self.edges, self.start, new_start)
        e_a = self._rename_edges(e_a, self.end, new_end)
        
        e_b = self._rename_edges(other.edges, other.start, new_start)
        e_b = self._rename_edges(e_b, other.end, new_end)

        return RBD(new_nodes, e_a.union(e_b), new_start, new_end)

    def __rshift__(self, other):
        """Composición Serial: self ; other (operador >>)"""
        if not isinstance(other, RBD):
            return NotImplemented

        # Restricción estricta: V_fA intersection V_fB = empty
        if self.functional_nodes.intersection(other.functional_nodes):
            raise ValueError("Serial composition requires disjoint functional node sets.")

        new_start = self.start
        new_end = other.end

        # Nodos intermedios a eliminar: self.end y other.start
        new_nodes = self.nodes.union(other.nodes)
        new_nodes.discard(self.end)
        new_nodes.discard(other.start)

        # Calculamos aristas puente (Bridge edges)
        preds_a = {u for u, v in self.edges if v == self.end}
        succs_b = {v for u, v in other.edges if u == other.start}
        bridge_edges = set(product(preds_a, succs_b))

        # Filtramos aristas originales eliminando las que tocaban los nodos borrados
        e_a = {(u, v) for u, v in self.edges if v != self.end}
        e_b = {(u, v) for u, v in other.edges if u != other.start}

        new_edges = e_a.union(e_b).union(bridge_edges)

        return RBD(new_nodes, new_edges, new_start, new_end)