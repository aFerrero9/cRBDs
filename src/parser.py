""" 
File Format Conventions
=======================
The parser reads a plain text file containing exactly three mandatory sections.
Empty lines and lines starting with '#' (comments) are safely ignored.

@SYSTEM
-------
Defines the graph behavior. Must contain exactly one type declaration.
    TYPE = RBD
    TYPE = CRBD

@NODES
------
Declares all nodes in the topology. 
Format: node_id, failure_rate, [not_functional_flag]
    * Defaults: Nodes are functional by default (requires exactly 2 items: id, failure_rate).
    * Non-functional: Require exactly 3 items. Append a flag like 'nf', 'not', 'notfunctional', 'notf', 'nonf', 'false', or 'n' (e.g., `START, 0, nf`).
    * Structural Nodes: The graph strictly requires a START and END node. 
      You may use aliases (e.g., 's', 'inicio', 'e', 'final') ONLY IF accompanied 
      by a non-functional flag (e.g., `s, 0, nf` parses as START). Functional nodes 
      named 's' or 'e' are treated as standard internal nodes.

@TOPOLOGY
---------
Defines directed edges and colors. All nodes MUST be previously declared in @NODES.
    * RBD Format:  u -> v
    * cRBD Format: u -> v : color_1, color_2
    * Tuple Colors (cRBD): To define a tuple as a single color entity, enclose 
      it in parentheses. (e.g., `A -> B : red, (blue, green)` parses as 
      two distinct colors).

RBD format example:
@SYSTEM
TYPE = RBD

@NODES
# id, failure_rate, [not_functional]
([not_functional] if node is non-functional)

@TOPOLOGY
# u -> v

-------------------

cRBD format example:
@SYSTEM
TYPE = CRBD

@NODES
# id, failure_rate, [not_functional]
([not_functional] if node is non-functional)

@TOPOLOGY
# u -> v : color_1, color_2, ...
"""
from rbd import Node, RBD
from crbd import CRBD

class CRBDParser:
    """
    Parser for reading RBD and cRBD topologies from text files.
    """

    @staticmethod
    def _parse_colors(color_string: str) -> set:
        """
        Splits a string by commas, ignoring commas enclosed in parentheses.
        Allows parsing of tuple-colors (e.g., '(red, blue)').
        """
        result = set()
        current = []
        paren_level = 0
        
        for char in color_string:
            if char == '(':
                paren_level += 1
            elif char == ')':
                paren_level -= 1
                
            # Only split if a comma is found and we are not inside parentheses
            if char == ',' and paren_level == 0:
                val = "".join(current).strip()
                if val:
                    result.add(val)
                current = []
            else:
                current.append(char)
                
        # Add the last accumulated fragment
        val = "".join(current).strip()
        if val:
            result.add(val)
            
        return result

    @staticmethod
    def parse_file(filepath: str) -> RBD:
        system_type = None
        nodes_dict = {}
        edges = set()
        colors_set = set()
        coloring = {}
        
        current_section = None

        with open(filepath, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, start=1):
                # Clean whitespaces and ignore empty lines or comments
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Detect section headers to switch the parser state
                if line.startswith('@'):
                    current_section = line.upper()
                    continue
                    
                try:
                    # @SYSTEM
                    if current_section == '@SYSTEM':
                        if line.upper().startswith('TYPE'):
                            parts = line.split('=')
                            if len(parts) == 2:
                                system_type = parts[1].strip().upper()
                                
                    # @NODES
                    elif current_section == '@NODES':
                        parts = [p.strip() for p in line.split(',')]
                        
                        if len(parts) == 2:
                            # Functional node (Exactly 2 items)
                            node_id = parts[0]
                            failure_rate = float(parts[1])
                            is_functional = True
                            
                        elif len(parts) == 3:
                            # Structural/Non-functional node (Exactly 3 items)
                            node_id = parts[0]
                            failure_rate = float(parts[1])
                            flag = parts[2].lower()
                            
                            if flag in ('nf', 'not', 'notfunctional', 'notf', 'nonf', 'false', 'n'):
                                is_functional = False
                                # Resolve aliases for structural nodes
                                if node_id.lower() in ('start', 's', 'inicio', 'source'):
                                    node_id = "START"
                                if node_id.lower() in ('end', 'e', 'final', 'sink'):
                                    node_id = "END"
                            else:
                                raise ValueError(f"Unrecognized non-functional flag '{parts[2]}'. Structural nodes require a valid flag.")
                                
                        else:
                            # Enforce the strict 2 or 3 items rule
                            raise ValueError(f"Invalid format in {parts[0]}. Functional nodes need exactly 2 items, structural nodes need exactly 3. Got {len(parts)}.")
                            
                        # Create the node passing the parsed failure_rate
                        nodes_dict[node_id] = Node(node_id, is_functional=is_functional, is_up=True, failure_rate=failure_rate)
                            
                    # @TOPOLOGY
                    elif current_section == '@TOPOLOGY':
                        if ':' in line:
                            edge_part, colors_part = line.split(':', 1)
                        else:
                            edge_part, colors_part = line, ""
                            
                        if '->' not in edge_part:
                            raise SyntaxError("Missing '->' operator in edge definition.")
                            
                        u_str, v_str = [p.strip() for p in edge_part.split('->')]
                        
                        # Check for different start/end names
                        if u_str not in nodes_dict:
                            if u_str.lower() in ('start', 's', 'inicio', 'source') and "START" in nodes_dict:
                                u_str = "START"
                            elif u_str.lower() in ('end', 'e', 'final', 'sink') and "END" in nodes_dict:
                                u_str = "END"

                        if v_str not in nodes_dict:
                            if v_str.lower() in ('start', 's', 'inicio', 'source') and "START" in nodes_dict:
                                v_str = "START"
                            elif v_str.lower() in ('end', 'e', 'final', 'sink') and "END" in nodes_dict:
                                v_str = "END"
                        
                        # Validaciones estrictas después de resolver los nombres
                        if u_str not in nodes_dict:
                            raise ValueError(f"Node '{u_str}' is used in @TOPOLOGY but was not declared in @NODES.")
                        if v_str not in nodes_dict:
                            raise ValueError(f"Node '{v_str}' is used in @TOPOLOGY but was not declared in @NODES.")
                            
                        u = nodes_dict[u_str]
                        v = nodes_dict[v_str]
                        edge = (u, v)
                        edges.add(edge)
                        
                        if system_type.lower() == 'crbd' and colors_part:
                            edge_colors = CRBDParser._parse_colors(colors_part)
                            colors_set.update(edge_colors)
                            coloring[edge] = edge_colors

                except Exception as e:
                    raise ValueError(f"Error parsing line {line_number} ('{line}'): {e}")

        # Final validation and instantiation
        
        # Ensure structural nodes were created explicitly by the user
        if "START" not in nodes_dict or "END" not in nodes_dict:
            raise ValueError("Topology is missing structural 'START' or 'END' nodes. They must be declared in @NODES.")
            
        start_node = nodes_dict["START"]
        end_node = nodes_dict["END"]
        
        nodes = set(nodes_dict.values())

        if system_type.lower() == 'crbd':
            return CRBD(nodes, edges, start_node, end_node, colors_set, coloring)
        elif system_type.lower() == 'rbd':
            return RBD(nodes, edges, start_node, end_node)
        else:
            raise ValueError(f"Unknown or missing system TYPE: {system_type}. Must be 'RBD' or 'CRBD'.")
