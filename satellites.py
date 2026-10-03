from rbd import Node, RBD
from crbd import CRBD
from parser import RBDParser

if __name__ == "__main__":
    satelliteA = RBDParser.parse_file('satelliteA.txt')
    satelliteB = RBDParser.parse_file('satelliteB.txt')

    parallel = satelliteA // satelliteB

    print(parallel)
    parallel.draw()