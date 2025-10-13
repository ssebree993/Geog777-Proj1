# ==========================================================
# Geog 777 - Project 1 Spatial Analysis Backend
# Projection + IDW + Zonal + OLS + Moran’s I
# Author: Sonja Sebree — Fall 2025
# ==========================================================

import arcpy, os, time, traceback
from arcpy import sa

# ----------------------------------------------------------
# CONSTANTS / ENVIRONMENT
# ----------------------------------------------------------
GDB_PATH       = r"C:\temp\T4\AGM\AGM.gdb"
PROJECT_PATH   = r"C:\temp\T4\AGM\AGM.aprx"
RESULTS_FOLDER = r"C:\temp\T4\images"
SR_WI_TM       = arcpy.SpatialReference(3071)   # Wisconsin Transverse Mercator

arcpy.CheckOutExtension("Spatial")
arcpy.env.workspace = GDB_PATH
arcpy.env.overwriteOutput = True

# ----------------------------------------------------------
# UTILITIES
# ----------------------------------------------------------
def retry_if_fails(func, max_retries=3, delay_sec=2, *args, **kwargs):
    """Retry a function if a transient or schema lock error occurs."""
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except arcpy.ExecuteError as e:
            if "Cannot get exclusive schema lock" in str(e) and attempt < max_retries:
                print(f"[retry_if_fails] Schema lock, retrying ({attempt})...")
                time.sleep(delay_sec)
                continue
            raise

def clear_workspace_cache():
    """Release locks from the geodatabase."""
    try:
        arcpy.management.ClearWorkspaceCache(GDB_PATH)
    except Exception as e:
        print(f"[clear_workspace_cache] Warning: {e}")

# ----------------------------------------------------------
# DATA PREPARATION
# ----------------------------------------------------------
def project_to_gdb(src_path, name_in_gdb):
    """Copy & project shapefile into the GDB (WTM 3071)."""
    dst = os.path.join(GDB_PATH, name_in_gdb)
    temp_copy = os.path.join(GDB_PATH, f"{name_in_gdb}_raw")
    desc = arcpy.Describe(src_path)
    sr_src = desc.spatialReference

    if not arcpy.Exists(temp_copy):
        arcpy.management.CopyFeatures(src_path, temp_copy)

    if not sr_src or sr_src.name != SR_WI_TM.name:
        arcpy.management.Project(temp_copy, dst, SR_WI_TM)
        print(f"[project_to_gdb] Projected → {dst}")
    else:
        arcpy.management.CopyFeatures(temp_copy, dst)
        print(f"[project_to_gdb] Copied → {dst}")
    return dst

def prepare_inputs():
    """Prepare all source shapefiles (copy + project → GDB)."""
    wells_src   = r"C:\temp\T4\data\well_nitrate.shp"
    tracts_src  = r"C:\temp\T4\data\cancer_tracts.shp"
    counties_src= r"C:\temp\T4\data\cancer_county.shp"

    wells_gdb   = project_to_gdb(wells_src,   "wells_proj")
    tracts_gdb  = project_to_gdb(tracts_src,  "tracts_proj")
    counties_gdb= project_to_gdb(counties_src,"counties_proj")
    return wells_gdb, tracts_gdb, counties_gdb

# ----------------------------------------------------------
# IDW INTERPOLATION
# ----------------------------------------------------------
def idw(wells, counties, k):
    """Run IDW interpolation, update map & layout."""
    arcpy.env.workspace = GDB_PATH
    arcpy.env.outputCoordinateSystem = SR_WI_TM
    arcpy.env.extent = counties
    arcpy.env.mask = counties
    arcpy.env.overwriteOutput = True

    z_field = "nitr_ran"
    power   = float(k)
    out_name = f"idwWellNit_{str(k).replace('.', '_')}"

    print(f"[idw] Running IDW for k = {k}")
    out_ras = sa.Idw(wells, z_field, power=power)
    out_ras.save(out_name)

    aprx = arcpy.mp.ArcGISProject(PROJECT_PATH)
    idw_map = aprx.listMaps("IDW")[0]
    idw_layer = idw_map.listLayers("IDW_Well_Nitrates")[0]
    cp = idw_layer.connectionProperties.copy()
    cp['dataset'] = out_name
    idw_layer.updateConnectionProperties(idw_layer.connectionProperties, cp)

    idw_layout = aprx.listLayouts("idwWellNit_LO")[0]
    title = idw_layout.listElements('TEXT_ELEMENT', 'idwTitle')[0]
    title.text = f"Inverse Distance Weighting for k = {k}"
    idw_layout.exportToPNG(fr"{RESULTS_FOLDER}\IDW_{k}.png")

    if not aprx.isReadOnly:
        aprx.save()
    del aprx
    print(f"[idw] ✅ Completed for k = {k}")
    return out_name

# ----------------------------------------------------------
# ZONAL STATISTICS
# ----------------------------------------------------------
def zonalStats(tracts, idw_ras, k):
    """Compute mean nitrate per tract (with projection match)."""
    arcpy.env.workspace = GDB_PATH
    arcpy.env.outputCoordinateSystem = SR_WI_TM
    arcpy.env.overwriteOutput = True

    zone_field = "GEOID10"
    stats_table = f"statsTable_{str(k).replace('.', '_')}"
    idw_path = os.path.join(GDB_PATH, idw_ras)

    print(f"[zonalStats] Zone: {tracts}")
    print(f"[zonalStats] Raster: {idw_path}")
    print(f"[zonalStats] Zone SR: {arcpy.Describe(tracts).spatialReference.name}")
    print(f"[zonalStats] Raster SR: {arcpy.Describe(idw_path).spatialReference.name}")

    retry_if_fails(
        arcpy.sa.ZonalStatisticsAsTable,
        3, 2,
        in_zone_data=tracts,
        zone_field=zone_field,
        in_value_raster=idw_path,
        out_table=stats_table,
        ignore_nodata="DATA",
        statistics_type="MEAN"
    )

    temp_layer = "tempTract"
    new_field = "meanNit"
    out_fc = f"tractsMeanNit_{str(k).replace('.', '_')}"
    join_field = zone_field

    arcpy.management.MakeFeatureLayer(tracts, temp_layer)
    arcpy.management.AddJoin(temp_layer, join_field, stats_table, join_field)
    retry_if_fails(arcpy.management.AddField, 3, 2, tracts, new_field, "DOUBLE")
    retry_if_fails(arcpy.management.CalculateField, 3, 2,
                   temp_layer, new_field, f"!{stats_table}.MEAN!", "PYTHON3")
    arcpy.management.RemoveJoin(temp_layer, stats_table)
    retry_if_fails(arcpy.management.CopyFeatures, 3, 2, temp_layer, out_fc)
    clear_workspace_cache()
    print(f"[zonalStats] ✅ Completed for k = {k}")
    return out_fc

# ----------------------------------------------------------
# OLS REGRESSION (auto-detect layout fix)
# ----------------------------------------------------------
def ols(tracts_mean, k):
    """Run OLS regression, detect layout dynamically, export PNG & PDF."""
    arcpy.env.workspace = GDB_PATH
    arcpy.env.outputCoordinateSystem = SR_WI_TM
    arcpy.env.overwriteOutput = True

    in_fc = tracts_mean
    unique_id = "FIDint"
    out_name = f"ols_{str(k).replace('.', '_')}"
    dep, exp = "canrate", "meanNit"
    report_pdf = fr"{RESULTS_FOLDER}\olsReport_{k}.pdf"

    # Ensure ID field
    if unique_id not in [f.name for f in arcpy.ListFields(in_fc)]:
        arcpy.management.AddField(in_fc, unique_id, "LONG")
        arcpy.management.CalculateField(in_fc, unique_id, "!OBJECTID!", "PYTHON3")

    print(f"[ols] Running OLS for k = {k}")
    arcpy.stats.OrdinaryLeastSquares(
        in_fc, unique_id, out_name, dep, exp,
        Output_Report_File=report_pdf
    )

    aprx = arcpy.mp.ArcGISProject(PROJECT_PATH)

    # --- Map detection ---
    ols_maps = aprx.listMaps("OLS") or [m for m in aprx.listMaps() if "OLS" in m.name]
    if not ols_maps:
        raise RuntimeError(f"❌ No OLS map found. Maps: {[m.name for m in aprx.listMaps()]}")
    ols_map = ols_maps[0]
    print(f"[ols] Using map: {ols_map.name}")

    # --- Layer update ---
    ols_layer = None
    for lyr in ols_map.listLayers():
        if "OrdinaryLeastSquares" in lyr.name:
            ols_layer = lyr
            break
    if not ols_layer:
        raise RuntimeError(f"❌ OLS layer not found in {ols_map.name}. Layers: {[lyr.name for lyr in ols_map.listLayers()]}")
    cp = ols_layer.connectionProperties.copy()
    cp["dataset"] = out_name
    ols_layer.updateConnectionProperties(ols_layer.connectionProperties, cp)

    # --- Layout detection (robust) ---
    print(f"[ols] Available layouts: {[l.name for l in aprx.listLayouts()]}")
    ols_layouts = aprx.listLayouts("OLS_LO") or [l for l in aprx.listLayouts() if "OLS" in l.name]
    if not ols_layouts:
        raise RuntimeError(f"❌ No OLS layout found. Available: {[l.name for l in aprx.listLayouts()]}")
    ols_layout = ols_layouts[0]
    print(f"[ols] Using layout: {ols_layout.name}")

    # --- Update title text dynamically ---
    title_elements = ols_layout.listElements("TEXT_ELEMENT")
    title_el = next((el for el in title_elements if "ols" in el.name.lower()), None)
    if title_el:
        title_el.text = f"Ordinary Least Squares for k = {k}"
        layout_width = ols_layout.pageWidth
        title_el.elementWidth = len(title_el.text) * 4.5
        title_el.elementPositionX = (layout_width - title_el.elementWidth) / 2
    else:
        print("[ols] ⚠️ No title element found; skipping title update.")

    # --- Export layout ---
    export_path = fr"{RESULTS_FOLDER}\OLS_{k}.png"
    ols_layout.exportToPNG(export_path)
    print(f"[ols] Exported → {export_path}")

    if not aprx.isReadOnly:
        aprx.save()
    del aprx
    print(f"[ols] ✅ Completed OLS for k = {k}")
    return out_name

# ----------------------------------------------------------
# MORAN’S I
# ----------------------------------------------------------
def morans(ols_fc, k):
    """Run Moran’s I and return HTML report path."""
    arcpy.env.workspace = GDB_PATH
    arcpy.env.outputCoordinateSystem = SR_WI_TM

    print(f"[morans] Running Moran’s I for k = {k}")
    result = arcpy.stats.SpatialAutocorrelation(
        ols_fc,
        "StdResid",
        "GENERATE_REPORT",
        "INVERSE_DISTANCE",
        "EUCLIDEAN_DISTANCE",
        "ROW"
    )
    report = result.getOutput(3)
    print(f"[morans] ✅ Done for k = {k}")
    return report
# ==========================================================