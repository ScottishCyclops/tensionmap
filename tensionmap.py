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

bl_info = {
    "name":        "Tension Map Script",
    "author":      "Scott Winkelmann <scottlandart@gmail.com>, Jean-Francois Gallant (PyroEvil)",
    "version":     (2, 1, 1),
    "blender":     (2, 80, 72),
    "location":    "Properties Panel > Data Tab",
    "description": "This add-on adds stretch and squeeze information to desired meshes",
    "warning":     "",
    "wiki_url":    "https://github.com/ScottishCyclops/tensionmap",
    "tracker_url": "https://github.com/ScottishCyclops/tensionmap/issues",
    "category":    "Object"
}

last_processed_frame = None
number_of_tm_channels = 2
original_edge_lengths_per_obj = dict()
# list of modifiers that we will keep to compute the deformation
# TODO: update based on list in docs
# https://docs.blender.org/api/blender2.8/bpy.types.Modifier.html#bpy.types.Modifier.type
kept_modifiers = ["ARMATURE", "MESH_CACHE", "CAST", "CURVE", "HOOK",
                  "LAPLACIANSMOOTH", "LAPLACIANDEFORM",
                  "LATTICE", "MESH_DEFORM", "SHRINKWRAP", "SIMPLE_DEFORM",
                  "SMOOTH", "WARP", "WAVE", "CLOTH",
                  "SOFT_BODY"]

tm_update_modes = ["OBJECT", "WEIGHT_PAINT", "VERTEX_PAINT"]


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

    global kept_modifiers

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
        show_original_state[i] = obj.modifiers[i].show_viewport

        # if the modifier is not one we keep for the deformed mesh, hide it for now
        # TODO: use a bool property on each modifier to determine if it should be kept
        # it appears a property can't be added to the Modifier type
        # another way will need to be found
        if obj.modifiers[i].type not in kept_modifiers:
            obj.modifiers[i].show_viewport = False

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

    global original_edge_lengths_per_obj
    if not obj.name in original_edge_lengths_per_obj:
        original_edge_lengths_per_obj[obj.name] = tm_update_original_edges(obj)
        
    original_edge_lengths = original_edge_lengths_per_obj[obj.name]            
    # calculate the new weights
    for i in range(len(obj.data.edges)):
        edge = obj.data.edges[i]
        first_vertex = edge.vertices[0]
        second_vertex = edge.vertices[1]

        original_edge_length = original_edge_lengths[i]
        deformed_edge_length = (
            deformed_mesh.vertices[first_vertex].co - deformed_mesh.vertices[second_vertex].co).length

        deformation_factor = (original_edge_length -
                              deformed_edge_length) * obj.data.tm_multiply

        # store the weights by subtracting to overlay all the factors for each vertex
        weights[first_vertex] -= deformation_factor
        weights[second_vertex] -= deformation_factor

    # delete the temporary deformed mesh
    object_eval.to_mesh_clear()
    
    # create vertex color list for faster access
    vertex_colors = [0]*(number_of_tm_channels*num_vertices)
    # put the new values in the vertex groups
    for i in range(num_vertices):
        add_index = [i]
        stretch_value = obj.data.tm_minimum
        squeeze_value = obj.data.tm_minimum
        if weights[i] >= 0:
            # positive: stretched
            stretch_value = max(obj.data.tm_minimum, min(obj.data.tm_maximum, weights[i]))
        else:
            # negative: squeezed
            # invert weights to keep only positive values
            squeeze_value = max(obj.data.tm_minimum, min(obj.data.tm_maximum, -weights[i]))
        if obj.data.tm_enable_vertex_groups:
            group_squeeze.add(add_index, squeeze_value, "REPLACE")
            group_stretch.add(add_index, stretch_value, "REPLACE")
        vertex_colors[i*number_of_tm_channels] = stretch_value  # red
        vertex_colors[i*number_of_tm_channels+1] = squeeze_value  # green

    if obj.data.tm_enable_vertex_colors:
        colors_tension = get_or_create_vertex_colors(obj, "tm_tension")
        # put the new values from the vertex groups in the vertex colors
        # this is heavy, but vertex colors are stored by vertex loop
        # and there is no simpler way to do it (it would seem)
        for poly_idx in range(len(obj.data.polygons)):
            polygon = obj.data.polygons[poly_idx]
            for loop_vertex_idx, loop_idx in enumerate(polygon.loop_indices):
                vertex_color = colors_tension.data[loop_idx]
                vertex_idx = polygon.vertices[loop_vertex_idx]
                vertex_color.color = (vertex_colors[vertex_idx*number_of_tm_channels],
                                      vertex_colors[vertex_idx*number_of_tm_channels+1],0,1)
                        
def tm_update_original_edges(obj):
    """
    Updates the original edges of an object
    :param obj: the object to operate on
    :return: the updated original edges of an object
    """
    num_vertices = len(obj.data.vertices)
    original_edge_lengths = [0]*len(obj.data.edges)
    for i in range(len(obj.data.edges)):
        edge = obj.data.edges[i]
        first_vertex_idx = edge.vertices[0]
        second_vertex_idx = edge.vertices[1]
        original_edge_lengths[i] = (obj.data.vertices[first_vertex_idx].co - 
                                    obj.data.vertices[second_vertex_idx].co).length
    return original_edge_lengths

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

    global original_edge_lengths_per_obj
    if context.object.data.tm_active:
        original_edge_lengths_per_obj[context.object.name]=tm_update_original_edges(context.object)
    else:
        del original_edge_lengths_per_obj[context.object.name]
    print(original_edge_lengths_per_obj.keys())
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

        flow = self.layout.column()

        row1 = flow.column()
        row1.active = context.object.data.tm_active
        row1.operator("tm.update_selected")
        row1.prop(context.object.data, "tm_enable_vertex_groups", text="Enable Vertex Groups")
        row1.prop(context.object.data, "tm_enable_vertex_colors", text="Enable Vertex Colors")
        row1.prop(context.object.data, "tm_multiply", text="Multiplier")
        row1.prop(context.object.data, "tm_minimum", text="Minimum")
        row1.prop(context.object.data, "tm_maximum", text="Maximum")

        '''
        # TODO: finish implementing interface for choosing modifiers
        flow.separator()

        row2 = flow.column()
        row2.enabled = context.object.data.tm_active
        row2.label(text="Modifiers to use when computing tension")
        list = row2.box()

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
            name="tm_multiply",
            description="Tension map intensity multiplier",
            min=0.0,
            max=9999.0,
            default=1.0,
            update=tm_update_selected)
    bpy.types.Mesh.tm_minimum = bpy.props.FloatProperty(
            name="tm_minimum",
            description="Tension map minimum value",
            min=0.0,
            max=1.0,
            default=0.0,
            update=tm_update_selected)
    bpy.types.Mesh.tm_maximum = bpy.props.FloatProperty(
            name="tm_maximum",
            description="Tension map maximum value",
            min=0.0,
            max=1.0,
            default=1.0,
            update=tm_update_selected)
    bpy.types.Mesh.tm_enable_vertex_groups = bpy.props.BoolProperty(
            name="tm_enable_vertex_groups",
            description="Whether to enable vertex groups",
            default=False,
            update=tm_update_selected)
    bpy.types.Mesh.tm_enable_vertex_colors = bpy.props.BoolProperty(
            name="tm_enable_vertex_colors",
            description="Whether to enable vertex colors (takes longer to process each frame)",
            default=False,
            update=tm_update_selected)


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
    remove_props()


# if the script is run directly, register it
if __name__ == "__main__":
    register()
