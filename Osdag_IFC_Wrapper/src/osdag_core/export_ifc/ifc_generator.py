import ifcopenshell
import ifcopenshell.guid
import uuid
import time
import numpy as np

class OsdagIfcExporter:
    """
    Main generator for exporting Osdag 3D models to IFC format.
    Maintains the file structure, project hierarchy, and delegates to the helpers in the module.
    """

    def __init__(self, filename="Osdag_Model.ifc", schema="IFC2X3"):
        """
        Initialize the IFC exporter.
        :param filename: Output path for the IFC file.
        :param schema: IFC schema to use ('IFC2X3' or 'IFC4').
        """
        self.filename = filename
        self.schema = schema
        
        # Initialize an empty IFC file with the chosen schema
        self.ifc_file = ifcopenshell.file(schema=self.schema)
        
        # IFC Header Setup
        self.setup_header()
        
        # Initialize Project Hierarchy
        self.project = None
        self.site = None
        self.building = None
        self.storey = None
        self.setup_project_hierarchy()
        
        # Initialize Mappers
        from .geometry_mapper import GeometryMapper
        from .metadata_mapper import MetadataMapper
        self.geom_mapper = GeometryMapper(self)
        self.meta_mapper = MetadataMapper(self)

        # Axis handler and overlap checker (lazy-initialized per connection)
        self._axis_handler = None
        self._overlap_checker = None

        # Material cache to avoid duplicate IfcMaterial entities
        self._material_cache = {}

    def generate_guid(self, osdag_id=None):
        """
        Generates a 22-character IFC standard GUID.
        If an osdag_id is provided, it can be used to generate a deterministic GUID.
        """
        if osdag_id is not None:
            # Deterministic GUID based on the element's unique Osdag ID
            # Use uuid5 with a namespace to consistently get the same uuid for the same ID
            namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
            element_uuid = uuid.uuid5(namespace, str(osdag_id))
            # Pack uuid to IFC base64
            guid = ifcopenshell.guid.compress(element_uuid.hex)
        else:
            # Random GUID
            guid = ifcopenshell.guid.new()
        return guid

    def setup_header(self):
        """Set up the IFC file header metadata."""
        owner_history = self.ifc_file.createIfcOwnerHistory()
        # To be populated fully in metadata_mapper if needed, but a basic one is required
        # IfcPerson: IFC2X3 uses 'Id', IFC4 renamed it to 'Identification'
        if self.schema == "IFC4":
            person = self.ifc_file.createIfcPerson(
                Identification="OsdagUser", FamilyName="User"
            )
            org = self.ifc_file.createIfcOrganization(
                Identification="Osdag", Name="Osdag"
            )
        else:  # IFC2X3
            person = self.ifc_file.createIfcPerson(
                Id="OsdagUser", FamilyName="User"
            )
            org = self.ifc_file.createIfcOrganization(
                Id="Osdag", Name="Osdag"
            )
        person_and_org = self.ifc_file.createIfcPersonAndOrganization(ThePerson=person, TheOrganization=org)
        
        app = self.ifc_file.createIfcApplication(
            ApplicationDeveloper=org,
            Version="1.0",
            ApplicationFullName="Osdag Structural Design",
            ApplicationIdentifier="OSDAG"
        )
        
        self.owner_history = self.ifc_file.createIfcOwnerHistory(
            OwningUser=person_and_org,
            OwningApplication=app,
            ChangeAction="ADDED",
            CreationDate=int(time.time())
        )

    def setup_project_hierarchy(self):
        """Create the Project -> Site -> Building -> Storey hierarchy."""
        
        # Create Units
        length_unit = self.ifc_file.createIfcSIUnit(
            UnitType="LENGTHUNIT",
            Prefix="MILLI",
            Name="METRE"
        )
        area_unit = self.ifc_file.createIfcSIUnit(
            UnitType="AREAUNIT",
            Name="SQUARE_METRE"
        )
        volume_unit = self.ifc_file.createIfcSIUnit(
            UnitType="VOLUMEUNIT",
            Name="CUBIC_METRE"
        )
        mass_unit = self.ifc_file.createIfcSIUnit(
            UnitType="MASSUNIT",
            Prefix="KILO",
            Name="GRAM"
        )
        angle_unit = self.ifc_file.createIfcSIUnit(
            UnitType="PLANEANGLEUNIT",
            Name="RADIAN"
        )
        unit_assignment = self.ifc_file.createIfcUnitAssignment(
            Units=[length_unit, area_unit, volume_unit, mass_unit, angle_unit]
        )
        
        # Create Project
        self.project = self.ifc_file.createIfcProject(
            GlobalId=self.generate_guid("osdag_project"),
            OwnerHistory=self.owner_history,
            Name="Osdag Connection Design",
            RepresentationContexts=self._create_contexts(),
            UnitsInContext=unit_assignment
        )
        
        # Create Site
        self.site = self.ifc_file.createIfcSite(
            GlobalId=self.generate_guid("osdag_site"),
            OwnerHistory=self.owner_history,
            Name="Site",
            CompositionType="COMPLEX"
        )
        self.ifc_file.createIfcRelAggregates(
            GlobalId=self.generate_guid(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.project,
            RelatedObjects=[self.site]
        )
        
        # Create Building
        self.building = self.ifc_file.createIfcBuilding(
            GlobalId=self.generate_guid("osdag_building"),
            OwnerHistory=self.owner_history,
            Name="Building",
            CompositionType="COMPLEX"
        )
        self.ifc_file.createIfcRelAggregates(
            GlobalId=self.generate_guid(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.site,
            RelatedObjects=[self.building]
        )
        
        # Create Storey
        self.storey = self.ifc_file.createIfcBuildingStorey(
            GlobalId=self.generate_guid("osdag_storey"),
            OwnerHistory=self.owner_history,
            Name="Level 1",
            CompositionType="COMPLEX",
            Elevation=0.0
        )
        self.ifc_file.createIfcRelAggregates(
            GlobalId=self.generate_guid(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.building,
            RelatedObjects=[self.storey]
        )

    def _create_contexts(self):
        """Creates representation contexts for 3D modeling."""
        # 3D Context
        context3d = self.ifc_file.createIfcGeometricRepresentationContext(
            ContextType="Model",
            CoordinateSpaceDimension=3,
            Precision=1e-5,
            WorldCoordinateSystem=self._create_placement(),
            TrueNorth=self._create_direction((0.0, 1.0, 0.0))
        )
        return [context3d]

    def _create_placement(self, point=(0.0, 0.0, 0.0), dir_z=(0.0, 0.0, 1.0), dir_x=(1.0, 0.0, 0.0)):
        """Helper to create Local Placement."""
        point_ifc = self.ifc_file.createIfcCartesianPoint(list(point))
        axis = self.ifc_file.createIfcDirection(list(dir_z))
        ref_dir = self.ifc_file.createIfcDirection(list(dir_x))
        axis2placement = self.ifc_file.createIfcAxis2Placement3D(Location=point_ifc, Axis=axis, RefDirection=ref_dir)
        return axis2placement

    def _create_direction(self, dir_tuple):
        """Helper to create a direction."""
        return self.ifc_file.createIfcDirection(list(dir_tuple))

    def save(self):
        """Save the IFC file to disk."""
        self.ifc_file.write(self.filename)
        print(f"IFC file successfully saved to {self.filename}")

    # ─── Local Placement Infrastructure ────────────────────────────────────

    def create_local_placement(self, origin=(0.0, 0.0, 0.0),
                               dir_z=(0.0, 0.0, 1.0),
                               dir_x=(1.0, 0.0, 0.0),
                               relative_to=None):
        """
        Create an IfcLocalPlacement for element positioning.

        :param origin: (x, y, z) in mm
        :param dir_z: Z-axis direction (element "up")
        :param dir_x: X-axis direction (element "reference")
        :param relative_to: Parent IfcLocalPlacement (defaults to storey)
        :returns: IfcLocalPlacement
        """
        axis2 = self._create_placement(origin, dir_z, dir_x)
        return self.ifc_file.createIfcLocalPlacement(
            PlacementRelTo=relative_to,
            RelativePlacement=axis2
        )

    def _get_storey_placement(self):
        """Get or create the storey's local placement."""
        if getattr(self.storey, 'ObjectPlacement', None) is None:
            placement = self.create_local_placement()
            self.storey.ObjectPlacement = placement
        return self.storey.ObjectPlacement

    def _create_element_placement(self, osdag_obj, relative_to=None):
        """
        Create element placement from Osdag component's geometry attributes.
        Falls back to origin placement if attributes are missing.
        """
        if relative_to is None:
            relative_to = self._get_storey_placement()

        origin = getattr(osdag_obj, 'sec_origin',
                         getattr(osdag_obj, 'origin', None))
        u_dir = getattr(osdag_obj, 'uDir', None)
        w_dir = getattr(osdag_obj, 'wDir', None)

        if origin is not None:
            origin = [float(c) for c in origin]
            z_dir = [float(c) for c in w_dir] if w_dir is not None else [0, 0, 1]
            x_dir = [float(c) for c in u_dir] if u_dir is not None else [1, 0, 0]

            # Ensure orthogonality
            z_arr = np.array(z_dir, dtype=float)
            x_arr = np.array(x_dir, dtype=float)
            z_norm = np.linalg.norm(z_arr)
            x_norm = np.linalg.norm(x_arr)
            if z_norm > 0:
                z_arr /= z_norm
            if x_norm > 0:
                x_arr /= x_norm
            if abs(np.dot(z_arr, x_arr)) > 0.01:
                y_arr = np.cross(z_arr, x_arr)
                y_norm = np.linalg.norm(y_arr)
                if y_norm > 0:
                    y_arr /= y_norm
                x_arr = np.cross(y_arr, z_arr)
                x_arr /= np.linalg.norm(x_arr)

            return self.create_local_placement(
                origin=origin,
                dir_z=z_arr.tolist(),
                dir_x=x_arr.tolist(),
                relative_to=relative_to
            )

        return self.create_local_placement(relative_to=relative_to)

    # Material Definitions
    # =========================================================================

    def get_or_create_material(self, material_name="Steel", grade=""):
        """
        Creates an IfcMaterial just once per name to avoid duplicates.
        Returns (IfcMaterial, IfcMaterialLayer, IfcMaterialLayerSet).
        """
        key = f"{material_name}_{grade}"
        if key in self._material_cache:
            return self._material_cache[key]

        full_name = f"{material_name} {grade}".strip() if grade else material_name
        ifc_material = self.ifc_file.createIfcMaterial(Name=full_name)

        self._material_cache[key] = ifc_material
        return ifc_material

    def assign_material_to_element(self, ifc_element, osdag_obj):
        """
        Create IfcRelAssociatesMaterial between an element and its material.
        """
        material_str = str(getattr(osdag_obj, 'material',
                                   getattr(osdag_obj, 'Material', 'Steel')))
        grade = str(getattr(osdag_obj, 'grade',
                            getattr(osdag_obj, 'Grade', '')))

        ifc_material = self.get_or_create_material(material_str, grade)

        self.ifc_file.createIfcRelAssociatesMaterial(
            GlobalId=self.generate_guid(),
            OwnerHistory=self.owner_history,
            RelatedObjects=[ifc_element],
            RelatingMaterial=ifc_material
        )

    # Element Relationships
    # =========================================================================

    def create_connection_relationship(self, connecting_element,
                                        connected_element,
                                        connection_type="BOLTED"):
        """
        Connects members (e.g. beam to column) so Revit knows they're joined.
        """
        self.ifc_file.createIfcRelConnectsElements(
            GlobalId=self.generate_guid(),
            OwnerHistory=self.owner_history,
            ConnectionGeometry=None,
            RelatingElement=connecting_element,
            RelatedElement=connected_element
        )

    # Collision Detection
    # =========================================================================

    def _init_overlap_checker(self):
        """Setup the collision detection engine for this export."""
        from .overlap_checker import OverlapChecker
        self._overlap_checker = OverlapChecker()

    def _register_for_overlap(self, name, osdag_obj):
        """Add an element to the collision check list."""
        if self._overlap_checker is not None:
            self._overlap_checker.add_element(name, osdag_obj)

    def _finalize_overlaps(self):
        """Run the intersection test and push results into the IFC."""
        if self._overlap_checker is not None:
            overlaps = self._overlap_checker.check_all_overlaps()
            if overlaps:
                print(f"[IFC] Overlap detection: {len(overlaps)} overlaps found")
                self._overlap_checker.annotate_ifc(self)
                report = self._overlap_checker.get_overlap_report()
                print(report)
            else:
                print("[IFC] Overlap detection: No overlapping members detected.")

    # ─── Axis Handler ──────────────────────────────────────────────────────

    def _init_axis_handler(self, cad_class_name=None):
        """
        Initialize the module-specific axis handler.
        Falls back to base handler if no specific handler exists.
        """
        from .axis_definitions import get_axis_handler
        self._axis_handler = get_axis_handler(
            cad_class_name or '', self
        )
        # Update the storey placement from the axis handler
        if self._axis_handler is not None:
            self.storey.ObjectPlacement = self._axis_handler.storey_placement

    # ─── Main Export Orchestration ─────────────────────────────────────────

    def export_connection(self, connection_id, members, plates, bolts,
                          welds=None, metadata=None, others=None,
                          cad_class_name=None):
        """
        Orchestrates the export of an entire Osdag structural connection.

        :param connection_id: Unique string identifier for the connection
        :param members: List of Osdag parameterized section objects
        :param plates: List of Osdag Plate objects
        :param bolts: List of Osdag Bolt/Nut/Washer objects
        :param welds: Optional list of Osdag Weld objects
        :param metadata: Optional dict with design loads, status, material
        :param others: Optional list of non-steel elements
        :param cad_class_name: Optional CAD class name for axis handler
        """
        print(f"Starting IFC LOD 500 export for connection: {connection_id}")

        # ── Initialize axis handler and overlap checker ──
        cad_cls = cad_class_name or (
            metadata.get('CAD_Class', '') if metadata else ''
        )
        self._init_axis_handler(cad_cls)
        self._init_overlap_checker()

        storey_placement = self._get_storey_placement()
        ifc_elements = []
        member_elements = []  # Track for connectivity relationships

        # ─── 1. Map Members (Beams, Columns) ───────────────────────────────
        for member in members:
            solid = self.geom_mapper.map_extruded_solid(member)
            if solid:
                m_name = getattr(member, 'ifc_name', 'Steel Member')
                placement = self._create_element_placement(
                    member, storey_placement
                )

                if 'Column' in m_name:
                    ifc_element = self.ifc_file.createIfcColumn(
                        GlobalId=self.generate_guid(),
                        OwnerHistory=self.owner_history,
                        Name=m_name,
                        ObjectPlacement=placement,
                        Representation=self._create_shape_representation(solid)
                    )
                else:
                    ifc_element = self.ifc_file.createIfcBeam(
                        GlobalId=self.generate_guid(),
                        OwnerHistory=self.owner_history,
                        Name=m_name,
                        ObjectPlacement=placement,
                        Representation=self._create_shape_representation(solid)
                    )

                # Apply bolt hole boolean cuts to members (LOD 500)
                for fastener in bolts:
                    if (fastener.__class__.__name__ == 'Bolt' or
                            getattr(fastener, '_class_name', '') == 'Bolt'):
                        try:
                            origin = (getattr(fastener, 'origin', None) or
                                      getattr(fastener, 'sec_origin', None))
                            shaft_dir = (getattr(fastener, 'shaftDir', None) or
                                         getattr(fastener, 'uDir', None))
                            r = getattr(fastener, 'r', None)
                            h = getattr(fastener, 'H', None)
                            if all(v is not None for v in
                                   [origin, shaft_dir, r, h]):
                                opening_solid = self.geom_mapper.create_opening_element(
                                    origin, shaft_dir, r, h
                                )
                                # Place opening relative to the host element placement
                                self.geom_mapper.perform_boolean_cut(
                                    ifc_element, opening_solid,
                                    opening_placement_rel_to=ifc_element.ObjectPlacement
                                )
                        except Exception as e:
                            print(f"[IFC] Warning: Failed to apply bolt hole "
                                  f"to member {m_name}: {e}")

                self.meta_mapper.assign_osdag_design_data(ifc_element, member)
                self.meta_mapper.assign_member_boq(ifc_element, member,
                                                   metadata)
                self.assign_material_to_element(ifc_element, member)
                self._register_for_overlap(m_name, member)
                ifc_elements.append(ifc_element)
                member_elements.append(ifc_element)

        # ─── 2. Map Plates & Apply Boolean Cuts ────────────────────────────
        plate_elements = []
        for plate in plates:
            plate_solid = self.geom_mapper.map_extruded_solid(plate)
            if not plate_solid:
                continue

            p_name = getattr(plate, 'ifc_name', "Connection Plate")
            placement = self._create_element_placement(
                plate, storey_placement
            )

            ifc_plate = self.ifc_file.createIfcPlate(
                GlobalId=self.generate_guid(),
                OwnerHistory=self.owner_history,
                Name=p_name,
                ObjectPlacement=placement,
                Representation=self._create_shape_representation(plate_solid)
            )

            # Apply bolt hole boolean cuts (LOD 500)
            for fastener in bolts:
                if (fastener.__class__.__name__ == 'Bolt' or
                        getattr(fastener, '_class_name', '') == 'Bolt'):
                    try:
                        origin = (getattr(fastener, 'origin', None) or
                                  getattr(fastener, 'sec_origin', None))
                        shaft_dir = (getattr(fastener, 'shaftDir', None) or
                                     getattr(fastener, 'uDir', None))
                        r = getattr(fastener, 'r', None)
                        h = getattr(fastener, 'H', None)
                        if all(v is not None for v in
                               [origin, shaft_dir, r, h]):
                            opening_solid = self.geom_mapper.create_opening_element(
                                origin, shaft_dir, r, h
                            )
                            self.geom_mapper.perform_boolean_cut(
                                ifc_plate, opening_solid,
                                opening_placement_rel_to=ifc_plate.ObjectPlacement
                            )
                        else:
                            print(f"[IFC] Warning: Bolt missing attrs for "
                                  f"hole: origin={origin}")
                    except Exception as e:
                        print(f"[IFC] Warning: Failed to apply bolt hole "
                              f"to plate {p_name}: {e}")

            self.meta_mapper.assign_osdag_design_data(ifc_plate, plate)
            self.meta_mapper.assign_plate_boq(ifc_plate, plate)
            self.assign_material_to_element(ifc_plate, plate)
            self._register_for_overlap(p_name, plate)
            ifc_elements.append(ifc_plate)
            plate_elements.append(ifc_plate)

        # ─── 3. Map Fasteners (Bolts, Nuts, Washers) ───────────────────────
        for bolt in bolts:
            mapped_item = self.geom_mapper.map_fastener(bolt)
            if mapped_item:
                placement = self._create_element_placement(
                    bolt, storey_placement
                )
                ifc_fastener = self.ifc_file.createIfcFastener(
                    GlobalId=self.generate_guid(),
                    OwnerHistory=self.owner_history,
                    Name="Bolt Assembly",
                    ObjectPlacement=placement,
                    Representation=self._create_shape_representation(
                        mapped_item, rep_type="MappedRepresentation"
                    )
                )
                self.meta_mapper.assign_fastener_boq(
                    ifc_fastener, bolt, bolt.__class__.__name__
                )
                ifc_elements.append(ifc_fastener)

        # ─── 4. Map Welds as Fasteners ─────────────────────────────────────
        if welds:
            for weld in welds:
                weld_solid = self.geom_mapper.map_weld(weld)
                if weld_solid:
                    placement = self._create_element_placement(
                        weld, storey_placement
                    )
                    ifc_weld = self.ifc_file.createIfcFastener(
                        GlobalId=self.generate_guid(),
                        OwnerHistory=self.owner_history,
                        Name=getattr(weld, 'designation', 'Weld Joint'),
                        ObjectType="WELD",
                        ObjectPlacement=placement,
                        Representation=self._create_shape_representation(
                            weld_solid, rep_type="SweptSolid"
                        )
                    )
                    self.meta_mapper.assign_osdag_design_data(
                        ifc_weld, weld
                    )
                    self.meta_mapper.assign_weld_boq(ifc_weld, weld)
                    ifc_elements.append(ifc_weld)

        # ─── 5. Map Others (Concrete, Grout) ──────────────────────────────
        if others:
            for other_item in others:
                other_solid = self.geom_mapper.map_extruded_solid(other_item)
                if other_solid:
                    name = getattr(other_item, '_class_name',
                                   other_item.__class__.__name__)
                    ifc_other = self.ifc_file.createIfcBuildingElementProxy(
                        GlobalId=self.generate_guid(),
                        OwnerHistory=self.owner_history,
                        Name=name,
                        Representation=self._create_shape_representation(
                            other_solid, rep_type="SweptSolid"
                        )
                    )
                    ifc_elements.append(ifc_other)

        # ─── 6. Create Connection Relationships ────────────────────────────
        if len(member_elements) >= 2:
            for i in range(len(member_elements) - 1):
                self.create_connection_relationship(
                    member_elements[i], member_elements[i + 1]
                )
            print(f"[IFC] Created {len(member_elements) - 1} "
                  f"IfcRelConnectsElements relationships")

        # Connect plates to first member
        if member_elements and plate_elements:
            for plate_el in plate_elements:
                self.create_connection_relationship(
                    member_elements[0], plate_el
                )

        # ─── 7. Assembly and Spatial Containment ──────────────────────────
        assembly = self.meta_mapper.create_element_assembly(
            f"Connection_{connection_id}", ifc_elements
        )

        # Assign assembly placement at the global origin
        assembly_placement = self.create_local_placement(
            relative_to=storey_placement
        )
        assembly.ObjectPlacement = assembly_placement

        # Attach design metadata to the assembly
        if metadata:
            self.meta_mapper.assign_standard_pset(
                assembly, "Pset_OsdagDesignData", metadata
            )

        self.ifc_file.createIfcRelContainedInSpatialStructure(
            GlobalId=self.generate_guid(),
            OwnerHistory=self.owner_history,
            RelatingStructure=self.storey,
            RelatedElements=[assembly]
        )

        # ─── 8. Run Overlap Detection ─────────────────────────────────────
        self._finalize_overlaps()

        print(f"[IFC] Export orchestration completed for {connection_id}")
        print(f"[IFC] Total elements exported: {len(ifc_elements)}")

    def _create_shape_representation(self, geometric_item,
                                      rep_type="SweptSolid"):
        """Helper to wrap a solid/mapped item in IfcProductDefinitionShape."""
        rep = self.ifc_file.createIfcShapeRepresentation(
            ContextOfItems=self.project.RepresentationContexts[0],
            RepresentationIdentifier="Body",
            RepresentationType=rep_type,
            Items=[geometric_item]
        )
        return self.ifc_file.createIfcProductDefinitionShape(
            Representations=[rep]
        )
