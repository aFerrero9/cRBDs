# MINITEST
import argparse
import sys
import os
from rbd import Node, RBD
from crbd import CRBD
from parser import RBDParser

def main():
    # 1. Set up the argument parser
    parser = argparse.ArgumentParser(description="Parse and validate strict RBD/cRBD topologies from a text file.")
    parser.add_argument(
        "filepath", 
        type=str, 
        help="Path to the .txt file containing the system topology."
    )
    
    args = parser.parse_args()
    filepath = args.filepath
    
    # 2. Check if the file actually exists before parsing
    if not os.path.exists(filepath):
        print(f"Error: The file '{filepath}' was not found.")
        sys.exit(1)
        
    print(f"=== PARSING FILE: {filepath} ===")
    
    try:
        # 3. Call your parser
        system = RBDParser.parse_file(filepath)
        
        # 4. Dynamically check the returned type to print the correct structure
        system_type_name = type(system).__name__
        print(f"System Type successfully loaded: {system_type_name}")
        
        print(system)
            
        # 5. Print extra fields if the system is a cRBD
        if system_type_name == 'CRBD':
            print("\n--- Colors Universe ---")
            print(f"  {system.colors}")

        system.draw()
                
    except Exception as e:
        # Catch and cleanly display your strict validation errors
        print(f"\nPARSER ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()