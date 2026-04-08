Osdag IFC Export Enhancements
This document outlines the recent updates to the IFC export pipeline. The goal was to move away from basic .brep geometry dumps and implement a proper parametric IFC generation pipeline that integrates well with BIM software, specifically Revit for BoQ (Bill of Quantities) extraction.

Features & Changes
1. Coordinate Systems (Global & Local)
Previously, elements lacked proper relative placement. I've added a global origin (0,0,0) and implemented module-specific local axis handlers.

Elements now use IfcLocalPlacement tied to IfcAxis2Placement3D.
Currently supports accurate spatial positioning for:
Beam-to-Column End Plate (CADFillet, CADGroove, etc.)
Column-to-Column Cover Plate Welded
Beam-to-Beam Cover Plate Bolted
Tension Member - Bolted to End Gusset
1.1 Critical Fix: Preventing "Double Transformation" / "Exploded View"
Some BIM viewers will show an "exploded" model if the same translation/rotation is applied twice:

once through IfcProduct.ObjectPlacement (via IfcLocalPlacement), and
again inside geometry items (e.g., IfcExtrudedAreaSolid.Position or IfcMappedItem.MappingTarget).
Correct IFC practice (and current implementation):

Geometry is authored in local coordinates (identity / origin).
The full element transform (origin + axis directions) lives only in ObjectPlacement.
This keeps the IFC strictly compliant and avoids viewer-specific double-application of transforms.

2. IFC Viewer Integration
Hooked up ifcopenshell.geom to render generated IFCs directly inside our existing pythonOCC widget.
Added new File menu actions: "Export to IFC" and "Open IFC File".
The viewer parses IfcProduct elements and drops them into the CAD display, color-coding by entity type (Beams get blue, Plates get gold, etc.).
Also added an auto-generation hook so the IFC is built transparently after a successful design run.
3. Overlap Detection
Rolled a custom AABB (Axis-Aligned Bounding Box) collision checker (overlap_checker.py).
It runs during the IFC export process and flags overlapping geometry.
The results are injected into the IFC file via Pset_OsdagOverlapDetection so BIM coordinators can spot clashes during federation.
4. Revit BoQ Support
Heavily updated the metadata mapping. Elements now correctly associate with IfcMaterial via IfcRelAssociatesMaterial.
Added standard buildingSMART property sets (Pset_BeamCommon, Pset_ColumnCommon, Pset_PlateCommon).
Elements are now properly connected via IfcRelConnectsElements.
Note: Kept the default schema at IFC2X3 as Revit's importer still behaves best with it for our structural elements.
Running Tests
Added a test suite to validate the export logic without needing the full GUI. It mocks the CAD objects for the 4 target modules and verifies the IFC hierarchy, placements, and property sets.

cd src/
python -m osdag_core.export_ifc.test_ifc_export
Dependencies
Requires ifcopenshell (needs to be built with OCC support, the pip wheel usually handles this fine on Windows/Linux). If you get import errors viewing IFCs, just run: pip install ifcopenshell

Running the GUI (WSL/Linux)
Osdag GUI requires Qt + OpenCASCADE (pythonOCC). On WSL/Linux, the most reliable setup is via conda-forge.

1) Install Miniforge (local, no sudo)
cd ~
curl -L -o Miniforge3.sh "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
bash Miniforge3.sh -b -p ~/miniforge3
2) Create an environment with OCC + Qt + IFC
MAMBA_NO_LOW_SPEED_LIMIT=1 ~/miniforge3/bin/mamba create -y -n osdag-gui -c conda-forge \
  python=3.11 pythonocc-core pyside6 ifcopenshell numpy pyqt
3) Install Osdag (editable) + runtime Python deps
~/miniforge3/bin/conda run -n osdag-gui python -m pip install -e .
~/miniforge3/bin/conda run -n osdag-gui python -m pip install lark pandas markdown openpyxl
4) Launch the UI
~/miniforge3/bin/conda run -n osdag-gui python -m osdag_gui
If the window does not appear, verify you have GUI forwarding enabled (WSLg or an X server) and that DISPLAY is set.
