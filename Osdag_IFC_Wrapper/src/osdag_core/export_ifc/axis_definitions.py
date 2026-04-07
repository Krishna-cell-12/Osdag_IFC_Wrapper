"""
IFC Export - Axis Definitions

Sets up local coordinate systems for the Osdag connection modules.
We need this because elements were jumping around in Revit without proper IfcLocalPlacements.

Supported Modules:
    1. Beam-to-Column End Plate
    2. Column-to-Column Cover Plate Welded
    3. Beam-to-Beam Cover Plate Bolted
    4. Tension Member - Bolted to End Gusset

"""

import numpy as np


class AxisDefinitionHandler:
    """
    Base class for module-specific axis definition handlers.
    Creates IFC local placements relative to a global origin for each
    component in a structural connection.
    """

    def __init__(self, ifc_exporter):
        """
        :param ifc_exporter: OsdagIfcExporter instance managing the IFC file.
        """
        self.exporter = ifc_exporter
        self.ifc_file = ifc_exporter.ifc_file

        # Global axis at the world origin
        self.global_placement = self._create_global_axis()

        # Storey placement (parent for all element placements)
        self.storey_placement = self._create_storey_placement()

    def _create_global_axis(self):
        """
        Define the global coordinate system at (0, 0, 0) with standard
        X = (1,0,0), Y = (0,1,0), Z = (0,0,1) directions.

        Returns an IfcAxis2Placement3D representing the world origin.
        """
        origin = self.ifc_file.createIfcCartesianPoint([0.0, 0.0, 0.0])
        z_axis = self.ifc_file.createIfcDirection([0.0, 0.0, 1.0])
        x_axis = self.ifc_file.createIfcDirection([1.0, 0.0, 0.0])

        return self.ifc_file.createIfcAxis2Placement3D(
            Location=origin,
            Axis=z_axis,
            RefDirection=x_axis
        )

    def _create_storey_placement(self):
        """
        Create an IfcLocalPlacement for the building storey.
        All element placements will reference this as their parent.
        """
        return self.ifc_file.createIfcLocalPlacement(
            PlacementRelTo=None,
            RelativePlacement=self.global_placement
        )

    def create_local_placement(self, origin, z_dir=None, x_dir=None,
                                relative_to=None):
        """
        Create an IfcLocalPlacement for a component element.

        :param origin: 3-tuple or numpy array (x, y, z) in mm
        :param z_dir: 3-tuple for the local Z axis (default: global Z)
        :param x_dir: 3-tuple for the local X axis (default: global X)
        :param relative_to: Parent IfcLocalPlacement (default: storey)
        :returns: IfcLocalPlacement entity
        """
        if z_dir is None:
            z_dir = (0.0, 0.0, 1.0)
        if x_dir is None:
            x_dir = (1.0, 0.0, 0.0)
        if relative_to is None:
            relative_to = self.storey_placement

        # Ensure orthogonality
        z_arr = np.array(z_dir, dtype=float)
        x_arr = np.array(x_dir, dtype=float)
        if abs(np.dot(z_arr, x_arr)) > 0.01:
            y_arr = np.cross(z_arr, x_arr)
            y_arr = y_arr / np.linalg.norm(y_arr)
            x_arr = np.cross(y_arr, z_arr)
            x_arr = x_arr / np.linalg.norm(x_arr)

        point = self.ifc_file.createIfcCartesianPoint(
            [float(c) for c in origin]
        )
        axis = self.ifc_file.createIfcDirection(
            [float(c) for c in z_arr]
        )
        ref_dir = self.ifc_file.createIfcDirection(
            [float(c) for c in x_arr]
        )
        axis2placement = self.ifc_file.createIfcAxis2Placement3D(
            Location=point, Axis=axis, RefDirection=ref_dir
        )

        return self.ifc_file.createIfcLocalPlacement(
            PlacementRelTo=relative_to,
            RelativePlacement=axis2placement
        )

    def create_placement_from_osdag_obj(self, osdag_obj, relative_to=None):
        """
        Extract origin, uDir, wDir from an Osdag CAD component and create
        an IfcLocalPlacement.

        :param osdag_obj: Osdag component (ISection, Plate, etc.)
        :param relative_to: Parent placement (default: storey)
        :returns: IfcLocalPlacement
        """
        origin = getattr(osdag_obj, 'sec_origin',
                         getattr(osdag_obj, 'origin', [0, 0, 0]))
        origin = np.array(origin, dtype=float)

        u_dir = np.array(
            getattr(osdag_obj, 'uDir', [1, 0, 0]), dtype=float
        )
        w_dir = np.array(
            getattr(osdag_obj, 'wDir', [0, 0, 1]), dtype=float
        )

        return self.create_local_placement(
            origin=origin, z_dir=w_dir, x_dir=u_dir,
            relative_to=relative_to
        )


class BCEndplateAxisHandler(AxisDefinitionHandler):
    """
    Axis definitions for Beam-to-Column End Plate connection.

    Coordinate system:
        - Column placed at global origin (0, 0, 0), vertical along Z
        - Beam connects at the column face, offset in Y by (D/2 + plate.T)
        - End plate is between column face and beam end
        - Bolts pass through the end plate into the column flange
    """

    def get_element_placements(self, cad_obj):
        """
        Extract placements for all components in a BCEndplate connection.

        :param cad_obj: CADFillet or CADGroove BCEndplate CAD object
        :returns: dict mapping element name to IfcLocalPlacement
        """
        placements = {}

        # Column: at global origin, vertical
        column = getattr(cad_obj, 'column', None)
        if column is not None:
            placements['column'] = self.create_placement_from_osdag_obj(
                column
            )

        # Beam: offset from column face
        beam = getattr(cad_obj, 'beam', None)
        if beam is not None:
            placements['beam'] = self.create_placement_from_osdag_obj(beam)

        # End Plate: between column and beam
        plate = getattr(cad_obj, 'plate', None)
        if plate is not None:
            placements['plate'] = self.create_placement_from_osdag_obj(plate)

        # Continuity plates
        for attr in ['contPlate_L1', 'contPlate_L2',
                     'contPlate_R1', 'contPlate_R2']:
            obj = getattr(cad_obj, attr, None)
            if obj is not None:
                placements[attr] = self.create_placement_from_osdag_obj(obj)

        # Beam stiffeners
        for attr in ['beam_stiffener_1', 'beam_stiffener_2']:
            obj = getattr(cad_obj, attr, None)
            if obj is not None:
                placements[attr] = self.create_placement_from_osdag_obj(obj)

        return placements


class CCSpliceCoverPlateAxisHandler(AxisDefinitionHandler):
    """
    Axis definitions for Column-to-Column Cover Plate Welded connection.

    Coordinate system:
        - Column1 at global origin, vertical along Z
        - Column2 above Column1 at the splice height
        - Cover plates (flange + web) at the splice location
    """

    def get_element_placements(self, cad_obj):
        """
        Extract placements for CC Splice Cover Plate components.
        """
        placements = {}

        # Columns
        for attr in ['column', 'column1', 'column2']:
            obj = getattr(cad_obj, attr, None)
            if obj is not None:
                placements[attr] = self.create_placement_from_osdag_obj(obj)

        # Flange plates
        for attr in ['flangePlate1', 'flangePlate2',
                     'innerFlangePlate1', 'innerFlangePlate2',
                     'innerFlangePlate3', 'innerFlangePlate4']:
            obj = getattr(cad_obj, attr, None)
            if obj is not None:
                placements[attr] = self.create_placement_from_osdag_obj(obj)

        # Web plates
        for attr in ['webPlate1', 'webPlate2']:
            obj = getattr(cad_obj, attr, None)
            if obj is not None:
                placements[attr] = self.create_placement_from_osdag_obj(obj)

        return placements


class BBCoverPlateBoltedAxisHandler(AxisDefinitionHandler):
    """
    Axis definitions for Beam-to-Beam Cover Plate Bolted connection.

    Coordinate system:
        - BeamLeft at global origin, extending in +Y
        - BeamRight mirrored, extending in -Y
        - Cover plates at the splice location
    """

    def get_element_placements(self, cad_obj):
        """
        Extract placements for BB Cover Plate Bolted components.
        """
        placements = {}

        # Beams
        for attr in ['beamLeft', 'beamRight', 'beam1', 'beam2']:
            obj = getattr(cad_obj, attr, None)
            if obj is not None:
                placements[attr] = self.create_placement_from_osdag_obj(obj)

        # Above / Below Flange plates
        for attr in ['plateAbvFlange', 'plateBelwFlange',
                     'WebPlateLeft', 'WebPlateRight',
                     'innerplateAbvFlangeFront',
                     'innerplateAbvFlangeBack',
                     'innerplateBelwFlangeFront',
                     'innerplateBelwFlangeBack']:
            obj = getattr(cad_obj, attr, None)
            if obj is not None:
                placements[attr] = self.create_placement_from_osdag_obj(obj)

        return placements


class TensionMemberAxisHandler(AxisDefinitionHandler):
    """
    Axis definitions for Tension Member - Bolted to End Gusset.

    Coordinate system:
        - Member1 at global origin, extending along its length axis
        - Gusset plate(s) at member end
        - Bolt arrays connecting members to gusset
    """

    def get_element_placements(self, cad_obj):
        """
        Extract placements for Tension Member components.
        """
        placements = {}

        # Members
        for attr in ['member1', 'member2', 'sec']:
            obj = getattr(cad_obj, attr, None)
            if obj is not None:
                placements[attr] = self.create_placement_from_osdag_obj(obj)

        # Gusset / End plates
        for attr in ['plate1', 'plate2']:
            obj = getattr(cad_obj, attr, None)
            if obj is not None:
                placements[attr] = self.create_placement_from_osdag_obj(obj)

        return placements


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher: Maps CAD class names to the correct axis handler
# ─────────────────────────────────────────────────────────────────────────────

AXIS_HANDLER_MAP = {
    # Beam-to-Column End Plate
    'CADFillet': BCEndplateAxisHandler,
    'CADGroove': BCEndplateAxisHandler,
    'CADColWebFillet': BCEndplateAxisHandler,
    'CADcolwebGroove': BCEndplateAxisHandler,

    # Column-to-Column Cover Plate Welded
    'CCSpliceCoverPlateWeldedCAD': CCSpliceCoverPlateAxisHandler,
    'CCSpliceCoverPlateBoltedCAD': CCSpliceCoverPlateAxisHandler,

    # Beam-to-Beam Cover Plate Bolted
    'BBCoverPlateBoltedCAD': BBCoverPlateBoltedAxisHandler,
    'BBSpliceCoverPlateWeldedCAD': BBCoverPlateBoltedAxisHandler,

    # Tension Member
    'TensionAngleBoltCAD': TensionMemberAxisHandler,
    'TensionChannelBoltCAD': TensionMemberAxisHandler,
    'TensionAngleWeldCAD': TensionMemberAxisHandler,
    'TensionChannelWeldCAD': TensionMemberAxisHandler,
}


def get_axis_handler(cad_class_name, ifc_exporter):
    """
    Factory function to get the appropriate axis handler for a CAD class.

    :param cad_class_name: String name of the Osdag CAD class
    :param ifc_exporter: OsdagIfcExporter instance
    :returns: AxisDefinitionHandler subclass instance, or base handler
    """
    handler_cls = AXIS_HANDLER_MAP.get(
        cad_class_name, AxisDefinitionHandler
    )
    return handler_cls(ifc_exporter)
