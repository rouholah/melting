"""
  FreeCADBatchFEMTools - A library for using FreeCAD for FEM preprocessing in batch mode

  Copyright 1st May 2018 - , Trafotek Oy, Finland
 
  This library is free software; you can redistribute it and/or
  modify it under the terms of the GNU Lesser General Public
  License as published by the Free Software Foundation; either
  version 2.1 of the License, or (at your option) any later version.

  This library is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
  Lesser General Public License for more details.
 
  You should have received a copy of the GNU Lesser General Public
  License along with this library (in file ../LGPL-2.1); if not, write 
  to the Free Software Foundation, Inc., 51 Franklin Street, 
  Fifth Floor, Boston, MA  02110-1301  USA

  Authors: Eelis Takala, Janne Keranen, Sami Rannikko
  Emails:  eelis.takala@gmail.com, janne.sami.keranen@vtt.fi
  Address: Trafotek Oy
           Kaarinantie 700
           20540 Turku
           Finland

  Original Date: May 2018
"""
from __future__ import print_function
import os
import Fem
import FreeCAD
import Part
import BOPTools.SplitFeatures
import ObjectsFem
import femmesh.gmshtools
import math
import itertools
import subprocess

import meshutils


def fit_view():
    """
    If GUI is available, fit the view so that the geometry can be seen
    """
    if FreeCAD.GuiUp:
        import FreeCADGui
        FreeCADGui.ActiveDocument.activeView().viewAxonometric()
        FreeCADGui.SendMsgToActiveView("ViewFit")

def isclose(a, b, rel_tol=1e-4, abs_tol=1e-4):
    """
    Returns True if a and b are close to each other (within absolute or relative tolerance).

    :param a: float
    :param b: float
    :param rel_tol: float
    :param abs_tol: float
    :return: bool
    """
    return abs(a-b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)

def vectors_are_same(vec1,vec2,tol=1e-4):
    """
    Compares vectors vec1 and vec2. If they are same within a tolerance returns
    True if not returns false.

    :param vec1: Vector 1 
    :param vec2: Vector 2 to be compared with Vector 1
    :return: Boolean
    """
    vec3 = vec1.sub(vec2)
    return isclose(vec3.Length, 0., abs_tol=tol)

def faces_with_vertices_in_symmetry_plane(face_object_list, plane=None, abs_tol=1e-4):
    """
    Returns faces from a list of FreeCAD face objects. The returned faces have to 
    be in a defined symmetry plane. The face is in symmetry plane if all of its points
    and the center of mass are in the plane.

    :param face_object_list: list of FreeCAD face objects
    :param plane: symmetry plane.

    :return: list of FreeCAD face objects that are in the given symmetry plane
    """
    if plane is None: return None
    face_object_list_out = []
    for face_object in face_object_list:
        vertices = face_object.Vertexes
        center_of_mass = face_object.CenterOfMass
        if plane in ['zx', 'xz']: center_compare_value = center_of_mass.y
        elif plane in ['xy', 'yx']: center_compare_value = center_of_mass.z
        elif plane in ['yz', 'zy']: center_compare_value = center_of_mass.x
        else: raise ValueError("Wrong keyword for plane variable, should be: zx, xy, yz, xz, yx or zy!")
        for i, vertex in enumerate(vertices):
            if plane in ['zx', 'xz']: compare_value = vertex.Y
            elif plane in ['xy', 'yx']: compare_value = vertex.Z
            elif plane in ['yz', 'zy']: compare_value = vertex.X
            else: raise ValueError("Wrong keyword for plane variable, should be: zx, xy, yz, xz, yx or zy!")
            if not isclose(compare_value, 0., abs_tol=abs_tol): break
        if i==len(vertices)-1 and isclose(center_compare_value, 0., abs_tol=abs_tol): face_object_list_out.append(face_object)
    return face_object_list_out

def reduce_half_symmetry(solid, name, App, doc, planes=None, reversed_direction = False):
    doc.recompute()
    if planes==None: return solid
    plane = planes.pop()
    doc.recompute()
    reduced_name = name + '_' + plane
    tool_box = doc.addObject("Part::Box","CutBox"+reduced_name)
    x = 10. * solid.Shape.BoundBox.XLength
    y = 10. * solid.Shape.BoundBox.YLength
    z = 10. * solid.Shape.BoundBox.ZLength
    if isinstance(solid, Part.Feature):
        center=solid.Shape.Solids[0].CenterOfMass
    else:
        center=solid.Shape.CenterOfMass
    
    tool_box.Length = x
    tool_box.Width = y 
    tool_box.Height = z
    if plane == 'zx':
        tool_box.Placement = App.Placement(App.Vector(center.x-x/2.,0,center.z-z/2.),App.Rotation(App.Vector(0,0,1),0))
    elif plane == 'xy':
        tool_box.Placement = App.Placement(App.Vector(center.x-x/2.,center.y-y/2.,0),App.Rotation(App.Vector(0,0,1),0))
    elif plane == 'yz':
        tool_box.Placement = App.Placement(App.Vector(0,center.y-y/2.,center.z-z/2.),App.Rotation(App.Vector(0,0,1),0))
    else:
        raise ValueError("Wrong keyword for plane variable, should be: zx, xy or yz!")
    
    if reversed_direction:
        half_symmetry = doc.addObject("Part::MultiCommon",reduced_name)
        half_symmetry.Shapes = [solid, tool_box]
    else:
        half_symmetry = doc.addObject("Part::Cut", reduced_name)
        half_symmetry.Base = solid
        half_symmetry.Tool = tool_box

    if len(planes) > 0:
        return reduce_half_symmetry(half_symmetry, reduced_name, App, doc, planes, reversed_direction)

    return half_symmetry

def faces_same_center_of_masses(face1, face2, tolerance=0.0001):    
    """
    Compare two faces by comparing if they have same centers of mass with the tolerance.

    :param face1: FreeCAD face object
    :param face2: FreeCAD face object
    :param tolerance: float

    """
    return vectors_are_same(face1.CenterOfMass, face2.CenterOfMass, tolerance)

def faces_are_same(face1, face2, tolerance=1e-4):
    """
    Return true if face1 is same as face2. The faces are same if they have
    the same center of masses and same vertices.

    :param face1: FreeCAD face object
    :param face2: FreeCAD face object

    :return: bool
    """
    return faces_same_center_of_masses(face1, face2, tolerance) and faces_have_same_vertices(face1, face2, tolerance)

def is_face_in_list(search_face, face_object_list, tolerance=1e-4):
    """
    Returns true if search_face is in the face_object_list. Compares faces with 
    face_compare method.

    :param search_face: FreeCAD face object
    :param face_object_list: list of FreeCAD face objects
    """
    for face_object in face_object_list:
        if faces_are_same(search_face, face_object): return True
    return False

def remove_compare_face_from_list(cface, face_object_list, tolerance=1e-4):
    """
    Removes the first FreeCAD face object that matches in the FreeCAD face object list. 
    Uses face_compare to determine if the face is to be removed. 

    :param cface: a FreeCAD face object to be compared
    :param face_object_list: the list of FreeCAD face objects where the face 
                             is to be removed in case of a match

    :return: list of FreeCAD face objects that are removed from the original list of 
             FreeCAD face objects.
    """
 
    for i, face_object in enumerate(face_object_list):
        if faces_are_same(cface, face_object): 
            return face_object_list.pop(i)
    return None

def remove_compare_faces_from_list(compare_face_object_list, face_object_list):
    """
    Removes all the face objects in compare_face_object_list that match to the face objects in 
    the face_object_list. Uses face_compare to determine if the face is to be removed. 

    :param compare_face_object_list: list of FreeCAD face objects to be compared
    :param face_object_list: original list of FreeCAD face objects

    :return: list of FreeCAD face objects that are removed from the original list of 
             FreeCAD face objects.
    """
    removed = []
    for face_object in compare_face_object_list:
        removed.append(remove_compare_face_from_list(face_object, face_object_list))
    return removed 

def faces_have_same_vertices(face1, face2, tolerance=0.0001):
    """
    Compare two faces by comparing that they have same number of vertices and 
    the vertices are in identical coordinates with the tolerance. Return 
    truth value to the faces are the same in this regard.

    :param face1: FreeCAD face object
    :param face2: FreeCAD face object
    :return: bool
    """
    face_vertices_found = []
    for vertex in face2.Vertexes:
        for cvertex in face1.Vertexes:
            if vectors_are_same(vertex.Point,cvertex.Point, tolerance):                   
                face_vertices_found.append(1)
    return len(face_vertices_found) == len(face2.Vertexes) and len(face_vertices_found) == len(face1.Vertexes)

def is_point_inside_face(face, vector, tolerance=0.0001):
    """
    Returns True if point is inside face.

    WARNING: This function calls function face.isInside which does NOT respect tolerance
             https://forum.freecadweb.org/viewtopic.php?t=31524

    :param face: FreeCAD face object
    :param vector: Vector
    :param tolerance: float

    :return: bool
    """
    return face.isInside(vector, tolerance, True)

def is_point_inside_solid(solid, vector, tolerance=0.0001, include_faces=True):
    """
    Returns True if point is inside solid.

    :param solid: FreeCAD solid object
    :param vector: Vector
    :param tolerance: float
    :param include_faces: bool

    :return: bool
    """
    return solid.isInside(vector, tolerance, include_faces)

def is_point_inside_solid_with_round(solid, vector, tolerance=0.0001, round_digits=6):
    """
    Returns True if point is inside solid (faces included) with
    additional tolerance (8 points checked).
    Tries upper and lower rounding of coordinates with precision round_digits.

    :param solid: FreeCAD solid object
    :param vector: Vector
    :param tolerance: float
    :param round_digits: integer

    :return: bool
    """
    rounding = 10**round_digits
    x_floor, x_ceil = math.floor(rounding*vector.x)/rounding, math.ceil(rounding*vector.x)/rounding
    y_floor, y_ceil = math.floor(rounding*vector.y)/rounding, math.ceil(rounding*vector.y)/rounding
    z_floor, z_ceil = math.floor(rounding*vector.z)/rounding, math.ceil(rounding*vector.z)/rounding
    for coordinates in itertools.product([x_floor, x_ceil], [y_floor, y_ceil], [z_floor, z_ceil]):
        vector.x = coordinates[0]
        vector.y = coordinates[1]
        vector.z = coordinates[2]
        if is_point_inside_solid(solid, vector, tolerance):
            return True
    return False

def is_same_vertices(vertex1, vertex2, tolerance=0.0001):
    """
    Checks if given vertices are same.

    :param vertex1: FreeCAD vertex
    :param vertex2: FreeCAD vertex
    :param tolerance: float

    :return: bool
    """
    if abs(vertex1.X - vertex2.X) < tolerance:
        if abs(vertex1.Y - vertex2.Y) < tolerance:
            if abs(vertex1.Z - vertex2.Z) < tolerance:
                return True
    return False

def is_same_edge(edge1, edge2, tolerance=0.0001):
    """
    Checks if given edges are in same place by comparing end points.

    :param edge1: FreeCAD edge
    :param edge2: FreeCAD edge
    :param tolerance: float

    :return: bool
    """
    if is_same_vertices(edge1.Vertexes[0], edge2.Vertexes[0], tolerance):
        if is_same_vertices(edge1.Vertexes[1], edge2.Vertexes[1], tolerance):
            return True
    elif is_same_vertices(edge1.Vertexes[0], edge2.Vertexes[1], tolerance):
        if is_same_vertices(edge1.Vertexes[1], edge2.Vertexes[0], tolerance):
            return True
    return False

def is_edge_in_solid(solid, edge, tolerance=0.0001):
    """
    Returns True if edge inside solid by comparing is edge vertices inside solid.

    :param solid: FreeCAD solid object
    :param edge: FreeCAD edge object
    :param tolerance: float

    :return: bool
    """
    for vertex in edge.Vertexes:
        if not is_point_inside_solid(solid, vertex.Point, tolerance):
            return False
    return True

def get_point_from_solid(solid, tolerance=0.0001):
    """
    Returns point from given solid.

    :param solid: FreeCAD solid object
    :param tolerance: float

    :return: None or FreeCAD vector object
    """
    x_min, y_min, z_min = solid.BoundBox.XMin, solid.BoundBox.YMin, solid.BoundBox.ZMin
    x_len, y_len, z_len = solid.BoundBox.XLength, solid.BoundBox.YLength, solid.BoundBox.ZLength
    for split_count in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97,
                        101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181, 191, 193,
                        197, 199, 211, 223, 227, 229, 233, 239, 241, 251, 257, 263, 269, 271, 277, 281, 283, 293, 307,
                        311, 313, 317, 331, 337, 347, 349, 353, 359, 367, 373, 379, 383, 389, 397, 401, 409, 419, 421,
                        431, 433, 439, 443, 449, 457, 461, 463, 467, 479, 487, 491, 499, 503, 509, 521, 523, 541]:
        x_split_len, y_split_len, z_split_len = x_len/split_count, y_len/split_count, z_len/split_count
        for i in range(1, split_count):
            x_test = x_min + i*x_split_len
            for j in range(1, split_count):
                y_test = y_min + j*y_split_len
                for k in range(1, split_count):
                    test_point = FreeCAD.Vector(x_test, y_test, z_min + k*z_split_len)
                    if is_point_inside_solid(solid, test_point, tolerance, include_faces=False):
                        return test_point
    return None

def is_point_on_face_edges(face, p2, tol=0.0001):
    """
    Checks if given point is on same edge of given face.

    :param face: FreeCAD face object
    :param p2: FreeCAD Vector object
    :param tol: float

    :return: bool
    """
    vertex = Part.Vertex(p2)
    for edge in face.Edges:
        if vertex.distToShape(edge)[0] < tol:
            return True
    return False

def get_point_from_face_close_to_edge(face):
    """
    Increases parameter range minimum values of face by one until at least
    two of the x, y and z coordinates of the corresponding point has moved at least 1 unit.
    If point is not found None is returned.

    :param face: FreeCAD face object.

    :return: None or FreeCAD vector object.
    """
    u_min, u_max, v_min, v_max = face.ParameterRange
    p1 = face.valueAt(u_min, v_min)
    u_test, v_test = u_min+1, v_min+1
    while u_test < u_max and v_test < v_max:
        p2 = face.valueAt(u_test, v_test)
        # Check at least two coordinates moved 1 unit
        if (abs(p1.x - p2.x) >= 1) + (abs(p1.y - p2.y) >= 1) + (abs(p1.z - p2.z) >= 1) > 1:
            if is_point_on_face_edges(face, p2):
                v_test += 0.5
                continue  # go back at the beginning of while
            if face.isPartOfDomain(u_test, v_test):
                return p2
            return None
        u_test, v_test = u_test+1, v_test+1
    return None

def get_point_from_face(face):
    """
    Returns point from given face.

    :param face: FreeCAD face object.

    :return: None or FreeCAD vector object
    """
    point = get_point_from_face_close_to_edge(face)
    if point is not None:
        return point
    u_min, u_max, v_min, v_max = face.ParameterRange
    u_len, v_len = u_max-u_min, v_max-v_min
    # use primes so same points are not checked multiple times
    for split_count in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97,
                        101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181, 191, 193,
                        197, 199, 211, 223, 227, 229, 233, 239, 241, 251, 257, 263, 269, 271, 277, 281, 283, 293, 307,
                        311, 313, 317, 331, 337, 347, 349, 353, 359, 367, 373, 379, 383, 389, 397, 401, 409, 419, 421,
                        431, 433, 439, 443, 449, 457, 461, 463, 467, 479, 487, 491, 499, 503, 509, 521, 523, 541]:
        u_split_len, v_split_len = u_len/float(split_count), v_len/float(split_count)
        for i in range(1, split_count):
            u_test = u_min + i*u_split_len
            for j in range(1, split_count):
                v_test = v_min + j*v_split_len
                if face.isPartOfDomain(u_test, v_test):
                    return face.valueAt(u_test, v_test)
    return None

def is_face_in_face(face1, face2, tolerance=0.0001):
    """
    Returns True if all vertices and point in face1 also belongs to face2

    :param face1: FreeCAD face object
    :param face2: FreeCAD face object
    :param tolerance: float

    :return: bool
    """
    for vertex in face1.Vertexes:
        if not is_point_inside_face(face2, vertex.Point, tolerance):
            return False
    point_in_face1 = get_point_from_face(face1)
    if point_in_face1 is not None:
        if not is_point_inside_face(face2, point_in_face1, tolerance):
            return False
    else:
        raise ValueError('Face point not found')
    return True

def is_face_in_solid(solid, face, tolerance=0.0001, use_round=True):
    """
    Checks if all face vertices and one additional point from face are inside solid.
    If use_round is True calls function meth:`is_point_inside_solid_with_round` to check
    if point inside solid.

    :param solid: FreeCAD solid object
    :param face: FreeCAD face object
    :param tolerance: float
    :param use_round: bool

    :return: bool
    """
    if use_round:
        is_point_in_solid_func = is_point_inside_solid_with_round
    else:
        is_point_in_solid_func = is_point_inside_solid
    for vertex in face.Vertexes:
        if not is_point_in_solid_func(solid, vertex.Point, tolerance):
            return False
    point_in_face = get_point_from_face(face)
    if point_in_face is not None:
        if not is_point_in_solid_func(solid, point_in_face, tolerance):
            return False
    else:
        raise ValueError('Face point not found')
    return True

def is_compound_filter_solid_in_solid(compound_filter_solid, solid, tolerance=0.0001, point_search=True):
    """
    If point_search is True:
        returns True if all faces of compound_filter_solid are inside solid
    else:
        returns compound_filter_solid.common(solid).Volume > 0

    :param compound_filter_solid: FreeCAD solid object
    :param solid: FreeCAD solid object
    :param tolerance: float (only used with point_search)
    :param point_search: bool

    :return: bool
    """
    if point_search:
        point_in_solid = get_point_from_solid(compound_filter_solid, tolerance)
        if point_in_solid is None:
            raise ValueError('Solid point not found')
        return is_point_inside_solid(solid, point_in_solid, tolerance)
    return compound_filter_solid.common(solid).Volume > 0

def solids_are_the_same(solid1, solid2):
    """
    Compare two solids by comparing have they same number of faces and the faces are identical. 
    Return truth value to the solids are the same in this regard.
    
    :param solid1: FreeCAD solid object
    :param solid2: FreeCAD solid object
    :return: bool
    """
    solid_faces_found = []
    for face in solid2.Faces:
        for cface in solid1.Faces:
            if faces_same_center_of_masses(cface, face) and faces_have_same_vertices(cface, face):                   
                solid_faces_found.append(1)
    return len(solid_faces_found) == len(solid2.Faces) and len(solid_faces_found) == len(solid1.Faces)

def create_boolean_compound(solid_objects, doc):
    """
    Creates a FreeCAD boolean compound for the list of FreeCAD solid objects.
    This is needed when mesh is computed for the whole geometry. Note that
    there is also a create_mesh_object_and_compound_filter for meshing purpose.

    :param solid_objects: list of FreeCAD solid geometry objects.
    :param doc: FreeCAD document.
    :return: FreeCAD compound object.
    """
    doc.recompute()
    comp_obj = BOPTools.SplitFeatures.makeBooleanFragments(name='Compsolid')
    comp_obj.Objects = solid_objects 
    comp_obj.Mode = "CompSolid"
    comp_obj.Proxy.execute(comp_obj)
    comp_obj.purgeTouched()
    return comp_obj

def create_compound(solid_objects, doc, name='Compsolid'):
    """
    Creates a FreeCAD compound for the list of FreeCAD solid objects.

    :param solid_objects: list of FreeCAD solid geometry objects.
    :param doc: FreeCAD document.
    :param name: String.
    :return: FreeCAD compound object.
    """
    compound = doc.addObject('Part::Compound', name)
    compound.Links = solid_objects
    doc.recompute()
    return compound

def create_xor_object(solid_objects, doc):
    """
    Creates a FreeCAD xor object for the list of FreeCAD solid objects.

    :param solid_objects: list of FreeCAD solid geometry objects.
    :param doc: FreeCAD document.
    :return: FreeCAD xor object
    """
    doc.recompute()
    xor_object = BOPTools.SplitFeatures.makeXOR(name='XOR')
    xor_object.Objects = solid_objects
    xor_object.Proxy.execute(xor_object)
    xor_object.purgeTouched()
    return xor_object

def create_compound_filter(compsolid):
    """
    Create a compound filter. This is needed for meshing. Note that
    there is also a create_mesh_object_and_compound_filter for meshing purpose.

    :param compsolid: FreeCAD compound object for example from create_boolean_compound
    :return: FreeCAD compound filter object
    """
    import CompoundTools.CompoundFilter
    compound_filter = CompoundTools.CompoundFilter.makeCompoundFilter(name='CompoundFilter')
    compound_filter.Base = compsolid
    compound_filter.FilterType = 'window-volume' #???
    compound_filter.Proxy.execute(compound_filter) #???
    return compound_filter

def create_mesh_object(compound_filter, CharacteristicLength, doc, algorithm2d='Automatic', algorithm3d='New Delaunay'):
    """
    Creates a mesh object that controls the mesh definitions.

    :param compound_filter: FreeCAD compound filter object
    :param CharacteristicLength: Default mesh size characteristic length
    :param doc: FreeCAD document.
    :param algorithm2d: String 'MeshAdapt', 'Automatic', 'Delaunay', 'Frontal', 'BAMG', 'DelQuad'.
    :param algorithm3d: String 'Delaunay', 'New Delaunay', 'Frontal', 'Frontal Delaunay', 'Frontal Hex',
                        'MMG3D', 'R-tree'.
    :return: FreeCAD mesh object
    """
    # Make a FEM mesh and mesh groups for material bodies and boundary conditions
    mesh_object = ObjectsFem.makeMeshGmsh(doc, 'GMSHMeshObject')
    mesh_object.Part = compound_filter
    mesh_object.CharacteristicLengthMax = CharacteristicLength
    mesh_object.Algorithm2D = algorithm2d
    mesh_object.Algorithm3D = algorithm3d
    mesh_object.ElementOrder = u"1st"
    return mesh_object

def set_mesh_group_elements(gmsh_mesh):
    """
    Updates group_elements dictionary in gmsh_mesh.
    Rewritten gmsh_mesh.get_group_data without finding mesh group elements again

    :param gmsh_mesh: Instance of gmshtools.GmshTools.
    """
    for mg in gmsh_mesh.mesh_obj.MeshGroupList:
        gmsh_mesh.group_elements[mg.Label] = list(mg.References[0][1])  # tuple to list
    if gmsh_mesh.group_elements:
        FreeCAD.Console.PrintMessage('  {}\n'.format(gmsh_mesh.group_elements))

def _remove_ansi_color_escape_codes(message):
    """
    Replace color code escape codes from message with empty string.

    :param message: A string.

    :return: A string.
    """
    return message.replace('\x1b[1m', '').replace('\x1b[31m', '').replace('\x1b[35m', '').replace('\x1b[0m', '')

def run_gmsh(gmsh_mesh, gmsh_log_file=None):
    """
    Runs gmsh. Writes gmsh output to gmsh_log_file if given.

    :param gmsh_mesh: Instance of gmshtools.GmshTools.
    :param gmsh_log_file: None or path to gmsh_log.

    :return: Gmsh stderr, None or error string.
    """
    if gmsh_log_file is None:
        error = gmsh_mesh.run_gmsh_with_geo()
    else:
        try:
            with open(gmsh_log_file, 'w') as f:
                p = subprocess.Popen([gmsh_mesh.gmsh_bin, '-', gmsh_mesh.temp_file_geo],
                                     stdout=f, stderr=subprocess.PIPE, universal_newlines=True)
                no_value, error = p.communicate()
                if error:
                    error = _remove_ansi_color_escape_codes(error)
                    f.write(error)
                    f.flush()
        except Exception:
            error = 'Error executing gmsh'
    return error

def create_mesh(mesh_object, directory=False, gmsh_log_file=None, transfinite_param_list=None):
    """
    Create mesh mesh with Gmsh.
    Value of directory determines location gmsh temporary files::

        - False: Use current working directory
        - None: Let GmshTools decide (temp directory)
        - something else: try to use given value

    :param mesh_object: FreeCAD mesh object
    :param directory: Gmsh temp file location.
    :param gmsh_log_file: None or path to gmsh_log.
    :param transfinite_param_list: None or a list containing dictionaries {'volume': 'name',
                                                                           'surface_list': [s_name, sname2]}.

    :return: None or gmsh error text.
    """
    if directory is False:
        directory = os.getcwd()
    gmsh_mesh = femmesh.gmshtools.GmshTools(mesh_object)
    # error = gmsh_mesh.create_mesh()
    # update mesh data
    gmsh_mesh.start_logs()
    gmsh_mesh.get_dimension()
    set_mesh_group_elements(gmsh_mesh)  # gmsh_mesh.get_group_data
    gmsh_mesh.get_region_data()
    gmsh_mesh.get_boundary_layer_data()
    # create mesh
    gmsh_mesh.get_tmp_file_paths(param_working_dir=directory)
    gmsh_mesh.get_gmsh_command()
    gmsh_mesh.write_gmsh_input_files()
    if transfinite_param_list:
        meshutils.add_transfinite_lines_to_geo_file(directory, transfinite_param_list)
    error = run_gmsh(gmsh_mesh, gmsh_log_file)
    if error:
        FreeCAD.Console.PrintError('{}\n'.format(error))
        return error
    gmsh_mesh.read_and_set_new_mesh()

def create_mesh_object_and_compound_filter(solid_objects, CharacteristicLength, doc, separate_boundaries=False,
                                           algorithm2d='Automatic', algorithm3d='New Delaunay'):
    """
    Creates FreeCAD mesh and compound filter objects. Uses create_boolean_compound/create_compound and
    create_compound_filter, create_mesh_object methods.

    :param solid_objects: list of FreeCAD solid geometry objects
    :param CharacteristicLength: Default mesh size characteristic length
    :param doc: FreeCAD document.
    :param separate_boundaries: Boolean (create compound instead of boolean fragment).
    :param algorithm2d: String 'MeshAdapt', 'Automatic', 'Delaunay', 'Frontal', 'BAMG', 'DelQuad'.
    :param algorithm3d: String 'Delaunay', 'New Delaunay', 'Frontal', 'Frontal Delaunay', 'Frontal Hex',
                        'MMG3D', 'R-tree'.
    """
    if len(solid_objects) == 1 or separate_boundaries:  # boolean compound can not be created with only one solid
        boolean_compound = create_compound(solid_objects, doc)
    else:
        boolean_compound = create_boolean_compound(solid_objects, doc)
    compound_filter = create_compound_filter(boolean_compound)
    mesh_object = create_mesh_object(compound_filter, CharacteristicLength, doc, algorithm2d, algorithm3d)
    return mesh_object, compound_filter

def run_elmergrid(export_path, mesh_object, out_dir=None, log_file=None):
    """
    Run ElmerGrid as an external process if it found in the operating system.

    :param export_path: path where the result is written
    :param mesh_object: FreeCAD mesh object that is to be exported
    :param out_dir: directory where to write mesh files (if not given unv file name is used)
    :param log_file: None or a string.
    """
    # Export to UNV file for Elmer
    export_objects = [mesh_object]
    Fem.export(export_objects, export_path)
    elmerGrid_command = 'ElmerGrid 8 2 ' + export_path + ' -autoclean -names'
    if out_dir is not None:
        elmerGrid_command += ' -out ' + out_dir

    FreeCAD.Console.PrintMessage('Running ' + elmerGrid_command + '\n')
    if log_file is not None:
        with open(log_file, 'w') as f:
            p = subprocess.Popen(elmerGrid_command.split(), stdout=f, stderr=subprocess.STDOUT)
            p.communicate()
    else:
        from PySide import QtCore, QtGui
        try:
            process = QtCore.QProcess()
            process.startDetached(elmerGrid_command)
        except:
            FreeCAD.Console.PrintError('Error')
            QtGui.QMessageBox.critical(None, 'Error', 'Error!!', QtGui.QMessageBox.Abort)
    FreeCAD.Console.PrintMessage('Finished ElmerGrid\n')

def export_unv(export_path, mesh_object):
    """
    Exports UNV file for Elmer.

    :param export_path: string
    :param mesh_object: Mesh object
    """
    Fem.export([mesh_object], export_path)

def find_compound_filter_edge(compound_filter, edge):
    """
    Find which edge in the compound filter object is the edge as the one given in second argument.
    Returns the name of the edge in compound filter.

    :param compound_filter: FreeCAD compound filter.
    :param edge: FreeCAD edge.

    :return: A string.
    """
    for num, c_edge in enumerate(compound_filter.Shape.Edges):
        if is_same_edge(c_edge, edge):
            return str(num+1)
    raise ValueError('Edge not found')

def find_compound_filter_boundary(compound_filter, face):
    """
    Find which face in the compound filter object is the face as the one given in second argument.
    Returns the name of the face in compound filter.

    :param compound_filter: FreeCAD compound filter
    :param face: FreeCAD face object
    :return: string
    """
    faces = compound_filter.Shape.Faces
    face_found = None
    for num, cface in enumerate(faces):
        if faces_have_same_vertices(cface, face):
            face_found = num
    if face_found is None: return None
    string = "Face" + str(face_found+1)
    return string

def find_compound_filter_solid(compound_filter, solid):
    """
    Find which solid in the compound filter object is the solid as the one given in second argument.
    Returns the name of the solid in compound filter.

    :param compound_filter: FreeCAD compound filter
    :param solid: FreeCAD solid object
    :return: string
    """
    solids = compound_filter.Shape.Solids
    solid_found = None
    for num, csolid in enumerate(solids):
        if solids_are_the_same(csolid, solid):
            solid_found = num
    if solid_found is None: return None
    string = "Solid" + str(solid_found+1)
    return string

def find_compound_filter_boundaries(compound_filter, face, used_compound_face_names=None):
    """
    Finds all faces in the compound filter object which are inside given face.
    Returns a tuple containing all names of the faces in compound filter.
    If list used_compound_face_names is given checks that found face is not already used and
    face is not already found here (relates to argument 'separate_boundaries' in other functions).

    :param compound_filter: FreeCAD compound filter
    :param face: FreeCAD face object
    :param used_compound_face_names: None or a list.
    :return: tuple
    """
    face_name_list, already_found_cfaces = [], []
    for num, cface in enumerate(compound_filter.Shape.Faces):
        if is_face_in_face(cface, face):
            f_name = "Face" + str(num+1)
            if used_compound_face_names is not None:
                if f_name in used_compound_face_names:
                    continue
                face_already_found = False
                for found_cface in already_found_cfaces:
                    if is_face_in_face(cface, found_cface):
                        face_already_found = True
                        break
                if face_already_found:
                    continue
                already_found_cfaces.append(cface)
            face_name_list.append(f_name)
    if len(face_name_list) == 0:
        raise ValueError("Faces not found")
    return tuple(face_name_list)

def find_compound_filter_solids(compound_filter, solid, point_search=True):
    """
    Finds all solids in the compound filter object which are inside given solid.
    Returns a tuple containing all names of the solids in compound filter.

    :param compound_filter: FreeCAD compound filter
    :param solid: FreeCAD solid object
    :param point_search: bool
    :return: tuple
    """
    solid_name_list = []
    for num, csolid in enumerate(compound_filter.Shape.Solids):
        if is_compound_filter_solid_in_solid(csolid, solid, point_search=point_search):
            solid_name_list.append("Solid" + str(num+1))
    if len(solid_name_list) == 0:
        raise ValueError("Solids not found")
    return tuple(solid_name_list)

""" 
There is no topological naming in FreeCAD. Further, the face numbers are changed in 
making boolean compound. Hence, then making the original solids, the important solids 
and faces are named with generating the following entities dictionary: 

Entities dict definition 
    example_entities = {
      'name' : 'This is the name of the example',
      'faces' : [
                 {'name':'face1',
                  'geometric object':face1_geom_object,
                  'mesh size':mesh_size},
                  ..., 
                 {'name':'facen',
                  'geometric object':facen_geom_object,
                  'mesh size':mesh_size}
                ]
      'solids' : [
                  {'name':'solid_1',
                   'geometric object':solid1_geom_object,
                   'mesh size':mesh_size_1}, 
                   ...,
                  {'name':'solid_n',
                   'geometric object':solidn_geom_object,
                   'mesh size':mesh_size_n}
                 ]
      'main object': main_geom_object
     }
In 'faces' and 'solids' have lists that are so called entity lists.
Entity is defined as a dict containing the name, geometric object and 
the mesh size. In principle one could dynamically add more keys in this
entity property dict:

                  {'name':'solid_n',
                   'geometric object':solidn_geom_object,
                   'mesh size':mesh_size_n}

main_geom_object is for storing a main geometry. For example usually 
when a single solid is created, it contains many face and one solid. 
it is handy to store the solid under the 'main object' key.
"""
def add_entity_in_list(entity_list, name, geom_object, mesh_sizes=None):
    """
    Add entity in list of entities. The mesh sizes can be defined by 
    providing the following dictionary:

    mesh_sizes={
                entity_name_1:mesh_size_for_entity_name_1,
                ...
                entity_name_n:mesh_size_for_entity_name_n,
                mesh size:mesh size if name is not in the dict
               }

    :param entity_list: [entity_1, ..., entity_n]
    :param name: string (name of the entity to be added)
    :param geom_object: geometric object of the entity
    :param mesh_sizes: dict
    """
    if mesh_sizes is not None:
        if name in mesh_sizes: mesh_size = mesh_sizes[name]
        elif 'mesh size' in mesh_sizes: mesh_size = mesh_sizes['mesh size']
        else: mesh_size = None
    else:
        mesh_size = None
    entity_list.append({'name': name,
                        'geometric object': geom_object,
                        'mesh size': mesh_size})

def add_geom_obj_list_in_entitylist(entity_list, name, geom_obj_list, mesh_sizes=None):
    """
    Adds a list of geometry objects in entitylist using add_entity_in_list(entity_list, name, geom_object, mesh_sizes=None)
    """
    for geom_object in geom_obj_list:
        add_entity_in_list(entity_list, name, geom_object, mesh_sizes)

def add_symmetry_plane_faces_in_entity_list(entity_list, geom_object, plane, mesh_sizes=None):
    """
    Adds symmetry plane faces using add_geom_obj_list_in_entitylist(entity_list, name, geom_obj_list, mesh_sizes=None)
    """
    faces_in_symmetry_plane = faces_with_vertices_in_symmetry_plane(geom_object.Shape.Faces, plane)
    add_geom_obj_list_in_entitylist(entity_list, plane, faces_in_symmetry_plane)

def get_entitylist_faces(entity_list):
    """
    Collects geometric objects from dictionaries in entity_list.

    :param entity_list: list

    :return: list
    """
    faces = []
    for entity in entity_list:
        faces.append(entity['geometric object'])
    return faces

def create_entities_dict(name, face_entity_list, solid_entity_list, main_object=None, params=None):
    """
    Helper method for creating an entities dictionary.

    :param name: name of the collection of entities 
    :param face_entity_list: [face_entity_1, ..., face_entity_n]
    :param solid_entity_list: [solid_entity_1, ..., solid_entity_n]
    :param main_object: main object (usually a solid when the entity only has one)
    :param params: None or a dictionary added to entities_dict:

    :return: entities_dict
    """
    entities_dict = {
            'name': name,
            'faces': face_entity_list,
            'solids': solid_entity_list,
            'main object': main_object
            }
    if params:
        entities_dict.update(params)
    return entities_dict

def pick_faces_from_geometry(geom_object, face_picks, mesh_sizes=None):
    """
    Helper function for picking faces from a geometry object.
    The mesh sizes can be defined by providing the following dictionary::

        mesh_sizes={
                    entity_name_1:mesh_size_for_entity_name_1,
                    ...
                    entity_name_n:mesh_size_for_entity_name_n,
                    mesh size:mesh size if name is not in the dict
                     }

    :param geom_object: FreeCAD geometric object where the faces are picked
    :param face_picks: tuple('name of the face', int(face_number))
    :param mesh_sizes: dict

    :return: list
    """
    faces = []
    face_objects = geom_object.Shape.Faces
    for face_pick in face_picks:
        face_name = face_pick[0]
        face_number = face_pick[1]
        add_entity_in_list(faces, face_name, face_objects[face_number], mesh_sizes)
    return faces

def create_transfinite_mesh_param_dict(volume_name, surface_name_list, direction_dict=None, line_params=None):
    """
    Creates transfinite mesh parameter dictionary e.g.::

        {'transfinite_mesh_params': {'volume': 'A1',
                                     'surface_list': ['A1_alpha0', 'A1_alpha1']}
        }

    :param volume_name: List containing volume names.
    :param surface_name_list: List containing surface names.
    :param direction_dict: None or a dictionary e.g. {'A1_alpha0': 'Left'} (added to geo file).
    :param line_params: None or a list containing dictionaries (see function create_transfinite_line_param_dict).

    :return: Dictionary.
    """
    mesh_params = {'volume': volume_name,
                   'surface_list': surface_name_list}
    if direction_dict:
        mesh_params.update(direction_dict)
    if line_params:
        mesh_params['line_params'] = line_params
    return {'transfinite_mesh_params': mesh_params}

def create_transfinite_line_param_dict(edge_list, nof_points, progression=1, comment=''):
    """
    Creates dictionary containing transfinite line parameters.

    :param edge_list: List containing FreeCAD edge objects.
    :param nof_points: Integer.
    :param progression: Number.
    :param comment: String (commented in geo file).

    :return: Dictionary.
    """
    return {'edges': edge_list, 'points': str(nof_points), 'progression': str(progression), 'comment': comment}

def merge_entities_dicts(entities_dicts, name, default_mesh_size=None, add_prefixes=None):
    """ 
    This method merges all the entities_dicts and optionally prefixes the entity names with the 
    name of the entity. As default the solids are not prefixed but the faces are.

    :param entities_dicts: [entities_dict_1, ..., entities_dict_n]
    :param name: string
    :param default_mesh_size: float
    :param add_prefixes: {'solids':bool, 'faces':bool}
    """
    if add_prefixes is None:
        add_prefixes = {'solids': False, 'faces': True}
    entities_out = {'name': name}
    faces = []
    solids = []
    transfinite_mesh_params = []
    for d in entities_dicts:
        for face in d['faces']:
            if face['mesh size'] is None: face['mesh size'] = default_mesh_size
            if add_prefixes['faces']: face_name = d['name'] + '_' + face['name']
            else: face_name = face['name']
            add_entity_in_list(faces, face_name, face['geometric object'], {'mesh size':face['mesh size']})
        for solid in d['solids']:
            if add_prefixes['solids']: solid_name = d['name'] + '_' + solid['name']
            else: solid_name = solid['name']
            if solid['mesh size'] is None: solid['mesh size'] = default_mesh_size
            add_entity_in_list(solids, solid_name, solid['geometric object'], {'mesh size':solid['mesh size']})
        if d.get('transfinite_mesh_params', {}):
            transfinite_mesh_params.append(d['transfinite_mesh_params'])
    entities_out['faces'] = faces
    entities_out['solids'] = solids
    entities_out['transfinite_mesh_params'] = transfinite_mesh_params
    return entities_out

def get_solids_from_entities_dict(entities_dict):
    """
    Return a list of solids from entities dictionary.

    :param entities_dict: entities dictionary
    :return: [solid object 1, ..., solid object n]
    """
    solid_objects = [solid_dict_list['geometric object'] for solid_dict_list in entities_dict['solids']] 
    return solid_objects

def create_mesh_group_and_set_mesh_size(mesh_object, doc, name, mesh_size):
    """
    Creates mesh group with function ObjectsFem.makeMeshGroup.
    Adds property 'mesh_size' to created group and returns object.

    :param mesh_object: FreeCAD mesh object
    :param doc: FreeCAD document.
    :param name: string
    :param mesh_size: float
    :return: MeshGroup object
    """
    # The third argument of makeMeshGroup is True, as we want to use labels,
    # not the names which cannot be changed.
    #
    # WARNING: No other object should have same label than this Mesh Group,
    # otherwise FreeCAD adds numbers to the end of the label to make it unique
    obj = ObjectsFem.makeMeshGroup(doc, mesh_object, True, name+'_group')
    obj.Label = name
    obj.addProperty('App::PropertyFloat', 'mesh_size')
    obj.mesh_size = mesh_size
    return obj

def find_lines_to_transfinite_mesh_params(compound_filter, entities_dict):
    """
    Find edge names from compound_filter and adds them to transfinite mesh parameters.

    Example of list entities_dict['transfinite_mesh_params'] after this function::

        [{'volume': 'A1',
          'surface_list': ['A1_alpha0', 'A1_alpha1']
          'line_params': [{'edges': [edgeObject1, edgeObject2],
                           'lines': ['1', '2'],                  # this function adds these
                           'points': '11',
                           'progression': '1',
                           'comment': ''}]
        }]

    :param compound_filter: FreeCAD compound filter.
    :param entities_dict: A dictionary containing transfinite_mesh_params.
    """
    for mesh_param_dict in entities_dict['transfinite_mesh_params']:
        for line_param_dict in mesh_param_dict.get('line_params', []):
            line_ids = []
            for edge in line_param_dict['edges']:
                line_ids.append(find_compound_filter_edge(compound_filter, edge))
            line_param_dict['lines'] = line_ids

def merge_boundaries(mesh_object, compound_filter, doc, face_entity_dict, compound_face_names, face_name_list,
                     surface_objs, surface_objs_by_compound_face_names, surface_object=None):
    """
    If face in compound_faces is already added to surface:
        - renames surface if there was only one face in existing
        - removes face from existing surface and creates a new surface for merged face
    Creates new surface object (MeshGroup) for compound_faces if needed and surface_object is not given.

    :param mesh_object: FreeCAD mesh object
    :param compound_filter: FreeCAD compound filter
    :param doc: FreeCAD document.
    :param face_entity_dict: dictionary
    :param compound_face_names: tuple containing compound face names in face
    :param face_name_list: list containing already handled face names
    :param surface_objs: list containing created surface objects same order as in face_name_list
    :param surface_objs_by_compound_face_names: dictionary (for checking if face needs to be merged)
    :param surface_object: None or already created surface object
    :return: tuple containing surface object and tuple containing filtered compound names
    """
    filtered_compound_faces = []
    for cface_name in compound_face_names:
        if cface_name in surface_objs_by_compound_face_names:
            surf_obj = surface_objs_by_compound_face_names[cface_name]
            old_face_name = surf_obj.Label
            new_face_name = '{}_{}'.format(old_face_name, face_entity_dict['name'])

            old_found_cface_names = surf_obj.References[0][1]
            filtered_old_found_cface_names = [cfname_i for cfname_i in old_found_cface_names if cfname_i != cface_name]
            if len(filtered_old_found_cface_names) == 0:
                # existing mesh object with new label
                surf_obj.Label = new_face_name
                # update face name in face_name_list
                index_found = face_name_list.index(old_face_name)
                face_name_list[index_found] = new_face_name
            else:
                # update references for existing mesh group
                surf_obj.References = [(compound_filter, tuple(filtered_old_found_cface_names))]
                # handle merged boundary
                if new_face_name in face_name_list:
                    # add merged boundary to existing mesh group
                    surface_index = face_name_list.index(new_face_name)
                    found_cface_names = surface_objs[surface_index].References[0][1]
                    surface_objs[surface_index].References = [(compound_filter, found_cface_names+tuple([cface_name]))]
                else:
                    # create new mesh group for merged boundary
                    surface_objs.append(create_mesh_group_and_set_mesh_size(mesh_object, doc, new_face_name,
                                                                            face_entity_dict['mesh size']))
                    surface_objs[-1].References = [(compound_filter, tuple([cface_name]))]
                    face_name_list.append(new_face_name)
                    surface_objs_by_compound_face_names[cface_name] = surface_objs[-1]
        else:
            filtered_compound_faces.append(cface_name)
            # create new mesh group only once if needed
            if surface_object is None:
                surface_object = create_mesh_group_and_set_mesh_size(mesh_object, doc, face_entity_dict['name'],
                                                                     face_entity_dict['mesh size'])
            surface_objs_by_compound_face_names[cface_name] = surface_object

    return surface_object, tuple(filtered_compound_faces)

def find_boundaries_with_entities_dict(mesh_object, compound_filter, entities_dict, doc, separate_boundaries=False):
    """
    For all faces in entities_dict, the same face in compound filter is added to a Mesh Group.
    All faces with same name in entities_dict are merged into one Mesh Group with the original name.
    If separate_boundaries is True calls function :meth:`find_compound_filter_boundaries`
    with used_compound_face_names list.

    :param mesh_object: FreeCAD mesh object
    :param compound_filter: FreeCAD compound filter
    :param entities_dict: entities dictionary
    :param doc: FreeCAD document.
    :param separate_boundaries: Boolean.
    :return: list containing MeshGroup objects with mesh size.
    """
    surface_objs = []
    face_name_list = []
    all_found_cface_names = []  # needed only for separate boundaries
    surface_objs_by_cface_names = {}
    for num, face in enumerate(entities_dict['faces']):
        if face['name'] in face_name_list:
            # Old name, do not create new MeshGroup
            index_found = face_name_list.index(face['name'])
            found_cface_names = surface_objs[index_found].References[0][1]
            if separate_boundaries:
                cface_names = find_compound_filter_boundaries(compound_filter, face['geometric object'],
                                                              used_compound_face_names=all_found_cface_names)
                all_found_cface_names.extend(cface_names)
            else:
                cface_names = find_compound_filter_boundaries(compound_filter, face['geometric object'])
            surface_obj, filtered_cface_names = merge_boundaries(mesh_object, compound_filter, doc, face,
                                                                 cface_names, face_name_list, surface_objs,
                                                                 surface_objs_by_cface_names,
                                                                 surface_object=surface_objs[index_found])
            if len(filtered_cface_names) > 0:
                surface_obj.References = [(compound_filter, found_cface_names+filtered_cface_names)]
        else:
            # New name, create new MeshGroup
            if separate_boundaries:
                cface_names = find_compound_filter_boundaries(compound_filter, face['geometric object'],
                                                              used_compound_face_names=all_found_cface_names)
                all_found_cface_names.extend(cface_names)
            else:
                cface_names = find_compound_filter_boundaries(compound_filter, face['geometric object'])
            if all_found_cface_names is not None:
                all_found_cface_names.extend(cface_names)
            surface_obj, filtered_cface_names = merge_boundaries(mesh_object, compound_filter, doc, face,
                                                                 cface_names, face_name_list, surface_objs,
                                                                 surface_objs_by_cface_names, surface_object=None)
            if len(filtered_cface_names) > 0:  # new surface_obj is already created
                surface_obj.References = [(compound_filter, filtered_cface_names)]
                surface_objs.append(surface_obj)
                face_name_list.append(face['name'])
    return surface_objs

def find_bodies_with_entities_dict(mesh_object, compound_filter, entities_dict, doc, point_search=True):
    """
    For all solids in entities_dict, the same solid in compound filter is added to a Mesh Group.
    All solids with same name in entities_dict are merged into one Mesh Group with the original name.

    :param mesh_object: FreeCAD mesh object
    :param compound_filter: FreeCAD compound filter
    :param entities_dict: entities dictionary
    :param doc: FreeCAD document.
    :param point_search: bool
    :return: list containing MeshGroup objects with mesh size.
    """
    solid_objs = []
    solid_name_list = []
    for num, solid in enumerate(entities_dict['solids']):
        if solid['name'] in solid_name_list:
            # Old name, do not create new MeshGroup
            index_found = solid_name_list.index(solid['name'])
            found_csolid_names = solid_objs[index_found].References[0][1]
            csolid_names = find_compound_filter_solids(compound_filter, solid['geometric object'].Shape, point_search)
            found_csolid_names = found_csolid_names + csolid_names
            solid_objs[index_found].References = [(compound_filter, found_csolid_names)]
        else:
            # New name, create new MeshGroup
            solid_objs.append(create_mesh_group_and_set_mesh_size(mesh_object, doc, solid['name'], solid['mesh size']))
            csolid_names = find_compound_filter_solids(compound_filter, solid['geometric object'].Shape, point_search)
            solid_objs[-1].References = [(compound_filter, csolid_names)]
            solid_name_list.append(solid['name'])
    return solid_objs

def define_mesh_sizes_with_mesh_groups(mesh_object, mesh_group_list, doc, ignore_list=None):
    """
    Meshregions are needed to have regionwise mesh density parameters.
    The mesh element length is the third parameter given in makeMeshRegion.
    Each mesh group in mesh_group_list needs to know its
    mesh size (created with function :meth:`create_mesh_group_and_set_mesh_size`).

    :param mesh_object: FreeCAD mesh object
    :param mesh_group_list: list containing MeshGroups
    :param doc: FreeCAD document.
    :param ignore_list: None or list containing solid names which mesh size is not defined.
    """
    if ignore_list is None:
        ignore_list = []
    for mesh_group in mesh_group_list:
        if mesh_group.Label not in ignore_list:
            mesh_region = ObjectsFem.makeMeshRegion(doc, mesh_object, mesh_group.mesh_size, mesh_group.Name+'_region')
            mesh_region.References = [(mesh_group.References[0][0], mesh_group.References[0][1])]

def define_mesh_sizes(mesh_object, compound_filter, entities_dict, doc, point_search=True, ignore_list=None):
    """
    Meshregions are needed to have regionwise mesh density parameters. 
    The mesh element length is the third parameter given in makeMeshRegion. 

    :param mesh_object: FreeCAD mesh object
    :param compound_filter: FreeCAD compound filter
    :param entities_dict: entities dictionary
    :param doc: FreeCAD document.
    :param point_search: bool
    :param ignore_list: None or list containing solid names which mesh size is not defined.
    """
    if ignore_list is None:
        ignore_list = []
    solid_objs = []
    solid_name_list = []
    for num, solid in enumerate(entities_dict['solids']):
        if solid['name'] in ignore_list:
            continue
        if solid['name'] in solid_name_list:
            # Old name, do not create new MeshGroup
            index_found = solid_name_list.index(solid['name'])
            found_csolid_names = solid_objs[index_found].References[0][1]
            csolid_names = find_compound_filter_solids(compound_filter, solid['geometric object'].Shape, point_search)
            solid_objs[index_found].References = [(compound_filter, found_csolid_names+csolid_names)]
        else:
            # New name, create new MeshGroup
            solid_objs.append(ObjectsFem.makeMeshRegion(doc, mesh_object, solid['mesh size'], solid['name']+'_region'))
            csolid_names = find_compound_filter_solids(compound_filter, solid['geometric object'].Shape, point_search)
            solid_objs[-1].References = [(compound_filter, csolid_names)]
            solid_name_list.append(solid['name'])


