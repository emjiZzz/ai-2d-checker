import base64
import json
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ...logger import logger

# ── Engineering material defaults (used when STEP surface has no colour) ──────
_DEFAULT_GRAY = (214, 218, 224)   # light machined engineering steel gray
_UNSET_COLOR  = (0, 0, 0, 0)      # gmsh sentinel for "no colour assigned"


class ThreeDConversionError(RuntimeError):
    """A model could not be read, so no mesh exists to return.

    Raised rather than substituting geometry. The caller decides what a failure means -- for
    an .icd it is a legitimate outcome, since the file may hold only a 2D drawing.
    """


#: A 31 MB assembly took minutes; the old 30s ceiling failed every real model.
ICD2STP_TIMEOUT_S = 900

#: MAN/3d_trans.pdf 6-3-4. Kept so a failure names itself instead of printing a bare number.
_ICD2STP_EXIT_MEANING = {
    0: "normal",
    4: "partially converted",
    8: "conversion failed",
    101: "bad arguments",
    102: "bad input or output file specification",
}


def _pack_glb(gltf: Dict[str, Any], binary: bytes) -> bytes:
    """A glTF document and its buffer, as one GLB container.

    Layout is the spec's: a 12-byte header, then length-prefixed chunks. Both chunks are
    padded to a 4-byte boundary -- JSON with spaces, binary with zeros -- because a reader
    is entitled to assume alignment and will reject the file otherwise.
    """
    json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    bin_chunk = binary + b"\x00" * ((4 - len(binary) % 4) % 4)

    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, total)          # 'glTF', version 2, length
    out += struct.pack("<II", len(json_chunk), 0x4E4F534A)    # chunk 0: 'JSON'
    out += json_chunk
    out += struct.pack("<II", len(bin_chunk), 0x004E4942)     # chunk 1: 'BIN\x00'
    out += bin_chunk
    return bytes(out)


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
            gltf_bytes: a self-contained binary glTF 2.0 (GLB) document.
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
                    # `-o` takes the path WITHOUT an extension; the converter appends `.stp`.
                    # The flags are documented as taking their value with no separating space
                    # (MAN/3d_trans.pdf 6-3-1), and passing the paths positionally instead is
                    # what produced exit 102 on every call this ever made. That was read as a
                    # licence failure and is not one -- 102 is "input or output file
                    # specification is incorrect", i.e. the arguments. Parasolid and STEP
                    # import/export are standard features, not licensed options (ibid. 164).
                    # Absolute, because the converter runs with `cwd` set to its own bin
                    # directory: a relative path resolves against C:\ICADSX\bin, is not found
                    # there, and comes back as exit 102 -- the same confusing argument error
                    # this branch already exists to explain. The manual asks for a full path
                    # from the drive letter (MAN/3d_trans.pdf 6-3-2).
                    file_path = file_path.resolve()
                    stem = file_path.with_suffix("")
                    output_step = file_path.with_suffix(".stp")
                    logger.info(f"Invoking ICD2STP.exe: {icd2stp_exe} → {output_step}")
                    try:
                        res = subprocess.run(
                            [str(icd2stp_exe), "-ls", f"-i{file_path}", f"-o{stem}"],
                            capture_output=True, text=True, timeout=ICD2STP_TIMEOUT_S,
                            cwd=str(icd2stp_exe.parent)
                        )
                        # 0 normal, 4 partial (output still written), 8 conversion failed,
                        # 101 bad arguments, 102 bad input/output file specification.
                        if res.returncode == 4:
                            logger.warning(
                                f"ICD2STP.exe exit 4: some geometry in {filename} could not be "
                                "converted. The STEP output is partial."
                            )
                        elif res.returncode not in (0, 4):
                            raise ThreeDConversionError(
                                f"ICD2STP.exe exit {res.returncode} "
                                f"({_ICD2STP_EXIT_MEANING.get(res.returncode, 'unknown')}) "
                                f"for {filename}. Stderr: {res.stderr[:200]}"
                            )
                        if not output_step.exists():
                            raise ThreeDConversionError(
                                f"ICD2STP.exe reported exit {res.returncode} but wrote no STEP "
                                f"file for {filename}."
                            )
                        logger.info(f"iCAD → STEP conversion OK: {output_step}")
                        # Written beside the source, which is the uploads directory. Registered
                        # for cleanup because every .icd now produces one: a 6 MB drawing left a
                        # 31 MB STEP behind, and nothing else would ever remove it.
                        temp_cleanup_paths.append(output_step)
                        file_path = output_step
                        ext       = ".stp"
                        filename  = output_step.name
                        file_size = output_step.stat().st_size
                    except subprocess.TimeoutExpired as exc:
                        raise ThreeDConversionError(
                            f"ICD2STP.exe timed out after {ICD2STP_TIMEOUT_S}s on {filename}."
                        ) from exc
                    except ThreeDConversionError:
                        raise
                    except Exception as ex:
                        raise ThreeDConversionError(
                            f"ICD2STP.exe execution failed for {filename}: {ex}"
                        ) from ex
                else:
                    # gmsh cannot read .icd -- it is a proprietary binary and the parse fails
                    # with a syntax error. Saying so beats letting it fail downstream.
                    raise ThreeDConversionError(
                        f"ICD2STP.exe not found at {icd2stp_exe}. An .icd cannot be read "
                        "without it; gmsh has no reader for the format."
                    )

            # ── 2. Tessellate with gmsh + extract per-surface colours ─────── #
            face_count   = 0
            volume       = 0.0
            surface_area = 0.0
            bounds_min   = [0.0, 0.0, 0.0]
            bounds_max   = [0.0, 0.0, 0.0]

            # Each entry: {'verts': [x,y,z,...], 'indices': [i,...]}
            # Keyed by (part index, colour). The part is what the viewer toggles; the
            # colour still separates primitives within a part, since one part can carry
            # differently coloured surfaces.
            color_groups: Dict[Tuple[int, Tuple[int, int, int]], Dict[str, List]] = {}
            parts: List[Dict[str, Any]] = []
            total_triangles = 0

            import gmsh

            try:
                gmsh.initialize(interruptible=False)
                gmsh.option.setNumber("General.Terminal", 0)
                gmsh.option.setNumber("Mesh.Algorithm", 6)          # Frontal-Delaunay
                gmsh.option.setNumber("Mesh.MeshSizeFactor", 0.9)   # High-fidelity CAD curve tessellation
                gmsh.option.setNumber("Mesh.CharacteristicLengthFactor", 0.9)
                gmsh.option.setNumber("Mesh.MinimumCirclePoints", 36.0) # Smooth circles (default was 7 = heptagon!)
                gmsh.option.setNumber("Mesh.MinimumCurvePoints", 12.0)
                gmsh.option.setNumber("Mesh.AngleSmoothNormals", 35.0)

                gmsh.merge(str(file_path.absolute()))
                gmsh.model.occ.synchronize()

                vols  = gmsh.model.occ.getEntities(3)
                surfs = gmsh.model.occ.getEntities(2)
                face_count = len(surfs)

                # Which part each surface belongs to.
                #
                # A STEP exported from an .icd keeps its assembly structure: gmsh reports one
                # volume per part, named with its path -- `Shapes/M745246A01//2.3x700x711`,
                # matching iCAD's own tree. Grouping triangles by colour alone merged every part
                # into one blob, because they are all the same steel grey.
                #
                # Names repeat: two `φ9×204` are two instances of one part, not a duplicate, so
                # the index rather than the name identifies a row.
                surface_part: dict[int, int] = {}
                for part_index, (_vdim, vtag) in enumerate(vols):
                    try:
                        raw = gmsh.model.getEntityName(3, vtag) or ""
                    except Exception:
                        raw = ""
                    label = raw.rsplit("/", 1)[-1] or f"Part {part_index + 1}"
                    try:
                        part_volume = float(gmsh.model.occ.getMass(3, vtag))
                    except Exception:
                        part_volume = 0.0
                    try:
                        bnd = gmsh.model.getBoundary(
                            [(3, vtag)], oriented=False, recursive=False
                        )
                    except Exception:
                        bnd = []
                    for _sdim, stag in bnd:
                        surface_part[abs(int(stag))] = part_index
                    parts.append({
                        "index": part_index,
                        "name": label,
                        "surfaces": len(bnd),
                        "volume_mm3": part_volume or None,
                        "triangles": 0,
                    })

                # Bounding box & volume, over the WHOLE assembly.
                #
                # Both were read off `vols[0]` -- one part standing in for all nine, so a model's
                # reported volume was whichever part the kernel happened to list first and its
                # bounds framed that part alone.
                if vols:
                    volume = sum(p["volume_mm3"] or 0.0 for p in parts)
                    boxes = []
                    for _vdim, vtag in vols:
                        try:
                            boxes.append(gmsh.model.occ.getBoundingBox(3, vtag))
                        except Exception:
                            pass
                    if boxes:
                        bounds_min = [min(b[i] for b in boxes) for i in (0, 1, 2)]
                        bounds_max = [max(b[i] for b in boxes) for i in (3, 4, 5)]
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

                # Extract true CAD material colours (copper, manganese, colored holes, etc.) from STEP AP214/AP203 styles
                step_face_colors = ThreeDPipeline._extract_step_surface_colors(file_path)

                # ── Per-surface triangle extraction with colour ─────────────
                for _dim, surf_tag in surfs:
                    # Read STEP colour for this surface
                    step_col = step_face_colors.get(surf_tag)
                    if step_col:
                        r = int(round(step_col[0] * 255.0))
                        g = int(round(step_col[1] * 255.0))
                        b = int(round(step_col[2] * 255.0))
                        if (r, g, b) == (255, 255, 255) or max(r, g, b) < 15:
                            r, g, b = _DEFAULT_GRAY
                    else:
                        try:
                            r, g, b, a = gmsh.model.getColor(2, surf_tag)
                            # (0,0,0,0), (0,0,0,255) or pure black → gmsh "unset" or untinted CAD surface; treat as default steel gray
                            if (r, g, b) == (0, 0, 0) or (r, g, b, a) in ((0, 0, 0, 0), (0, 0, 0, 255)) or max(r, g, b) < 15:
                                r, g, b = _DEFAULT_GRAY
                        except Exception:
                            r, g, b = _DEFAULT_GRAY

                    part_index = surface_part.get(int(surf_tag), 0)
                    group_key = (part_index, (int(r), int(g), int(b)))
                    if group_key not in color_groups:
                        color_groups[group_key] = {"verts": [], "indices": []}

                    group = color_groups[group_key]

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

            # ── 3. Tessellation produced nothing ──────────────────────────── #
            #
            # This used to substitute a 1x1x1 box and return it as a successful conversion,
            # with `face_count: 12` and `acad_version: 3D_STANDARD_BREP` -- indistinguishable
            # from a real 12-face model. A 6 MB assembly and a 440 KB drawing produced
            # byte-identical 1.6 KB glTF cubes and both reported success.
            #
            # Volume and surface area were fixed the same way one layer down, and the reason
            # given there applies here in full: fabricating an engineering quantity a user
            # could act on is worse than not having it. Geometry is the same kind of claim.
            if not color_groups:
                raise ThreeDConversionError(
                    f"No geometry could be tessellated from {filename}. The file may hold no "
                    "solid model, or the kernel could not read it."
                )

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

            # One glTF NODE per part, each holding that part's primitives. The viewer toggles
            # a node by name, so a part must not be split across nodes nor merged with another.
            part_primitives: Dict[int, List[dict]] = defaultdict(list)

            for (part_index, (r, g, b)), group in color_groups.items():
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

                part_primitives[part_index].append({
                    "attributes": {"POSITION": acc_pos_idx},
                    "indices":    acc_idx_idx,
                    "material":   mat_idx,
                    "mode":       4,   # TRIANGLES
                })
                if 0 <= part_index < len(parts):
                    parts[part_index]["triangles"] += n_i // 3

                buffer_offset += len(chunk)

            # A node and a mesh per part, named so the client can address one. Parts with no
            # geometry are skipped rather than emitted empty -- an entry the viewer can toggle
            # but never see is worse than no entry.
            gltf_nodes:  List[dict] = []
            gltf_meshes: List[dict] = []
            emitted_parts: List[dict] = []
            for part in parts:
                prims = part_primitives.get(part["index"])
                if not prims:
                    continue
                name = part["name"]
                gltf_meshes.append({"name": name, "primitives": prims})
                gltf_nodes.append({"name": name, "mesh": len(gltf_meshes) - 1})
                part["node"] = len(gltf_nodes) - 1
                emitted_parts.append(part)

            # A model with no assembly structure (a lone solid, or a STEP without products)
            # still needs one node, or the scene is empty.
            if not gltf_nodes:
                flat = [pr for prims in part_primitives.values() for pr in prims]
                gltf_meshes.append({"name": filename, "primitives": flat})
                gltf_nodes.append({"name": filename, "mesh": 0})

            # Concatenate all chunks into one buffer
            total_buffer = b"".join(buffer_chunks)
            # ── 6. Assemble glTF 2.0, as GLB ──────────────────────────────── #
            #
            # Binary container rather than JSON with a base64 `uri`. Base64 inflates the
            # vertex buffer by a third for nothing -- measured on a 12-part assembly, 11.52 MB
            # of an 11.53 MB document was the encoded buffer, and the same model as GLB is
            # 8.65 MB. The client needs no change: GLTFLoader identifies a document by its
            # magic bytes, so it reads both, and the .gltf files already written stay readable.
            gltf = {
                "asset":  {"version": "2.0", "generator": "KMTI-AI-2D-Checker ThreeDPipeline"},
                "scene":  0,
                "scenes": [{"nodes": list(range(len(gltf_nodes)))}],
                "nodes":  gltf_nodes,
                "meshes": gltf_meshes,
                "accessors":   gltf_accessors,
                "bufferViews": gltf_buffer_views,
                "materials":   gltf_materials,
                # No `uri`: in a GLB the buffer is the binary chunk that follows.
                "buffers": [{"byteLength": len(total_buffer)}],
            }

            gltf_bytes = _pack_glb(gltf, total_buffer)

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
                # The assembly, so the client can list its parts without parsing the glTF.
                # `node` addresses the glTF node; `name` is iCAD's own part label and REPEATS
                # across instances, so a row is identified by index, never by name.
                "parts": [
                    {
                        "index":      pt["index"],
                        "node":       pt["node"],
                        "name":       pt["name"],
                        "surfaces":   pt["surfaces"],
                        "triangles":  pt["triangles"],
                        "volume_mm3": pt["volume_mm3"],
                    }
                    for pt in emitted_parts
                ],
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

    @staticmethod
    def _extract_step_surface_colors(step_path: Path) -> Dict[int, Tuple[float, float, float]]:
        """Parses STEP AP214/AP203 presentation styles to extract true per-surface RGB colours.

        iCAD SX, SolidWorks, and other CAD modelers assign specific material colours
        (e.g., copper, manganese, steel, green boreholes) to individual ADVANCED_FACE entities.
        OpenCASCADE's reader often fails to surface these through gmsh.model.getColor(),
        so reading the standard ISO 10303-21 STYLED_ITEM entities directly recovers the exact
        RGB values intended by the engineer.
        """
        if not step_path.exists() or step_path.suffix.lower() not in (".stp", ".step"):
            return {}
        try:
            import re
            text = step_path.read_text(encoding="latin-1")
            entity_map = {}
            for match in re.finditer(r"#(\d+)\s*=\s*([^;]+);", text):
                entity_map[int(match.group(1))] = match.group(2).strip()

            shell_faces = []
            for eid, content in entity_map.items():
                if "CLOSED_SHELL" in content or "OPEN_SHELL" in content:
                    m = re.search(r"SHELL\s*\(\s*\'[^\']*\'\s*,\s*\(([^\)]+)\)\s*\)", content)
                    if m:
                        shell_faces.extend([int(x.replace("#", "").strip()) for x in m.group(1).split(",")])

            def resolve_color(style_id: int):
                visited = set()
                curr = [style_id]
                while curr:
                    nid = curr.pop(0)
                    if nid in visited:
                        continue
                    visited.add(nid)
                    content = entity_map.get(nid, "")
                    if "COLOUR_RGB" in content:
                        m = re.search(
                            r"COLOUR_RGB\s*\(\s*\'[^\']*\'\s*,\s*([eE\d\.\+\-]+)\s*,\s*([eE\d\.\+\-]+)\s*,\s*([eE\d\.\+\-]+)\s*\)",
                            content,
                        )
                        if m:
                            return (float(m.group(1)), float(m.group(2)), float(m.group(3)))
                    refs = [int(x) for x in re.findall(r"#(\d+)", content)]
                    curr.extend(refs)
                return None

            face_color_map = {}
            for eid, content in entity_map.items():
                if content.startswith("STYLED_ITEM"):
                    m = re.search(r"STYLED_ITEM\s*\(\s*\'[^\']*\'\s*,\s*\(([^\)]+)\)\s*,\s*#(\d+)\s*\)", content)
                    if m:
                        sids = [int(x.replace("#", "").strip()) for x in m.group(1).split(",")]
                        target_id = int(m.group(2))
                        for sid in sids:
                            col = resolve_color(sid)
                            if col:
                                face_color_map[target_id] = col
                                break

            colors_by_face_index = {}
            for idx, fid in enumerate(shell_faces):
                if fid in face_color_map:
                    colors_by_face_index[idx + 1] = face_color_map[fid]
            return colors_by_face_index
        except Exception as e:
            logger.debug(f"Failed to parse STEP surface colors directly: {e}")
            return {}

