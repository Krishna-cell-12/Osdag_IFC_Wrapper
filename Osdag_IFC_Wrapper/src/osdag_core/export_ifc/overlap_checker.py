"""
IFC Overlap Detection (AABB)

Runs a basic Axis-Aligned Bounding Box (AABB) check to flag structural elements that might be colliding.
Dumps the findings into `Pset_OsdagOverlapDetection` so it's visible in Revit/BIM viewers.
"""

import numpy as np


class BoundingBox:
    """Axis-Aligned Bounding Box (AABB) for overlap detection."""

    def __init__(self, min_pt, max_pt):
        """
        :param min_pt: (x_min, y_min, z_min)
        :param max_pt: (x_max, y_max, z_max)
        """
        self.min_pt = np.array(min_pt, dtype=float)
        self.max_pt = np.array(max_pt, dtype=float)

    def intersects(self, other):
        """Check if this AABB intersects with another AABB."""
        return (
            self.min_pt[0] <= other.max_pt[0] and
            self.max_pt[0] >= other.min_pt[0] and
            self.min_pt[1] <= other.max_pt[1] and
            self.max_pt[1] >= other.min_pt[1] and
            self.min_pt[2] <= other.max_pt[2] and
            self.max_pt[2] >= other.min_pt[2]
        )

    def intersection_volume(self, other):
        """
        Compute the volume of intersection between two AABBs.
        Returns 0 if they do not intersect.
        """
        if not self.intersects(other):
            return 0.0

        overlap = np.maximum(
            np.minimum(self.max_pt, other.max_pt) -
            np.maximum(self.min_pt, other.min_pt),
            0.0
        )
        return float(np.prod(overlap))

    @property
    def volume(self):
        """Volume of this bounding box."""
        dims = self.max_pt - self.min_pt
        return float(np.prod(np.maximum(dims, 0.0)))

    def __repr__(self):
        return (f"BoundingBox(min={self.min_pt.tolist()}, "
                f"max={self.max_pt.tolist()})")


class OverlapChecker:
    """
    Checks for overlapping structural members in Osdag CAD models.

    Uses bounding box approximations computed from Osdag component
    geometry attributes (origin, dimensions, directions).
    """

    # Minimum overlap volume (mm^3) to report as significant
    MIN_OVERLAP_VOLUME = 1.0

    def __init__(self):
        self.elements = []  # List of (name, BoundingBox, osdag_obj)
        self.overlaps = []  # List of (name1, name2, volume)

    def add_element(self, name, osdag_obj):
        """
        Compute and register the bounding box for an Osdag CAD component.

        :param name: Human-readable name of the element
        :param osdag_obj: Osdag component with geometry attributes
        """
        bbox = self._compute_bbox(osdag_obj)
        if bbox is not None:
            self.elements.append((name, bbox, osdag_obj))

    def check_all_overlaps(self):
        """
        Perform pairwise AABB intersection tests among all registered
        elements. Returns a list of overlap tuples.

        :returns: List of (elem1_name, elem2_name, overlap_volume_mm3)
        """
        self.overlaps = []
        n = len(self.elements)
        for i in range(n):
            for j in range(i + 1, n):
                name_i, bbox_i, _ = self.elements[i]
                name_j, bbox_j, _ = self.elements[j]

                vol = bbox_i.intersection_volume(bbox_j)
                if vol > self.MIN_OVERLAP_VOLUME:
                    self.overlaps.append((name_i, name_j, vol))

        return self.overlaps

    def get_overlap_report(self):
        """
        Generate a human-readable overlap report.

        :returns: String report of detected overlaps
        """
        if not self.overlaps:
            self.check_all_overlaps()

        if not self.overlaps:
            return "No overlapping members detected."

        lines = [
            f"Overlap Detection Report",
            f"{'=' * 60}",
            f"Total elements checked: {len(self.elements)}",
            f"Overlaps found: {len(self.overlaps)}",
            f"{'=' * 60}",
        ]

        for i, (n1, n2, vol) in enumerate(self.overlaps, 1):
            lines.append(
                f"  {i}. {n1} ↔ {n2}: "
                f"overlap volume = {vol:.2f} mm³"
            )

        return "\n".join(lines)

    def annotate_ifc(self, ifc_exporter):
        """
        Write overlap data as property set annotations on the IFC
        project element. Uses Pset for IFC2X3 compatibility.

        :param ifc_exporter: OsdagIfcExporter instance
        """
        if not self.overlaps:
            return

        ifc_file = ifc_exporter.ifc_file
        props = []

        for i, (n1, n2, vol) in enumerate(self.overlaps, 1):
            label = f"Overlap_{i}"
            value = f"{n1} intersects {n2} (volume={vol:.1f} mm3)"
            prop = ifc_file.createIfcPropertySingleValue(
                label, label,
                ifc_file.createIfcLabel(value),
                None
            )
            props.append(prop)

        count_prop = ifc_file.createIfcPropertySingleValue(
            "OverlapCount", "OverlapCount",
            ifc_file.createIfcInteger(len(self.overlaps)),
            None
        )
        props.insert(0, count_prop)

        pset = ifc_file.createIfcPropertySet(
            GlobalId=ifc_exporter.generate_guid(),
            OwnerHistory=ifc_exporter.owner_history,
            Name="Pset_OsdagOverlapDetection",
            HasProperties=props
        )

        ifc_file.createIfcRelDefinesByProperties(
            GlobalId=ifc_exporter.generate_guid(),
            OwnerHistory=ifc_exporter.owner_history,
            RelatingPropertyDefinition=pset,
            RelatedObjects=[ifc_exporter.project]
        )

    @staticmethod
    def _compute_bbox(osdag_obj):
        """
        Compute an AABB from an Osdag component's geometry attributes.

        Handles multiple component types by examining available attributes:
        - ISection, Channel: Uses D, B, length/L and origin + directions
        - Plate: Uses L, W, T and origin
        - Bolt/Nut/Washer: Uses nominal diameter and height
        """
        origin = np.array(
            getattr(osdag_obj, 'sec_origin',
                    getattr(osdag_obj, 'origin', None)),
            dtype=float
        ) if getattr(osdag_obj, 'sec_origin',
                     getattr(osdag_obj, 'origin', None)) is not None \
            else None

        if origin is None:
            return None

        obj_class = getattr(osdag_obj, '_class_name',
                            type(osdag_obj).__name__)

        # Collect all possible dimensions
        dims = []
        for attr in ['D', 'B', 'length', 'L', 'W', 'H', 'T',
                     'Hst', 'Lst', 'A', 'h', 'b']:
            val = getattr(osdag_obj, attr, None)
            if val is not None:
                try:
                    dims.append(float(val))
                except (ValueError, TypeError):
                    pass

        if not dims:
            return None

        # Use the 3 largest dimensions as the bounding box half-extents
        dims.sort(reverse=True)
        half_x = dims[0] / 2.0 if len(dims) > 0 else 10
        half_y = dims[1] / 2.0 if len(dims) > 1 else half_x
        half_z = dims[2] / 2.0 if len(dims) > 2 else half_y

        # Apply direction vectors if available
        u_dir = np.array(
            getattr(osdag_obj, 'uDir', [1, 0, 0]), dtype=float
        )
        w_dir = np.array(
            getattr(osdag_obj, 'wDir', [0, 0, 1]), dtype=float
        )
        v_dir = np.cross(w_dir, u_dir)

        # Compute the 8 corners of the oriented bounding box
        corners = []
        for sx in [-1, 1]:
            for sy in [-1, 1]:
                for sz in [-1, 1]:
                    corner = (origin +
                              sx * half_x * u_dir +
                              sy * half_y * v_dir +
                              sz * half_z * w_dir)
                    corners.append(corner)

        corners = np.array(corners)
        min_pt = corners.min(axis=0)
        max_pt = corners.max(axis=0)

        return BoundingBox(min_pt, max_pt)
