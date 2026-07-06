import gmsh
import sys

gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 1)

gmsh.model.occ.addCylinder(0, 0, 0, 10, 0, 0, 2)
gmsh.model.occ.synchronize()
gmsh.model.mesh.generate(2)

gmsh.write("test_mesh.stl")
gmsh.write("test_mesh.obj")
gmsh.finalize()
