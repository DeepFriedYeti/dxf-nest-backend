from fastapi import FastAPI, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from typing import List
import tempfile
import shutil
import os
import ezdxf
from shapely.geometry import Polygon, box
from shapely.affinity import rotate, translate
from shapely import wkt
import svgwrite

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def extract_polygons_from_dxf(file_path):
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()
    polygons = []
    for e in msp.query('LWPOLYLINE LINE ARC CIRCLE'):
        try:
            if e.dxftype() == 'LWPOLYLINE':
                points = [(p[0], p[1]) for p in e.get_points()]
                if len(points) > 2:
                    polygons.append(Polygon(points))
        except:
            pass
    return polygons

def best_fit_nest(polygons, sheet_width, sheet_height, gap, rotation_step):
    sheet = box(0, 0, sheet_width, sheet_height)
    placed = []
    y_offset = gap

    for poly in polygons:
        best_fit = None
        best_area = float('inf')
        for angle in range(0, 360, rotation_step):
            rotated = rotate(poly, angle, origin='centroid', use_radians=False)
            bounds = rotated.bounds
            width = bounds[2] - bounds[0] + gap
            height = bounds[3] - bounds[1] + gap
            x_offset = gap
            while x_offset + width < sheet_width:
                candidate = translate(rotated, xoff=x_offset - bounds[0], yoff=y_offset - bounds[1])
                if sheet.contains(candidate):
                    area = width * height
                    if area < best_area:
                        best_fit = candidate
                        best_area = area
                x_offset += gap
        if best_fit:
            placed.append(best_fit)
            y_offset += best_fit.bounds[3] - best_fit.bounds[1] + gap
    return placed

def polygons_to_dxf(polygons, output_path):
    doc = ezdxf.new()
    msp = doc.modelspace()
    for poly in polygons:
        coords = list(poly.exterior.coords)
        msp.add_lwpolyline(coords, close=True)
    doc.saveas(output_path)

def polygons_to_svg(polygons, sheet_width, sheet_height):
    dwg = svgwrite.Drawing(size=(f"{sheet_width}px", f"{sheet_height}px"))
    for poly in polygons:
        points = [(x, sheet_height - y) for x, y in poly.exterior.coords]  # Flip Y for SVG
        dwg.add(dwg.polygon(points=points, fill='none', stroke='black'))
    return dwg.tostring()

@app.post("/nest")
async def nest(
    files: List[UploadFile] = File(...),
    quantities: List[int] = Form(...),
    sheet_width: float = Form(...),
    sheet_height: float = Form(...),
    gap: float = Form(...),
    rotation_step: int = Form(...),
):
    with tempfile.TemporaryDirectory() as tmpdir:
        all_polygons = []
        for i, file in enumerate(files):
            file_path = os.path.join(tmpdir, file.filename)
            with open(file_path, 'wb') as f:
                shutil.copyfileobj(file.file, f)
            polygons = extract_polygons_from_dxf(file_path)
            all_polygons.extend(polygons * quantities[i])

        nested_polygons = best_fit_nest(all_polygons, sheet_width, sheet_height, gap, rotation_step)
        output_path = os.path.join(tmpdir, 'nested_output.dxf')
        polygons_to_dxf(nested_polygons, output_path)
        return FileResponse(output_path, media_type='application/dxf')

@app.post("/nest_preview")
async def nest_preview(
    files: List[UploadFile] = File(...),
    quantities: List[int] = Form(...),
    sheet_width: float = Form(...),
    sheet_height: float = Form(...),
    gap: float = Form(...),
    rotation_step: int = Form(...),
):
    with tempfile.TemporaryDirectory() as tmpdir:
        all_polygons = []
        for i, file in enumerate(files):
            file_path = os.path.join(tmpdir, file.filename)
            with open(file_path, 'wb') as f:
                shutil.copyfileobj(file.file, f)
            polygons = extract_polygons_from_dxf(file_path)
            all_polygons.extend(polygons * quantities[i])

        nested_polygons = best_fit_nest(all_polygons, sheet_width, sheet_height, gap, rotation_step)
        svg_content = polygons_to_svg(nested_polygons, sheet_width, sheet_height)
        return Response(content=svg_content, media_type="image/svg+xml")