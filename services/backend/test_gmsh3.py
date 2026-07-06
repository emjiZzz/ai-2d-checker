import subprocess
from pathlib import Path
import gmsh

file_path = Path(r"d:\RAYSAN\ai-2d-checker\services\storage\uploads\ba0d4bbe5bc6cc1c5a7866ee6e2ee08051823d2c4feec72de077ae949ea86155.icd")
output_step = file_path.with_suffix(".step")

print(f"Running ICD2STP on {file_path}")
res = subprocess.run(["C:/ICADSX/bin/ICD2STP.exe", str(file_path), str(output_step)], capture_output=True, text=True)
print(f"ICD2STP finished with exit code {res.returncode}")
print(f"Output step exists: {output_step.exists()}")

if output_step.exists():
    print(f"Running gmsh on {output_step}")
    try:
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.merge(str(output_step.absolute()))
        
        vols = gmsh.model.occ.getEntities(3)
        surfs = gmsh.model.occ.getEntities(2)
        print(f"Vols: {len(vols)}, Surfs: {len(surfs)}")
        
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.generate(2)
        gmsh.write("test_output.stl")
        print("gmsh succeeded.")
    except Exception as e:
        print(f"gmsh failed: {e}")
    finally:
        gmsh.finalize()
