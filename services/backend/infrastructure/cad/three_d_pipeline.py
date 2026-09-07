import base64
import json
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ...logger import logger

# ── Engineering material defaults (used when STEP surface has no colour) ──────
_DEFAULT_GRAY = (192, 192, 192)   # light steel gray
_UNSET_COLOR  = (0, 0, 0, 0)      # gmsh sentinel for "no colour assigned"


class ThreeDPipeline:
    """
    Ingests and parses 3D engineering models (.step, .stp, .iges, .igs, .icd, .sldprt, .sldasm).

    Key behaviours
    ──────────────
    • SolidWorks .sldprt / .sldasm files are silently converted to STEP via COM.
    • iCAD SX .icd files are converted to STEP via ICD2STP.exe (if licensed)
      or a pre-exported .stp companion is used as fallback.
    • Geometry is tessellated with gmsh (OCC kernel).
    • Per-surface STEP colours are extracted via gmsh.model.getColor().
    • One glTF 2.0 primitive + PBR material is emitted per unique colour group
      so the frontend can render the model in its original iCAD colour scheme.
    • All geometry is centred + normalised to a unit-scale bounding box so the
      frontend camera-fitter always frames the model correctly.
    • Transition STEP files generated in background conversion are unlinked immediately.
    """

    @staticmethod
    def parse_and_convert(file_path: Path) -> Tuple[Dict[str, Any], bytes]:
        """
        Returns:
            metadata : dict of extracted physical / topological attributes.
            gltf_bytes: UTF-8 encoded, self-contained glTF 2.0 JSON document.
        """
        logger.info(f"Parsing 3D CAD model file: {file_path}")

        filename  = file_path.name
        ext       = file_path.suffix.lower()
        file_size = file_path.stat().st_size

        temp_cleanup_paths = []

        try:
            # ── 1. SolidWorks native binary → STEP (Silent COM automation / Companion Fallback) ── #
            if ext in (".sldprt", ".sldasm"):
                companion_step = None
                for step_ext in (".step", ".stp", ".STEP", ".STP"):
                    candidate = file_path.with_suffix(step_ext)
                    if candidate.exists():
                        companion_step = candidate
                        break

                if companion_step:
                    logger.info(f"Found pre-converted STEP companion for SolidWorks file: {companion_step}")
                    file_path = companion_step
                    ext       = companion_step.suffix.lower()
                    filename  = companion_step.name
                    file_size = companion_step.stat().st_size
                else:
                    try:
                        from .sw_converter import SolidWorksConverter
                        temp_step = SolidWorksConverter.convert_to_step(file_path)
                        if temp_step.exists():
                            temp_cleanup_paths.append(temp_step)
                            file_path = temp_step
                            ext       = temp_step.suffix.lower()
                            filename  = temp_step.name
                            file_size = temp_step.stat().st_size
                    except Exception as sw_ex:
                        logger.error(f"SolidWorks direct ingestion conversion failed: {sw_ex}")
                        raise

            # ── 1.2. iCAD SX proprietary binary → STEP ────────────────────── #
            elif ext == ".icd":
                import subprocess
                icd2stp_exe = Path("C:/ICADSX/bin/ICD2STP.exe")

                # Strategy A: pre-existing STEP companion next to the ICD
                companion_step = None
                for step_ext in (".step", ".stp", ".STEP", ".STP"):
                    candidate = file_path.with_suffix(step_ext)
                    if candidate.exists():
                        companion_step = candidate
                        break

                if companion_step:
                    logger.info(f"Found pre-converted STEP companion: {companion_step}")
                    file_path = companion_step
                    ext       = companion_step.suffix.lower()
                    filename  = companion_step.name
                    file_size = companion_step.stat().st_size

                elif icd2stp_exe.exists():
                    output_step = file_path.with_suffix(".step")
                    logger.info(f"Invoking ICD2STP.exe: {icd2stp_exe} → {output_step}")
                    try:
                        res = subprocess.run(
                            [str(icd2stp_exe), str(file_path), str(output_step)],
                            capture_output=True, text=True, timeout=30,
                            cwd=str(icd2stp_exe.parent)
                        )
                        if output_step.exists():
                            logger.info(f"iCAD → STEP conversion OK: {output_step}")
                            file_path = output_step
                            ext       = ".step"
                            filename  = output_step.name
                            file_size = output_step.stat().st_size
                        elif res.returncode == 102:
                            logger.warning(
                                "ICD2STP.exe exit 102: batch-STEP licence not active. "
                                "gmsh will attempt direct .icd parse as fallback."
                            )
                        else:
                            logger.error(
                                f"ICD2STP.exe exit {res.returncode}. "
                                f"Stderr: {res.stderr[:200]}"
                            )
                    except subprocess.TimeoutExpired:
                        logger.error("ICD2STP.exe timed out after 30 s.")
                    except Exception as ex:
                        logger.error(f"ICD2STP.exe execution failed: {ex}")
                else:
                    logger.warning("ICD2STP.exe not found. Attempting gmsh direct parse.")

            # ── 2. Tessellate with gmsh + extract per-surface colours ─────── #
            face_count   = 0
            volume       = 0.0
            surface_area = 0.0
            bounds_min   = [0.0, 0.0, 0.0]
            bounds_max   = [0.0, 0.0, 0.0]

            # Each entry: {'verts': [x,y,z,...], 'indices': [i,...]}
            color_groups: Dict[Tuple[int, int, int], Dict[str, List]] = {}
            total_triangles = 0

            import gmsh

            try:
                gmsh.initialize(interruptible=False)
                gmsh.option.setNumber("General.Terminal", 0)
                gmsh.option.setNumber("Mesh.Algorithm", 6)          # Frontal-Delaunay
                gmsh.option.setNumber("Mesh.MeshSizeFactor", 5.0)   # Optimize for fast & light WebGL rendering
                gmsh.option.setNumber("Mesh.CharacteristicLengthFactor", 5.0)
                gmsh.option.setNumber("Mesh.AngleSmoothNormals", 30.0)

                gmsh.merge(str(file_path.absolute()))
                gmsh.model.occ.synchronize()

                vols  = gmsh.model.occ.getEntities(3)
                surfs = gmsh.model.occ.getEntities(2)
                face_count = len(surfs)

                # Bounding box & volume
                if vols:
                    vol_tag = vols[0][1]
                    try:
                        volume = float(gmsh.model.occ.getMass(3, vol_tag))
                    except Exception:
                        volume = 0.0
                    try:
                        bb = gmsh.model.occ.getBoundingBox(3, vol_tag)
                        bounds_min = [bb[0], bb[1], bb[2]]
                        bounds_max = [bb[3], bb[4], bb[5]]
                    except Exception:
                        pass
                elif surfs:
                    all_bb = [gmsh.model.occ.getBoundingBox(2, s[1]) for s in surfs]
                    bounds_min = [min(b[0] for b in all_bb),
                                  min(b[1] for b in all_bb),
                                  min(b[2] for b in all_bb)]
                    bounds_max = [max(b[3] for b in all_bb),
                                  max(b[4] for b in all_bb),
                                  max(b[5] for b in all_bb)]

                try:
                    surface_area = sum(gmsh.model.occ.getMass(2, s[1]) for s in surfs)
                except Exception:
                    surface_area = 0.0

                # Generate surface mesh
                gmsh.model.mesh.generate(2)
                gmsh.model.mesh.removeDuplicateNodes()

                # Global node lookup
                node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
                coord_arr  = list(node_coords)
                tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}

                # ── Per-surface triangle extraction with colour ─────────────
                for _dim, surf_tag in surfs:
                    # Read STEP colour for this surface
                    try:
                        r, g, b, a = gmsh.model.getColor(2, surf_tag)
                        # (0,0,0,0) → gmsh "unset"; treat as default gray
                        if (r, g, b, a) == (0, 0, 0, 0):
                            r, g, b = _DEFAULT_GRAY
                    except Exception:
                        r, g, b = _DEFAULT_GRAY

                    color_key = (int(r), int(g), int(b))
                    if color_key not in color_groups:
                        color_groups[color_key] = {"verts": [], "indices": []}

                    group = color_groups[color_key]

                    try:
                        etypes, _, ntags_list = gmsh.model.mesh.getElements(2, surf_tag)
                    except Exception:
                        continue

                    for etype, ntags in zip(etypes, ntags_list):
                        if int(etype) != 2:  # only 3-node triangles
                            continue
                        n_tris = len(ntags) // 3
                        total_triangles += n_tris
                        for t in range(n_tris):
                            for k in range(3):
                                gt  = int(ntags[t * 3 + k])
                                li  = tag_to_idx.get(gt, 0)
                                gx  = coord_arr[li * 3 + 0]
                                gy  = coord_arr[li * 3 + 1]
                                gz  = coord_arr[li * 3 + 2]
                                vi  = len(group["verts"]) // 3
                                group["verts"].extend([gx, gy, gz])
                                group["indices"].append(vi)

                logger.info(
                    f"gmsh tessellation: {face_count} surfaces, "
                    f"{total_triangles} triangles, "
                    f"{len(color_groups)} colour groups"
                )

            except Exception as e:
                logger.error(f"gmsh error for {filename}: {e}", exc_info=True)
                color_groups = {}
            finally:
                try:
                    gmsh.finalize()
                except Exception:
                    pass

            # ── 3. Fallback geometry if tessellation produced nothing ─────── #
            if not color_groups:
                logger.warning(f"No geometry from {filename}. Using fallback box.")
                fv = [
                    -0.5,-0.5, 0.5,  0.5,-0.5, 0.5,  0.5, 0.5, 0.5,
                    -0.5,-0.5, 0.5,  0.5, 0.5, 0.5, -0.5, 0.5, 0.5,
                     0.5,-0.5,-0.5, -0.5,-0.5,-0.5, -0.5, 0.5,-0.5,
                     0.5,-0.5,-0.5, -0.5, 0.5,-0.5,  0.5, 0.5,-0.5,
                    -0.5,-0.5,-0.5, -0.5,-0.5, 0.5, -0.5, 0.5, 0.5,
                    -0.5,-0.5,-0.5, -0.5, 0.5, 0.5, -0.5, 0.5,-0.5,
                     0.5,-0.5, 0.5,  0.5,-0.5,-0.5,  0.5, 0.5,-0.5,
                     0.5,-0.5, 0.5,  0.5, 0.5,-0.5,  0.5, 0.5, 0.5,
                    -0.5, 0.5, 0.5,  0.5, 0.5, 0.5,  0.5, 0.5,-0.5,
                    -0.5, 0.5, 0.5,  0.5, 0.5,-0.5, -0.5, 0.5,-0.5,
                    -0.5,-0.5,-0.5,  0.5,-0.5,-0.5,  0.5,-0.5, 0.5,
                    -0.5,-0.5,-0.5,  0.5,-0.5, 0.5, -0.5,-0.5, 0.5,
                ]
                color_groups[_DEFAULT_GRAY] = {"verts": fv, "indices": list(range(36))}
                face_count   = face_count or 12
                bounds_min   = [-0.5, -0.5, -0.5]
                bounds_max   = [ 0.5,  0.5,  0.5]

            # ── 4. Compute global centroid + scale (applied to ALL groups) ── #
            all_verts_flat: List[float] = []
            for g in color_groups.values():
                all_verts_flat.extend(g["verts"])

            xs = all_verts_flat[0::3]
            ys = all_verts_flat[1::3]
            zs = all_verts_flat[2::3]

            cx    = (min(xs) + max(xs)) / 2.0
            cy    = (min(ys) + max(ys)) / 2.0
            cz    = (min(zs) + max(zs)) / 2.0
            span  = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs))
            scale = (2.0 / span) if span > 1e-9 else 1.0

            def _normalise(verts: List[float]) -> List[float]:
                n = len(verts) // 3
                out: List[float] = []
                for i in range(n):
                    out.append((verts[i*3+0] - cx) * scale)
                    out.append((verts[i*3+1] - cy) * scale)
                    out.append((verts[i*3+2] - cz) * scale)
                return out

            for g in color_groups.values():
                g["norm_verts"] = _normalise(g["verts"])

            # ── 5. Build combined binary buffer & glTF arrays ─────────────── #
            buffer_chunks: List[bytes] = []
            buffer_offset = 0

            gltf_buffer_views: List[dict] = []
            gltf_accessors:    List[dict] = []
            gltf_materials:    List[dict] = []
            gltf_primitives:   List[dict] = []

            total_verts = 0

            for (r, g, b), group in color_groups.items():
                norm_v  = group["norm_verts"]
                indices = group["indices"]
                n_v     = len(norm_v) // 3
                n_i     = len(indices)
                total_verts += n_v

                if n_v == 0 or n_i == 0:
                    continue

                # -- Vertex bytes (FLOAT32) --
                vert_bytes  = struct.pack(f"{n_v * 3}f", *norm_v)
                vb_len      = len(vert_bytes)
                pad_v       = b"\x00" * ((4 - vb_len % 4) % 4)

                # -- Index bytes (UINT32) --
                idx_bytes   = struct.pack(f"{n_i}I", *indices)
                ib_len      = len(idx_bytes)
                pad_i       = b"\x00" * ((4 - ib_len % 4) % 4)

                chunk = vert_bytes + pad_v + idx_bytes + pad_i
                buffer_chunks.append(chunk)

                bv_vert_idx = len(gltf_buffer_views)
                gltf_buffer_views.append({
                    "buffer":     0,
                    "byteOffset": buffer_offset,
                    "byteLength": vb_len,
                    "target":     34962,  # ARRAY_BUFFER
                })

                bv_idx_idx = len(gltf_buffer_views)
                gltf_buffer_views.append({
                    "buffer":     0,
                    "byteOffset": buffer_offset + vb_len + len(pad_v),
                    "byteLength": ib_len,
                    "target":     34963,  # ELEMENT_ARRAY_BUFFER
                })

                # POSITION accessor
                acc_pos_idx = len(gltf_accessors)
                pmin = [min(norm_v[0::3]), min(norm_v[1::3]), min(norm_v[2::3])]
                pmax = [max(norm_v[0::3]), max(norm_v[1::3]), max(norm_v[2::3])]
                gltf_accessors.append({
                    "bufferView":    bv_vert_idx,
                    "byteOffset":    0,
                    "componentType": 5126,    # FLOAT
                    "count":         n_v,
                    "type":          "VEC3",
                    "min":           [round(v, 6) for v in pmin],
                    "max":           [round(v, 6) for v in pmax],
                })

                # INDEX accessor
                acc_idx_idx = len(gltf_accessors)
                gltf_accessors.append({
                    "bufferView":    bv_idx_idx,
                    "byteOffset":    0,
                    "componentType": 5125,    # UNSIGNED_INT
                    "count":         n_i,
                    "type":          "SCALAR",
                })

                # PBR material with STEP colour
                mat_idx = len(gltf_materials)
                rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
                # Darken very-bright whites slightly so they look metallic not plastic
                luminance = 0.299 * rf + 0.587 * gf + 0.114 * bf
                roughness = 0.5 if luminance < 0.7 else 0.4
                metalness = 0.35

                gltf_materials.append({
                    "name": f"mat_r{r}_g{g}_b{b}",
                    "pbrMetallicRoughness": {
                        "baseColorFactor":       [round(rf, 4), round(gf, 4), round(bf, 4), 1.0],
                        "metallicFactor":        metalness,
                        "roughnessFactor":       roughness,
                    },
                    "doubleSided": True,
                })

                gltf_primitives.append({
                    "attributes": {"POSITION": acc_pos_idx},
                    "indices":    acc_idx_idx,
                    "material":   mat_idx,
                    "mode":       4,   # TRIANGLES
                })

                buffer_offset += len(chunk)

            # Concatenate all chunks into one buffer
            total_buffer = b"".join(buffer_chunks)
            buf_b64      = base64.b64encode(total_buffer).decode("ascii")

            # ── 6. Assemble glTF 2.0 document ─────────────────────────────── #
            gltf = {
                "asset":  {"version": "2.0", "generator": "KMTI-AI-2D-Checker ThreeDPipeline"},
                "scene":  0,
                "scenes": [{"nodes": [0]}],
                "nodes":  [{"mesh": 0}],
                "meshes": [{"name": filename, "primitives": gltf_primitives}],
                "accessors":   gltf_accessors,
                "bufferViews": gltf_buffer_views,
                "materials":   gltf_materials,
                "buffers": [{
                    "byteLength": len(total_buffer),
                    "uri": f"data:application/octet-stream;base64,{buf_b64}",
                }],
            }

            gltf_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")

            # ── 7. Metadata ────────────────────────────────────────────────── #
            n_tris = total_triangles or (sum(len(g["indices"]) for g in color_groups.values()) // 3)
            if face_count == 0:
                face_count = n_tris

            # Volume and surface area were previously invented as `face_count * 1423.5`
            # and `face_count * 312.4` whenever the OCC kernel reported zero. Those are
            # engineering quantities a user could reasonably act on -- fabricating them
            # is worse than not having them. Report None so the absence is visible
            # rather than dressed up as a measurement.
            if volume == 0.0:
                logger.warning(f"Volume unavailable for {filename}; the geometry kernel reported zero.")
                volume = None
            if surface_area == 0.0:
                logger.warning(f"Surface area unavailable for {filename}; the geometry kernel reported zero.")
                surface_area = None

            metadata: Dict[str, Any] = {
                "file_name":        filename,
                "format":           ext.lstrip("."),
                "file_size_bytes":  file_size,
                "face_count":       face_count,
                "volume_mm3":       volume,
                "surface_area_mm2": surface_area,
                "bounds_min":       bounds_min,
                "bounds_max":       bounds_max,
                "measurement":      1,
                "acad_version":     "3D_STANDARD_BREP",
                "triangle_count":   n_tris,
                "vertex_count":     total_verts,
                "color_groups":     len(color_groups),
            }

            logger.info(
                f"glTF 2.0 complete for {filename}: {face_count} faces, "
                f"{n_tris} triangles, {total_verts} vertices, "
                f"{len(color_groups)} colour groups, "
                f"{len(gltf_bytes)//1024} kB."
            )
            return metadata, gltf_bytes

        finally:
            # ── 8. Immediate Clean-up of converted transition STEP files ── #
            for p in temp_cleanup_paths:
                if p.exists():
                    try:
                        p.unlink()
                        logger.info(f"Cleaned up transition STEP file: {p.name}")
                    except Exception as clean_err:
                        logger.warning(f"Failed to delete transition STEP file {p.name}: {clean_err}")
