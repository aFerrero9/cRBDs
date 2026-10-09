from rbd import Node, RBD
from crbd import CRBD
from parser import CRBDParser

if __name__ == "__main__":
    satelliteA = CRBDParser.parse_file('satelliteA.txt')
    satelliteB = CRBDParser.parse_file('satelliteB.txt')

    parallel = satelliteA // satelliteB

    print(parallel)
    parallel.draw(filename="satellites_parallel", show=True)
    parallel.to_logic_formula(t=100, filename="satellites_parallel.wcnf")