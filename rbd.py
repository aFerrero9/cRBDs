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
        state_str = f"is up={self.is_up}"
        
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
        Functional nodes are drawn as rectangles, structural nodes as ellipses.
        """
        try:
            import graphviz
        except ImportError:
            raise ImportError("The 'graphviz' package is required. Run: pip install graphviz")

        # Create a directed graph. 'LR' forces Left-to-Right layout (standard for RBDs).
        dot = graphviz.Digraph(comment='Reliability Block Diagram')
        dot.attr(rankdir='LR') 
        
        # General node attributes for better aesthetics
        dot.attr('node', fontname='Helvetica', fontsize='12', margin='0.1')

        # Add nodes with specific shapes based on their functional nature
        for node in self.nodes:
            if node.is_functional:
                # Functional components as rectangles (boxes)
                # Color can dynamically change if it's broken during a simulation
                color = 'lightblue' if node.is_up else 'salmon'
                dot.node(node.id, node.id, shape='box', style='filled', fillcolor=color)
            else:
                # Structural boundaries (START/END) as ellipses
                dot.node(node.id, node.id, shape='ellipse', style='filled', fillcolor='lightgray')

        # Add directed edges (arrows)
        for u, v in self.edges:
            dot.edge(u.id, v.id)

        # Render the graph to a file and optionally open it
        try:
            dot.render(filename, format='png', view=view, cleanup=True)
        except Exception as e:
            print(f"Error rendering graph. Ensure Graphviz binaries are installed on your OS. Details: {e}")


# MINITEST

def create_atomic_block(name: str) -> RBD:
    """Helper function to quickly create a single-component RBD."""
    comp = Node(name, is_functional=True, is_up=True)
    start = Node("START", is_functional=False)
    end = Node("END", is_functional=False)
    
    nodes = {start, comp, end}
    edges = {(start, comp), (comp, end)}
    
    return RBD(nodes, edges, start, end)

""" if __name__ == "__main__":
    # 1. Instanciamos los bloques básicos
    pump_a = create_atomic_block("Bomba_A")
    pump_b = create_atomic_block("Bomba_B")
    valve = create_atomic_block("Valvula_Principal")
    sensor = create_atomic_block("Sensor_Presion")

    # 2. Componemos el sistema usando tu álgebra de operadores
    # (Bomba A // Bomba B) >> Valvula >> Sensor
    pumps_subsystem = pump_a // pump_b
    system = pumps_subsystem >> valve >> sensor

    print(system)

    system.draw(filename="my_sistem_rbd", view=True)
 """
