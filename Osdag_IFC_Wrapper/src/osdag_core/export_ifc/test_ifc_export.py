"""
Test Script for IFC Export Pipeline

This script validates the IFC generation logic for the 4 core connection modules.
It stubs out the Osdag CAD objects using `SimpleNamespace` and feeds them through
the `OsdagIfcExporter` to make sure we're getting valid IFC data out without needing
to spin up the entire GUI and OCC backend.

Testing focus:
- Valid `IfcProject` structure
- Proper `IfcLocalPlacement` and `IfcAxis2Placement3D` chaining
- BoQ materials (`IfcRelAssociatesMaterial`)
- `Pset` assignments and overlap checkers
"""

import os
import sys
import tempfile
from types import SimpleNamespace

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


def create_mock_isection(name="ISMB 400", length=1000, designation="ISMB 400",
                          material="E 250 (Fe 410 W)A",
                          cls_name="ISection", ifc_name="Steel Beam",
                          origin=None, u_dir=None, w_dir=None):
    """Create a mock ISection-like object with typical attributes."""
    obj = SimpleNamespace()
    obj._class_name = cls_name
    obj.ifc_name = ifc_name
    obj.designation = designation
    obj.material = material
    # Typical ISMB 400 dimensions (mm)
    obj.D = 400.0
    obj.B = 140.0
    obj.T = 16.0    # flange thickness
    obj.t = 8.9     # web thickness
    obj.R1 = 14.0
    obj.R2 = 0.0
    obj.length = float(length)
    obj.L = float(length)
    obj.sec_origin = origin or [0, 0, 0]
    obj.uDir = u_dir or [1, 0, 0]
    obj.wDir = w_dir or [0, 0, 1]
    return obj


def create_mock_plate(name="End Plate", L=500, W=200, T=20,
                       material="E 250 (Fe 410 W)A",
                       origin=None, u_dir=None, w_dir=None):
    """Create a mock Plate object."""
    obj = SimpleNamespace()
    obj._class_name = "Plate"
    obj.ifc_name = name
    obj.L = float(L)
    obj.W = float(W)
    obj.T = float(T)
    obj.material = material
    obj.sec_origin = origin or [0, 200, 250]
    obj.uDir = u_dir or [0, 1, 0]
    obj.wDir = w_dir or [1, 0, 0]
    return obj


def create_mock_bolt(origin=None, u_dir=None):
    """Create a mock Bolt object."""
    obj = SimpleNamespace()
    obj._class_name = "Bolt"
    obj.d = 20.0
    obj.D = 20.0
    obj.l = 80.0
    obj.L = 80.0
    obj.H = 80.0
    obj.r = 10.0
    obj.R = 18.0       # Head radius (for hex head geometry)
    obj.T = 12.5        # Head thickness
    obj.property_class = "8.8"
    obj.type = "Bearing"
    obj.sec_origin = origin or [50, 210, 300]
    obj.origin = origin or [50, 210, 300]
    obj.uDir = u_dir or [0, 1, 0]
    obj.wDir = [0, 0, 1]
    obj.shaftDir = u_dir or [0, 1, 0]
    return obj


def create_mock_weld(origin=None):
    """Create a mock fillet weld object."""
    obj = SimpleNamespace()
    obj._class_name = "FilletWeld"
    obj.L = 100.0
    obj.b = 8.0
    obj.T = 8.0
    obj.h = 100.0
    obj.type = "Fillet"
    obj.designation = "Fillet Weld 8mm"
    obj.sec_origin = origin or [0, 200, 200]
    obj.uDir = [0, 1, 0]
    obj.wDir = [1, 0, 0]
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for Each Target Module
# ─────────────────────────────────────────────────────────────────────────────

def test_bcendplate_export():
    """Test: Beam-to-Column End Plate connection IFC export."""
    print("\n" + "="*70)
    print("TEST 1: Beam-to-Column End Plate (BCEndplate)")
    print("="*70)

    from osdag_core.export_ifc.ifc_generator import OsdagIfcExporter

    with tempfile.NamedTemporaryFile(suffix='.ifc', delete=False) as f:
        ifc_path = f.name

    exporter = OsdagIfcExporter(filename=ifc_path)

    # Column at origin, vertical
    column = create_mock_isection(
        name="ISHB 300", designation="ISHB 300", length=3000,
        cls_name="ISection", ifc_name="Column",
        origin=[0, 0, 0], u_dir=[1, 0, 0], w_dir=[0, 0, 1]
    )
    column.D = 300.0
    column.B = 250.0

    # Beam offset from column face
    beam = create_mock_isection(
        name="ISMB 400", designation="ISMB 400", length=2000,
        cls_name="ISection", ifc_name="Beam",
        origin=[0, 160, 1500], u_dir=[1, 0, 0], w_dir=[0, 1, 0]
    )

    plate = create_mock_plate(
        name="End Plate", L=500, W=200, T=20,
        origin=[-100, 150, 1500], u_dir=[0, 1, 0], w_dir=[1, 0, 0]
    )

    bolts = [
        create_mock_bolt(origin=[50, 155, 1600]),
        create_mock_bolt(origin=[-50, 155, 1600]),
        create_mock_bolt(origin=[50, 155, 1400]),
        create_mock_bolt(origin=[-50, 155, 1400]),
    ]

    welds = [create_mock_weld(origin=[0, 160, 1700])]

    metadata = {
        'ConnectionType': 'Beam-to-Column End Plate',
        'DesignCode': 'IS 800:2007',
        'DesignStatus': 'True',
        'CAD_Class': 'CADGroove',
    }

    exporter.export_connection(
        connection_id="BCEndplate_Test",
        members=[column, beam],
        plates=[plate],
        bolts=bolts,
        welds=welds,
        metadata=metadata,
        cad_class_name="CADGroove"
    )
    exporter.save()

    # Validate
    validate_ifc_file(ifc_path, "BCEndplate")
    os.unlink(ifc_path)


def test_cc_splice_export():
    """Test: Column-to-Column Cover Plate Welded connection."""
    print("\n" + "="*70)
    print("TEST 2: Column-to-Column Cover Plate Welded")
    print("="*70)

    from osdag_core.export_ifc.ifc_generator import OsdagIfcExporter

    with tempfile.NamedTemporaryFile(suffix='.ifc', delete=False) as f:
        ifc_path = f.name

    exporter = OsdagIfcExporter(filename=ifc_path)

    col1 = create_mock_isection(
        designation="ISHB 300", length=3000, ifc_name="Column 1",
        origin=[0, 0, 0], u_dir=[1, 0, 0], w_dir=[0, 0, 1]
    )
    col2 = create_mock_isection(
        designation="ISHB 300", length=3000, ifc_name="Column 2",
        origin=[0, 0, 3000], u_dir=[1, 0, 0], w_dir=[0, 0, 1]
    )

    flange_plate = create_mock_plate(
        name="Flange Cover Plate", L=400, W=250, T=16,
        origin=[-125, -150, 2900]
    )
    web_plate = create_mock_plate(
        name="Web Cover Plate", L=300, W=200, T=12,
        origin=[0, -100, 2900]
    )

    metadata = {
        'ConnectionType': 'Column-to-Column Cover Plate Welded',
        'CAD_Class': 'CCSpliceCoverPlateWeldedCAD',
    }

    welds = [
        create_mock_weld(origin=[0, -150, 3000]),
        create_mock_weld(origin=[0, 150, 3000]),
    ]

    exporter.export_connection(
        connection_id="CCSplice_Test",
        members=[col1, col2],
        plates=[flange_plate, web_plate],
        bolts=[],
        welds=welds,
        metadata=metadata,
        cad_class_name="CCSpliceCoverPlateWeldedCAD"
    )
    exporter.save()

    validate_ifc_file(ifc_path, "CCSplice")
    os.unlink(ifc_path)


def test_bb_coverplate_export():
    """Test: Beam-to-Beam Cover Plate Bolted connection."""
    print("\n" + "="*70)
    print("TEST 3: Beam-to-Beam Cover Plate Bolted")
    print("="*70)

    from osdag_core.export_ifc.ifc_generator import OsdagIfcExporter

    with tempfile.NamedTemporaryFile(suffix='.ifc', delete=False) as f:
        ifc_path = f.name

    exporter = OsdagIfcExporter(filename=ifc_path)

    beam_left = create_mock_isection(
        designation="ISMB 500", length=3000, ifc_name="Beam Left",
        origin=[0, 0, 0], u_dir=[1, 0, 0], w_dir=[0, 1, 0]
    )
    beam_right = create_mock_isection(
        designation="ISMB 500", length=3000, ifc_name="Beam Right",
        origin=[0, 3010, 0], u_dir=[1, 0, 0], w_dir=[0, -1, 0]
    )

    top_plate = create_mock_plate(
        name="Top Flange Cover Plate", L=600, W=200, T=16,
        origin=[-100, 2700, 250]
    )
    bottom_plate = create_mock_plate(
        name="Bottom Flange Cover Plate", L=600, W=200, T=16,
        origin=[-100, 2700, -250]
    )

    bolts = [
        create_mock_bolt(origin=[50, 2800, 260]),
        create_mock_bolt(origin=[-50, 2800, 260]),
        create_mock_bolt(origin=[50, 3200, 260]),
        create_mock_bolt(origin=[-50, 3200, 260]),
    ]

    metadata = {
        'ConnectionType': 'Beam-to-Beam Cover Plate Bolted',
        'CAD_Class': 'BBCoverPlateBoltedCAD',
    }

    exporter.export_connection(
        connection_id="BBCoverPlate_Test",
        members=[beam_left, beam_right],
        plates=[top_plate, bottom_plate],
        bolts=bolts,
        metadata=metadata,
        cad_class_name="BBCoverPlateBoltedCAD"
    )
    exporter.save()

    validate_ifc_file(ifc_path, "BBCoverPlate")
    os.unlink(ifc_path)


def test_tension_member_export():
    """Test: Tension Member - Bolted to End Gusset."""
    print("\n" + "="*70)
    print("TEST 4: Tension Member - Bolted to End Gusset")
    print("="*70)

    from osdag_core.export_ifc.ifc_generator import OsdagIfcExporter

    with tempfile.NamedTemporaryFile(suffix='.ifc', delete=False) as f:
        ifc_path = f.name

    exporter = OsdagIfcExporter(filename=ifc_path)

    member = create_mock_isection(
        designation="ISA 100x100x10", length=2000,
        ifc_name="Tension Member",
        cls_name="Angle",
        origin=[0, 0, 0], u_dir=[1, 0, 0], w_dir=[0, 1, 0]
    )
    member.A = 100.0    # Angle depth (geometry_mapper uses .A for Angle)
    member.D = 100.0
    member.B = 100.0
    member.T = 10.0
    member.t = 10.0

    gusset = create_mock_plate(
        name="Gusset Plate", L=300, W=200, T=12,
        origin=[-100, 2000, 0]
    )

    bolts = [
        create_mock_bolt(origin=[0, 2050, 50]),
        create_mock_bolt(origin=[0, 2050, -50]),
        create_mock_bolt(origin=[0, 2100, 50]),
        create_mock_bolt(origin=[0, 2100, -50]),
    ]

    metadata = {
        'ConnectionType': 'Tension Member - Bolted to End Gusset',
        'CAD_Class': 'TensionAngleBoltCAD',
    }

    exporter.export_connection(
        connection_id="TensionMember_Test",
        members=[member],
        plates=[gusset],
        bolts=bolts,
        metadata=metadata,
        cad_class_name="TensionAngleBoltCAD"
    )
    exporter.save()

    validate_ifc_file(ifc_path, "TensionMember")
    os.unlink(ifc_path)


# ─────────────────────────────────────────────────────────────────────────────
# IFC Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_ifc_file(ifc_path, test_name):
    """
    Validate the structure and contents of a generated IFC file.
    """
    import ifcopenshell

    print(f"\n--- Validating {test_name} IFC File ---")
    ifc = ifcopenshell.open(ifc_path)

    errors = []
    warnings = []

    # 1. Check project hierarchy
    projects = ifc.by_type("IfcProject")
    if len(projects) != 1:
        errors.append(f"Expected 1 IfcProject, found {len(projects)}")
    else:
        print(f"  ✓ IfcProject: {projects[0].Name}")

    sites = ifc.by_type("IfcSite")
    if len(sites) != 1:
        errors.append(f"Expected 1 IfcSite, found {len(sites)}")
    else:
        print(f"  ✓ IfcSite: {sites[0].Name}")

    buildings = ifc.by_type("IfcBuilding")
    if len(buildings) != 1:
        errors.append(f"Expected 1 IfcBuilding, found {len(buildings)}")
    else:
        print(f"  ✓ IfcBuilding: {buildings[0].Name}")

    storeys = ifc.by_type("IfcBuildingStorey")
    if len(storeys) != 1:
        errors.append(f"Expected 1 IfcBuildingStorey, found {len(storeys)}")
    else:
        print(f"  ✓ IfcBuildingStorey: {storeys[0].Name}")

    # 2. Check elements
    beams = ifc.by_type("IfcBeam")
    columns = ifc.by_type("IfcColumn")
    plates = ifc.by_type("IfcPlate")
    fasteners = ifc.by_type("IfcFastener")
    assemblies = ifc.by_type("IfcElementAssembly")

    print(f"  ✓ Elements: {len(beams)} beams, {len(columns)} columns, "
          f"{len(plates)} plates, {len(fasteners)} fasteners")
    print(f"  ✓ Assemblies: {len(assemblies)}")

    # 3. Check local placements
    products_without_placement = []
    products_with_placement = 0
    for product in ifc.by_type("IfcProduct"):
        if product.is_a("IfcProject") or product.is_a("IfcSite"):
            continue
        if hasattr(product, 'ObjectPlacement') and product.ObjectPlacement:
            products_with_placement += 1
        else:
            products_without_placement.append(
                f"{product.is_a()}:{product.Name}")

    print(f"  ✓ Products with IfcLocalPlacement: {products_with_placement}")
    if products_without_placement:
        warnings.append(f"Products without placement: "
                        f"{products_without_placement[:5]}")

    # 4. Check property sets
    psets = ifc.by_type("IfcPropertySet")
    pset_names = [p.Name for p in psets]
    print(f"  ✓ Property Sets ({len(psets)}): "
          f"{', '.join(set(pset_names))}")

    # 5. Check element quantities
    qtos = ifc.by_type("IfcElementQuantity")
    qto_names = [q.Name for q in qtos]
    print(f"  ✓ Element Quantities ({len(qtos)}): "
          f"{', '.join(set(qto_names))}")

    # 6. Check materials
    materials = ifc.by_type("IfcMaterial")
    mat_assocs = ifc.by_type("IfcRelAssociatesMaterial")
    print(f"  ✓ Materials: {len(materials)}, "
          f"Associations: {len(mat_assocs)}")

    # 7. Check connections
    connections = ifc.by_type("IfcRelConnectsElements")
    print(f"  ✓ IfcRelConnectsElements: {len(connections)}")

    # 8. Check spatial containment
    containment = ifc.by_type("IfcRelContainedInSpatialStructure")
    print(f"  ✓ Spatial Containment: {len(containment)}")

    # 9. Check for axis placement
    placements = ifc.by_type("IfcAxis2Placement3D")
    print(f"  ✓ IfcAxis2Placement3D instances: {len(placements)}")

    # 10. Check for overlap detection annotations
    overlap_psets = [p for p in psets if 'Overlap' in p.Name]
    if overlap_psets:
        print(f"  ✓ Overlap Detection: {len(overlap_psets)} Psets")

    # Summary
    file_size = os.path.getsize(ifc_path)
    print(f"\n  File size: {file_size:,} bytes")

    if errors:
        print(f"\n  ✘ ERRORS ({len(errors)}):")
        for e in errors:
            print(f"    - {e}")
    if warnings:
        print(f"\n  ⚠ WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"    - {w}")
    if not errors:
        print(f"\n  ✓ {test_name} PASSED")
    else:
        print(f"\n  ✘ {test_name} FAILED")

    return len(errors) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("="*70)
    print("  IFC Wrapper Enhancement - Verification Test Suite")
    print("  Testing all 4 target Osdag connection modules")
    print("="*70)

    results = {}

    try:
        test_bcendplate_export()
        results['BCEndplate'] = True
    except Exception as e:
        print(f"  ✘ BCEndplate test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results['BCEndplate'] = False

    try:
        test_cc_splice_export()
        results['CCSplice'] = True
    except Exception as e:
        print(f"  ✘ CCSplice test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results['CCSplice'] = False

    try:
        test_bb_coverplate_export()
        results['BBCoverPlate'] = True
    except Exception as e:
        print(f"  ✘ BBCoverPlate test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results['BBCoverPlate'] = False

    try:
        test_tension_member_export()
        results['TensionMember'] = True
    except Exception as e:
        print(f"  ✘ TensionMember test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results['TensionMember'] = False

    print("\n" + "="*70)
    print("  TEST SUMMARY")
    print("="*70)
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✘ FAIL"
        print(f"  {status} : {name}")

    total = len(results)
    passed_count = sum(1 for v in results.values() if v)
    print(f"\n  {passed_count}/{total} tests passed")
    print("="*70)

    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
