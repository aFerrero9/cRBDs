import argparse
import sys
import os
import subprocess
from rbd import Node, RBD
from crbd import CRBD
from parser import CRBDParser

def run_gpmc(wcnf_filepath: str):
    command = ["./solvers/gpmc", "--mode", "wmc", wcnf_filepath]
    
    print(f"\n--- Running GPMC ---")
    print(f"Command: {' '.join(command)}")
    
    try:
        # Execute the subprocess
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print("\n=== Raw solver output: ===")
        print(result.stdout)
        print("\n=== Reliability Results ===")
        
        for line in result.stdout.splitlines():
            # Look for the line containing the exact calculation
            if line.startswith("c s exact arb prec-sci"):
                # Split by spaces and take the last string 
                value_str = line.split()[-1]
                failure_prob = float(value_str)
                prob_percentage = failure_prob * 100
                
                print(f"System failure probability: {prob_percentage}%")
                break
        
    except subprocess.CalledProcessError as e:
        print("\nError running GPMC.")
        print(f"Error details:\n{e.stderr}")

    except FileNotFoundError:
        print("\nError: GPMC executable not found.")
 

def main():
    # Set up the argument parser
    parser = argparse.ArgumentParser(description="Parse and validate RBDs/cRBDs from a text file.")
    parser.add_argument(
        "filepath", 
        type=str, 
        help="Path to the .txt file containing the system/s topology."
    )

    parser.add_argument(
        "t", 
        type=float, 
        help="Mission time t"
    )
    
    args = parser.parse_args()
    filepath = args.filepath

    time = args.t

    # Check if the file actually exists before parsing
    if not os.path.exists(filepath):
        print(f"Error: The file '{filepath}' was not found.")
        sys.exit(1)
        
    print(f"=== PARSING FILE: {filepath} ===")
    file_name = filepath.split('/')[-1].split('.')[0]
    
    try:
        system = CRBDParser.multiple_parse_file(filepath)
        system.draw(filename=file_name)
        
    except Exception as e:
        # Show validation errors
        print(f"\nPARSER ERROR: {e}")
        sys.exit(1)

    system.to_logic_formula(t=time, filename=f"{file_name}.wcnf")
    
    # Run the solver on the generated file
    run_gpmc(f"wmc_files/{file_name}.wcnf")


if __name__ == "__main__":
    main()