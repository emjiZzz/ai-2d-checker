import gmsh
import sys

gmsh.initialize(sys.argv)
gmsh.option.setNumber("General.Terminal", 1)

try:
    gmsh.merge("C:/Users/Enduser/Downloads/test.step") # wait, I don't have a test step file. Let's just create a cylinder to test gltf export
except Exception:
    pass

gmsh.model.occ.addCylinder(0, 0, 0, 10, 0, 0, 2)
gmsh.model.occ.synchronize()
gmsh.model.mesh.generate(2)

gmsh.write("test_mesh.stl")
gmsh.write("test_mesh.obj")
try:
    gmsh.write("test_mesh.gltf")
except Exception as e:
    print(f"Error writing gltf: {e}")

gmsh.finalize()
