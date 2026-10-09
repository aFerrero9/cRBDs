# MINITEST
import argparse
import sys
import os
from rbd import Node, RBD
from crbd import CRBD
from parser import CRBDParser

def main():
    # Set up the argument parser
    parser = argparse.ArgumentParser(description="Parse and validate strict RBD/cRBD topologies from a text file.")
    parser.add_argument(
        "filepath", 
        type=str, 
        help="Path to the .txt file containing the system topology."
    )
    
    args = parser.parse_args()
    filepath = args.filepath
    
    # Check if the file actually exists before parsing
    if not os.path.exists(filepath):
        print(f"Error: The file '{filepath}' was not found.")
        sys.exit(1)
        
    print(f"=== PARSING FILE: {filepath} ===")
    
    try:
        # Call your parser
        system = CRBDParser.parse_file(filepath)
        
        # Dynamically check the returned type to print the correct structure
        system_type_name = type(system).__name__
        print(f"System Type successfully loaded: {system_type_name}")
        
        print(system)
            
        # Print extra fields if the system is a cRBD
        if system_type_name == 'CRBD':
            print("\n--- Colors Universe ---")
            print(f"  {system.colors}")

        system.draw()
                
    except Exception as e:
        # Show validation errors
        print(f"\nPARSER ERROR: {e}")
        sys.exit(1)

    if RBD._is_dag(system):
        print("Paths of the graph:")
        graph = {n: [] for n in system.nodes}
        for u, v in system.edges:
            graph[u].append(v)

        all_paths = system._decomposition_lemma(graph, system.start, system.end)
        just_id = [[n.id for n in path] for path in all_paths]
        print(just_id)

    file_name = filepath.split('/')[-1].split('.')[0]
    system.to_logic_formula(t=100, filename=f"{file_name}.wcnf")


if __name__ == "__main__":
    main()