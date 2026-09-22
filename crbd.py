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

    def __repr__(self):
        """String representation of the cRBD topology and coloring function."""
        base_repr = super().__repr__()
        
        lines = base_repr.split("\n")
        
        lines[0] = lines[0].replace("RBD(", "CRBD(", 1)
        # Le insertamos la cantidad de colores justo antes del paréntesis de cierre
        lines[0] = lines[0].replace(")", f", Colors: {len(self.colors)})")
        
        # 4. Agregamos un salto de línea y el título para la función de coloreo
        lines.append("\nEdge Coloring Mapping:")
        
        # 5. Ordenamos las aristas alfabéticamente para que la lectura sea determinista y prolija
        sorted_edges = sorted(self.coloring.keys(), key=lambda e: (e[0].id, e[1].id))
        
        for u, v in sorted_edges:
            # Agregamos cada arista con sus colores asociados
            lines.append(f"  {u.id} -> {v.id} : {self.coloring[(u, v)]}")
            
        # 6. Volvemos a unir todas las líneas con saltos de línea (\n)
        return "\n".join(lines)

    def draw(self, filename="crbd_diagram", view=True):
        """
        Generates and displays a visual representation of the cRBD using Graphviz.
        Forces parallel nodes to align vertically by calculating their topological depth.
        Dynamically shifts edge labels to avoid overlaps in mutual cycles.
        """
        try:
            import graphviz
            from collections import deque
        except ImportError:
            raise ImportError("The 'graphviz' package is required. Run: pip install graphviz")

        dot = graphviz.Digraph(comment='Colored Reliability Block Diagram')
        
        # Global spacing adjustments
        dot.attr(rankdir='LR', ranksep='0.4', nodesep='0.4') 
        dot.attr('node', fontname='Helvetica', fontsize='12', margin='0.1')
        
        # Se agregaron labelfontname y labelfontsize para controlar el tamaño de los taillabel/headlabel
        dot.attr('edge', fontname='Helvetica', fontsize='9', labelfontname='Helvetica', labelfontsize='9')

        # 1. Calculate topological depth using BFS to find nodes on the same level
        depths = {}
        visited = {self.start}
        queue = deque([(self.start, 0)])

        while queue:
            curr_node, current_depth = queue.popleft()
            
            if curr_node not in (self.start, self.end):
                depths[curr_node] = current_depth
                
            neighbors = [v for u, v in self.edges if u == curr_node]
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, current_depth + 1))

        # 2. Group nodes by depth
        depth_groups = {}
        for node, depth in depths.items():
            depth_groups.setdefault(depth, []).append(node)

        # 3. Add START and END explicitly at the absolute extremes
        with dot.subgraph() as s:
            s.attr(rank='source')
            s.node(self.start.id, self.start.id, shape='ellipse', style='filled', fillcolor='lightgray')
            
        with dot.subgraph() as s:
            s.attr(rank='sink')
            s.node(self.end.id, self.end.id, shape='ellipse', style='filled', fillcolor='lightgray')

        # 4. Add functional nodes grouped by their depth to force vertical alignment
        for depth, nodes in depth_groups.items():
            with dot.subgraph() as s:
                s.attr(rank='same')
                for node in nodes:
                    color = 'lightblue' if node.is_up else 'salmon'
                    s.node(node.id, node.id, shape='box', style='filled', fillcolor=color)

        # 5. Add directed edges with dynamically positioned coloring labels
        for u, v in self.edges:
            edge_colors = self.coloring.get((u, v), set())
            label_text = str(edge_colors) if edge_colors else ""
            
            # Detección lógica de ciclos mutuos
            if (v, u) in self.edges:
                # Empuja la etiqueta hacia el nodo de origen (u).
                # labeldistance aleja la etiqueta ligeramente del nodo para que no lo pise.
                dot.edge(u.id, v.id, taillabel=label_text, labeldistance='2.5', minlen='2')
            else:
                # Comportamiento normal para aristas sin ciclo (etiqueta al centro)
                dot.edge(u.id, v.id, label=label_text, minlen='2')

        # 6. Render the graph
        try:
            dot.render(filename, format='png', view=view, cleanup=True)
        except Exception as e:
            print(f"Error rendering graph. Details: {e}")


# MINITEST: two satellites mini version
if __name__ == "__main__":
    # 1. Manually instantiate Satellite A: START -> LaserA -> LaserB -> END (Red)
    start_a = Node("START", is_functional=False)
    laser_a_1 = Node("LaserA", is_functional=True, is_up=True)
    laser_b_1 = Node("LaserB", is_functional=True, is_up=True)
    end_a = Node("END", is_functional=False)
    
    nodes_a = {start_a, laser_a_1, laser_b_1, end_a}
    edges_a = {(start_a, laser_a_1), (laser_a_1, laser_b_1), (laser_a_1, end_a), (laser_b_1, end_a)}
    
    colors_a = {"red"}
    coloring_a = {e: {"red"} for e in edges_a}
    
    satellite_a = CRBD(nodes_a, edges_a, start_a, end_a, colors_a, coloring_a)

    # 2. Manually instantiate Satellite B: START -> LaserB -> LaserA -> END (Blue)
    start_b = Node("START", is_functional=False)
    laser_b_2 = Node("LaserB", is_functional=True, is_up=True)
    laser_a_2 = Node("LaserA", is_functional=True, is_up=True)
    end_b = Node("END", is_functional=False)
    
    nodes_b = {start_b, laser_b_2, laser_a_2, end_b}
    edges_b = {(start_b, laser_b_2), (laser_b_2, laser_a_2), (laser_b_2, end_b), (laser_a_2, end_b)}
    
    colors_b = {"blue"}
    coloring_b = {e: {"blue"} for e in edges_b}
    
    satellite_b = CRBD(nodes_b, edges_b, start_b, end_b, colors_b, coloring_b)

    system = satellite_a // satellite_b

    # 4. Print the resulting topology
    print("\nGlobal System Architecture:")
    print(system)

    # 6. Draw the graph with Graphviz
    system.draw(filename="my_system_crbd", view=True)
