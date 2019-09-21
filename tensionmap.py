#    Tension Map Script is a Blender add-on that adds stretch information to desired meshes
#    Copyright (C) 2019 Scott Winkelmann
#    Copyright (C) 2014 Jean-Francois Gallant
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import bpy
import bmesh
from dataclasses import dataclass

bl_info = {
    "name":        "Tension Map Script",
    "author":      "Scott Winkelmann <scottlandart@gmail.com>, Jean-Francois Gallant (PyroEvil)",
    "version":     (2, 3, 0),
    "blender":     (2, 80, 72),
    "location":    "Properties Panel > Data Tab",
    "description": "This add-on adds stretch and squeeze information to desired meshes",
    "warning":     "",
    "wiki_url":    "https://github.com/ScottishCyclops/tensionmap",
    "tracker_url": "https://github.com/ScottishCyclops/tensionmap/issues",
    "category":    "Object"
}

geometry_cache = dict()
last_processed_frame = None
number_of_color_channels = 4
# list of modifiers that we will keep to compute the deformation
# TODO: update based on list in docs
# https://docs.blender.org/api/blender2.8/bpy.types.Modifier.html#bpy.types.Modifier.type
kept_modifiers = ["ARMATURE", "MESH_CACHE", "CAST", "CURVE", "HOOK",
                  "LAPLACIANSMOOTH", "LAPLACIANDEFORM",
                  "LATTICE", "MESH_DEFORM", "SHRINKWRAP", "SIMPLE_DEFORM",
                  "SMOOTH", "WARP", "WAVE", "CLOTH",
                  "SOFT_BODY"]

tm_update_modes = ["OBJECT", "WEIGHT_PAINT", "VERTEX_PAINT"]


@dataclass
class GeometryData:
    original_edge_lengths: list
    vertex_color_index_mapping: dict


def calculate_original_edge_lengths(obj):
    """
    Calculates the edge length of an object, without modifiers
    :param obj: the object to operate on
    :return: returns a list of edge lengths
    """
    number_of_edges = len(obj.data.edges)
    edge_lengths = [0] * number_of_edges
    bmesh_orig = bmesh.new()
    bmesh_orig.from_mesh(obj.data)
    bmesh_orig.edges.ensure_lookup_table()
    for i in range(number_of_edges):
        edge_lengths[i] = bmesh_orig.edges[i].calc_length()
    return edge_lengths


def calculate_vertex_color_index_mapping(obj):
    """
    Calculates an dict for mapping regular vertex indices to loop-based vertex indices
    :param obj: the object to operate on
    :return: returns the mapping dict
    """
    index_mapping = dict()
    index = 0
    for polygon in obj.data.polygons:
        for loop_vertex_idx, loop_idx in enumerate(polygon.loop_indices):
            vertex_idx = polygon.vertices[loop_vertex_idx]
            index_mapping[index] = vertex_idx
            index = index + 1
    return index_mapping


def update_geometry_cache_for_object(obj):
    """
    Updates the geometry cache for an object by filling it with new values or deleting it
    :param obj: the object to operate on
    :return: nothing
    """
    if obj.data.tm_enable_geometry_cache:
        geometry_cache[obj] = GeometryData(calculate_original_edge_lengths(obj),
                                           calculate_vertex_color_index_mapping(obj))
    else:
        if obj in geometry_cache:
            del geometry_cache[obj]


def get_or_create_vertex_group(obj, group_name):
    """
    Creates a new vertex group and initializes it only if it doesn't exist then returns it
    :param obj: the object to operate on
    :param group_name: the name of the group to get or create
    :return: the the vertex group
    """
    if group_name not in obj.vertex_groups:
        obj.vertex_groups.new(name=group_name)
        for i in range(len(obj.data.vertices)):
            obj.vertex_groups[group_name].add([i], 0.0, "REPLACE")
    return obj.vertex_groups[group_name]


def get_or_create_vertex_colors(obj, colors_name):
    """
    Creates new vertex colors data only if it doesn't exist then returns it
    :param obj: the object to operate on
    :param colors_name: the name of the colors data to get or create
    :return: the vertex colors
    """
    if colors_name not in obj.data.vertex_colors:
        obj.data.vertex_colors.new(name=colors_name)
    return obj.data.vertex_colors[colors_name]


def tm_update(obj, context):
    """
    Updates the tension map for the given object
    :param obj: the object to update
    :param context: the context of the operation
    :return: nothing
    """
    # only care about meshes
    if obj.type != "MESH":
        return

    # only care about meshes with tensionmap activated
    if not obj.data.tm_active:
        return

    # only care if some method of output is activated, to avoid overhead
    if not obj.data.tm_enable_vertex_colors and not obj.data.tm_enable_vertex_groups:
        return

    # can't edit vertex group and so on when in other modes
    if obj.mode not in tm_update_modes:
        return

    # check vertex groups and vertex colors existence, add them otherwise
    if obj.data.tm_enable_vertex_groups:
        group_squeeze = get_or_create_vertex_group(obj, "tm_squeeze")
        group_stretch = get_or_create_vertex_group(obj, "tm_stretch")

    # optimization
    num_modifiers = len(obj.modifiers)
    range_modifiers = range(num_modifiers)
    num_vertices = len(obj.data.vertices)

    # save modifier viewport show state
    # temporarily hide modifiers to create a deformed mesh data
    show_original_state = [False] * num_modifiers
    for i in range_modifiers:
        modifier = obj.modifiers[i]
        show_original_state[i] = modifier.show_viewport

        # if the modifier is not one we keep for the deformed mesh, hide it for now
        # TODO: use a bool property on each modifier to determine if it should be kept
        # it appears a property can't be added to the Modifier type
        # another way will need to be found
        if modifier.type not in kept_modifiers:
            modifier.show_viewport = False

    # this converts the object to a mesh
    # as it is currently visible in the viewport
    depsgraph = context.evaluated_depsgraph_get()
    object_eval = obj.evaluated_get(depsgraph)
    deformed_mesh = object_eval.to_mesh()

    # restore modifiers viewport show state
    for i in range_modifiers:
        obj.modifiers[i].show_viewport = show_original_state[i]

    # array to store new weight for each vertices
    weights = [0.0] * num_vertices

    # referencing the cache data
    # it would be simpler to just generate the needed GeometryData for any non-cached object here,
    # but then we would go through the edge-loop twice, when calculating the edge lengths
    if obj.data.tm_enable_geometry_cache:
        if obj not in geometry_cache:
            update_geometry_cache_for_object(obj)
        geometry_data = geometry_cache[obj]
    else:
        original_bmesh = bmesh.new()
        original_bmesh.from_mesh(obj.data)
        original_bmesh.edges.ensure_lookup_table()
    deformed_bmesh = bmesh.new()
    deformed_bmesh.from_mesh(deformed_mesh)
    deformed_bmesh.edges.ensure_lookup_table()
    num_edges = len(obj.data.edges)
    
    # calculate the new weights
    for i in range(num_edges):
        if obj.data.tm_enable_geometry_cache:
            original_edge_length = geometry_data.original_edge_lengths[i]
        else:
            original_edge_length = original_bmesh.edges[i].calc_length()
        deformed_edge_length = deformed_bmesh.edges[i].calc_length()
        deformation_factor = (original_edge_length - 
                              deformed_edge_length) * obj.data.tm_multiply
        first_vertex, second_vertex = deformed_bmesh.edges[i].verts

        # store the weights by subtracting to overlay all the factors for each vertex
        weights[first_vertex.index] -= deformation_factor
        weights[second_vertex.index] -= deformation_factor


    # delete the temporary deformed mesh
    object_eval.to_mesh_clear()

    # create vertex color list for faster access only if vertex color is activated
    if obj.data.tm_enable_vertex_colors:
        vertex_colors = [[0.0] * number_of_color_channels] * num_vertices

    # lambda for clamping between min and max
    clamp = lambda value, lower, upper: lower if value < lower else upper if value > upper else value

    # calculate the new values
    # store them in the vertex_colors array if the feature is active
    # store them in the vertex groups if the feature is active
    for i in range(num_vertices):
        stretch_value = obj.data.tm_minimum
        squeeze_value = obj.data.tm_minimum

        if weights[i] >= 0:
            # positive: stretched
            stretch_value = clamp(weights[i], obj.data.tm_minimum, obj.data.tm_maximum)
        else:
            # negative: squeezed
            # invert weights to keep only positive values
            squeeze_value = clamp(-weights[i], obj.data.tm_minimum, obj.data.tm_maximum)

        if obj.data.tm_enable_vertex_groups:
            add_index = [i]
            group_squeeze.add(add_index, squeeze_value, "REPLACE")
            group_stretch.add(add_index, stretch_value, "REPLACE")

        if obj.data.tm_enable_vertex_colors:
            # red, green, blue, alpha
            vertex_colors[i] = (stretch_value, squeeze_value, 0.0, 1.0)

    if obj.data.tm_enable_geometry_cache:
        vertex_color_index_mapping = geometry_data.vertex_color_index_mapping
    else:
        vertex_color_index_mapping = calculate_vertex_color_index_mapping(obj)
    # store the calculated vertex colors if the feature is active
    if obj.data.tm_enable_vertex_colors:
        colors_tension_data = get_or_create_vertex_colors(obj, "tm_tension").data
        tension_color_size = len(colors_tension_data)
        for i in range(tension_color_size):
            colors_tension_data[i].color = vertex_colors[vertex_color_index_mapping[i]]


def tm_update_handler(scene):
    """
    Updates the tension map for all objects in the scene
    This function will be called by Blender every frame
    :param scene: the scene to operate on
    :return: nothing
    """
    global last_processed_frame

    # avoid executing the operations if the frame hasn't really changed
    if last_processed_frame == scene.frame_current:
        return

    last_processed_frame = scene.frame_current

    # TODO: store tm objects in a special array to avoid looping over all objects in the scene
    for obj in scene.objects:
        tm_update(obj, bpy.context)


def tm_update_selected(self, context):
    """
    Updates the tension map for the selected object
    :param context: the context in which the selected object is
    :return: nothing
    """
    tm_update(context.object, context)


def tm_update_geometry_cache(self, context):
    """
    Updates the geometry cache for the selected object, then updates the tension map
    :param context: the context in which the selected object is
    :return: nothing
    """
    update_geometry_cache_for_object(context.object)

    tm_update(context.object, context)


class TmUpdateSelected(bpy.types.Operator):
    """Update tension map for selected object"""

    # this operator is simply a wrapper for the tm_update_selected function
    bl_label = "Update tension map"
    bl_idname = "tm.update_selected"
    bl_options = {"REGISTER"}

    def execute(self, context):
        tm_update_selected(self, context)
        return {"FINISHED"}

    def invoke(self, context, event):
        return self.execute(context)


class TmUpdateGeometryCache(bpy.types.Operator):
    """Update geometry cache for selected object. \nHas to be done manually when the object changes."""

    # this operator is simply a wrapper for the update_geometry_cache function
    bl_label = "Update cache"
    bl_idname = "tm.update_geometry_cache"
    bl_options = {"REGISTER"}

    def execute(self, context):
        tm_update_geometry_cache(self, context)
        return {"FINISHED"}

    def invoke(self, context, event):
        return self.execute(context)


class TmPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""

    bl_label = "Tension Map Script"
    bl_idname = "OBJECT_PT_tm"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    def draw_header(self, context):
        if context.object.type != "MESH":
            return

        row = self.layout.row()
        row.prop(context.object.data, "tm_active", text="")

    def draw(self, context):
        if context.object.type != "MESH":
            return

        obj = context.object.data

        col1 = self.layout.column()
        col1.active = obj.tm_active
        col1.operator("tm.update_selected", icon="FILE_REFRESH")
        row1 = col1.row()
        row1Col1 = row1.column()
        row1Col2 = row1.column()
        row1Col1.prop(obj, "tm_enable_geometry_cache", toggle=True,
                      icon='CHECKBOX_HLT' if obj.tm_enable_geometry_cache else 'CHECKBOX_DEHLT', text="Geometry Cache")
        row1Col2.operator("tm.update_geometry_cache", icon="FILE_REFRESH")
        row1Col2.active = obj.tm_enable_geometry_cache

        col1.prop(obj, "tm_enable_vertex_groups")
        col1.prop(obj, "tm_enable_vertex_colors")
        col1.prop(obj, "tm_multiply")
        col1.prop(obj, "tm_minimum")
        col1.prop(obj, "tm_maximum")

        '''
        # TODO: finish implementing interface for choosing modifiers
        flow.separator()

        col2 = flow.column()
        col2.enabled = context.object.data.tm_active
        col2.label(text="Modifiers to use when computing tension")
        list = col2.box()

        modifiers = context.object.modifiers

        for i in range(len(modifiers)):
            row = list.row()
            row.prop(modifiers[i], "use_for_tension", text=modifiers[i].name)
        '''


def add_props():
    """
    Method responsible for adding properties to the mesh type
    :return: nothing
    """
    bpy.types.Mesh.tm_active = bpy.props.BoolProperty(
        name="tm_active",
        description="Activate tension map on this mesh",
        default=False,
        update=tm_update_selected)
    bpy.types.Mesh.tm_multiply = bpy.props.FloatProperty(
        name="Multiplier",
        description="Tension map intensity multiplier",
        min=0.0,
        max=9999.0,
        default=1.0,
        update=tm_update_selected)
    bpy.types.Mesh.tm_minimum = bpy.props.FloatProperty(
        name="Minimum",
        description="Tension map minimum value",
        min=0.0,
        max=1.0,
        default=0.0,
        update=tm_update_selected)
    bpy.types.Mesh.tm_maximum = bpy.props.FloatProperty(
        name="Maximum",
        description="Tension map maximum value",
        min=0.0,
        max=1.0,
        default=1.0,
        update=tm_update_selected)
    bpy.types.Mesh.tm_enable_vertex_groups = bpy.props.BoolProperty(
        name="Enable Vertex Group Output",
        description="Whether to enable vertex groups",
        default=False,
        update=tm_update_selected)
    bpy.types.Mesh.tm_enable_vertex_colors = bpy.props.BoolProperty(
        name="Enable Vertex Color Output",
        description="Whether to enable vertex colors",
        default=False,
        update=tm_update_selected)
    bpy.types.Mesh.tm_enable_geometry_cache = bpy.props.BoolProperty(
        name="Enable Geometry Cache",
        description="Improve realtime performance by pre-calculating some geometry data.\n"
                    "An update to the mesh will require a manual cache update",
        default=False,
        update=tm_update_geometry_cache)


def remove_props():
    """
    Method responsible for removing properties from the mesh type
    :return: nothing
    """
    del bpy.types.Mesh.tm_active
    del bpy.types.Mesh.tm_multiply
    del bpy.types.Mesh.tm_minimum
    del bpy.types.Mesh.tm_maximum
    del bpy.types.Mesh.tm_enable_vertex_groups
    del bpy.types.Mesh.tm_enable_vertex_colors
    del bpy.types.Mesh.tm_enable_geometry_cache


def add_handlers():
    """
    Method responsible for adding the handlers for the tm_update_all method
    :return: nothing
    """
    bpy.app.handlers.persistent(tm_update_handler)
    bpy.app.handlers.frame_change_post.append(tm_update_handler)


def remove_handlers():
    """
    Method responsible for removing the handlers for the tm_update_all method
    :return: nothing
    """
    bpy.app.handlers.frame_change_post.remove(tm_update_handler)


def register():
    """
    Method called by Blender when enabling the add-on
    :return: nothing
    """
    add_props()
    bpy.utils.register_class(TmUpdateGeometryCache)
    bpy.utils.register_class(TmUpdateSelected)
    bpy.utils.register_class(TmPanel)
    add_handlers()


def unregister():
    """
    Method called by Blender when disabling or removing the add-on
    :return: nothing
    """
    remove_handlers()
    bpy.utils.unregister_class(TmPanel)
    bpy.utils.unregister_class(TmUpdateSelected)
    bpy.utils.unregister_class(TmUpdateGeometryCache)
    remove_props()


# if the script is run directly, register it
if __name__ == "__main__":
    register()
