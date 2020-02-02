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
import numpy as np
from numba import njit

bl_info = {
    "name":        "Tension Map Script",
    "author":      "Scott Winkelmann <scottlandart@gmail.com>, Jean-Francois Gallant (PyroEvil)",
    "version":     (2, 2, 0),
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
    mesh = obj.data

    # restore modifiers viewport show state
    for i in range_modifiers:
        obj.modifiers[i].show_viewport = show_original_state[i]

    edges = read_edges(mesh)
    
    verts_original = read_vertices(mesh)
    
    verts_deformed = read_vertices(deformed_mesh)
        
    original_edge_len = np.linalg.norm(verts_original[edges[:,0]] 
    - verts_original[edges[:,1]],axis=1)
        
    deformed_edge_len = np.linalg.norm(verts_deformed[edges[:,0]] 
    - verts_deformed[edges[:,1]],axis=1)
        
    deform_factor = (original_edge_len - deformed_edge_len) * obj.data.tm_multiply
        
    weights = np.zeros(num_vertices,dtype='float32')
    
    get_weights(weights,edges,deform_factor,num_vertices)

    # delete the temporary deformed mesh
    object_eval.to_mesh_clear()

    stretch = np.zeros(num_vertices,dtype='float32')
    squeeze = np.zeros(num_vertices,dtype='float32')
    
    calc_values(stretch,squeeze,num_vertices,weights,0,1)
    
    if obj.data.tm_enable_vertex_groups:
        for i in range(num_vertices):
            group_squeeze.add([i], squeeze[i], "REPLACE")
            group_stretch.add([i], stretch[i], "REPLACE") 
               
    if obj.data.tm_enable_vertex_colors:
        if obj.data.tm_mesh_type == 'Mixed':
            vertex_colors = [0.0] * (number_of_tm_channels * num_vertices)
    
            for i in range(num_vertices):
                # red
                vertex_colors[i * number_of_tm_channels] = stretch[i]
                # green
                vertex_colors[i * number_of_tm_channels + 1] = squeeze[i]
        
            # store the calculated vertex colors if the feature is active
        
            if obj.data.tm_enable_vertex_colors:
                colors_tension = get_or_create_vertex_colors(obj, "tm_tension")
                # this is heavy, but vertex colors are stored by vertex loop
                # and there is no simpler way to do it (it would seem)
                for poly_idx in range(len(obj.data.polygons)):
                    polygon = obj.data.polygons[poly_idx]
                    for loop_vertex_idx, loop_idx in enumerate(polygon.loop_indices):
                        vertex_color = colors_tension.data[loop_idx]
                        vertex_idx = polygon.vertices[loop_vertex_idx]
                        # replace the color by a 4D vector, using 0 for blue and 1 for alpha
                        vertex_color.color = (vertex_colors[vertex_idx * number_of_tm_channels],
                                              vertex_colors[vertex_idx * number_of_tm_channels + 1], 0, 1)
        
        else:
            if 'tm_tension' not in obj.data.vertex_colors:
                obj.data.vertex_colors.new(name='tm_tension')
            if obj.data.tm_mesh_type == 'Quads':
                poly_idx = 4
            else:
                poly_idx = 3

            vertex_colors = np.zeros(num_vertices*number_of_tm_channels,dtype='float32')

            get_colors(vertex_colors,num_vertices,number_of_tm_channels,stretch,squeeze)

            vertex_colors_data = read_vertex_color_data(mesh,poly_idx)

            vertex_idxs = read_polygon_vertices(mesh,poly_idx)

            num_polygons = len(mesh.polygons)

            loop_indices = np.arange(num_polygons*poly_idx).reshape(num_polygons,poly_idx)

            change_colors(num_polygons,loop_indices,vertex_colors_data,vertex_idxs,vertex_colors,number_of_tm_channels)

            vertex_colors_data = vertex_colors_data.reshape(len(mesh.polygons)*poly_idx*4)

            mesh.vertex_colors['tm_tension'].data.foreach_set('color',vertex_colors_data)

def read_vertex_color_data(mesh,poly_idx):
    vertex_colors = np.zeros(len(mesh.polygons)*poly_idx*4, dtype='float32')
    mesh.vertex_colors['tm_tension'].data.foreach_get('color',vertex_colors)
    return (vertex_colors.reshape(len(mesh.polygons)*poly_idx,4))
    
def read_polygon_vertices(mesh,poly_idx):
        verts = np.zeros(len(mesh.polygons)*poly_idx, dtype='int32')
        mesh.polygons.foreach_get('vertices',verts)
        return(verts.reshape(len(mesh.polygons),poly_idx))
        
def read_vertices(mesh):
    verts = np.zeros((len(mesh.vertices)*3), dtype='float32')
    mesh.vertices.foreach_get("co", verts)
    return (verts.reshape(len(mesh.vertices), 3))

def read_edges(mesh):
    edges = np.zeros((len(mesh.edges)*2), dtype='int32')
    mesh.edges.foreach_get("vertices", edges)
    return (edges.reshape(len(mesh.edges), 2))
    
@njit()
def change_colors(num_polygons,loop_indices,vertex_colors_data,vertex_idxs,vertex_colors,num_of_channels):
    for poly_idx in range(num_polygons):            
        for loop_vertex_idx, loop_idx in enumerate(loop_indices[poly_idx,:]):
            vertex_idx = vertex_idxs[poly_idx,loop_vertex_idx]                    
            vertex_colors_data[loop_idx,:] = np.array([vertex_colors[vertex_idx * 2],
                                  vertex_colors[vertex_idx * 2 + 1], 0, 1])

@njit()
def get_weights(wg,edges,deform_factor,num_vertices):
    for i in range(len(deform_factor)):
        for j in edges[i,:]:
            wg[j] -= deform_factor[i]
        
@njit()
def get_colors(vertex_colors,num_vertices,channels,stretch,squeeze):        
        for i in range(num_vertices):
            vertex_colors[i * channels] = stretch[i]
            vertex_colors[i * channels + 1] = squeeze[i]

@njit()
def calc_values(stretch_values,squeeze_values,num_vertices,weights,min_val,max_val):        
        for i in range(num_vertices):            
            if weights[i] >= 0:
                stretch_values[i] = max(min_val, min(
                        max_val, weights[i]))
                squeeze_values[i] = min_val
            else:
                squeeze_values[i] = max(min_val, min(
                        max_val, -weights[i]))
                stretch_values[i] = min_val



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
        row1.prop(context.object.data, "tm_enable_vertex_groups",
                  text="Enable Vertex Groups")
        row1.prop(context.object.data, "tm_enable_vertex_colors",
                  text="Enable Vertex Colors")
        row1.prop(context.object.data, "tm_mesh_type", text="Mesh type")
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
        description="Whether to enable vertex colors",
        default=False,
        update=tm_update_selected)
    bpy.types.Mesh.tm_mesh_type = bpy.props.EnumProperty(
        name="tm_mesh_type",
        items=(
               ("Quads", "Quads only", "Select if mesh is build from quads"),
               ("Tris", "Triangles only", "Select if mesh is build from triangles"),
               ("Mixed", "Mixed", "Select if mesh is build from different types of polygons (slower)")
            ),
        )


def remove_props():
    """
    Method responsible for removing properties from the mesh type
    :return: nothing
    """
    del bpy.types.Mesh.tm_active
    del bpy.types.Mesh.tm_multiply
    del bpy.types.Mesh.tm_minimum
    del bpy.types.Mesh.tm_maximum
    del bpy.types.Mesh.tm_mesh_type
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
