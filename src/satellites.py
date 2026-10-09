from rbd import Node, RBD
from crbd import CRBD
from parser import CRBDParser

if __name__ == "__main__":
    satelliteA = CRBDParser.parse_file('crbd_examples/satelliteA.txt')
    satelliteB = CRBDParser.parse_file('crbd_examples/satelliteB.txt')

    parallel = satelliteA // satelliteB

    print(parallel)
    parallel.draw(filename="satellites_parallel", view=True)
    parallel.to_logic_formula(t=100, filename="satellites_parallel.wcnf")