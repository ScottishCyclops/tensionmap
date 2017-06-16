#    Tension Map Script is a Blender add-on
#    Copyright (C) 2017 Scott Winkelmann
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
    "version":     (1, 0, 1),
    "blender":     (2, 78, 0),
    "location":    "Properties Panel > Data Tab",
    "description": "This add-on adds stretch and squeeze information to desired meshes",
    "warning":     "",
    "wiki_url":    "http://pyroevil.com/",
    "tracker_url": "",
    "category":    "Object"
}

last_processed_frame = None
accepted_modifiers = ["ARMATURE", "MESH_CACHE", "CAST", "CURVE", "HOOK", "LAPLACIANSMOOTH", "LAPLACIANDEFORM",
                      "LATTICE", "MESH_DEFORM", "SHRINKWRAP", "SIMPLE_DEFORM", "SMOOTH", "WARP", "WAVE", "CLOTH",
                      "SOFT_BODY"]


def get_or_create_vertex_group(obj, group_name):
    """
    Creates a new vertex group and initializes it only if it doesn't exist then returns it's index
    :param obj: the object to operate on
    :param group_name: the name of the group to get or create
    :return: the index of the vertex group
    """

    if group_name not in obj.vertex_groups:
        obj.vertex_groups.new(name=group_name)
        for i in range(len(obj.data.vertices)):
            obj.vertex_groups[group_name].add([i], 0.0, "REPLACE")
    return obj.vertex_groups[group_name].index


def get_or_create_vertex_colors(obj, colors_name):
    """
    Creates new vertex colors data only if it doesn't exist then returns it's name
    :param obj: the object to operate on
    :param colors_name: the name of the colors data to get or create
    :return: the name of the vertex colors
    """

    if colors_name not in obj.data.vertex_colors:
        obj.data.vertex_colors.new(name=colors_name)
    return obj.data.vertex_colors[colors_name].name


def tm_update(obj, scene):
    """
    Updates the tension map for the given object
    :param obj: the object to update
    :param scene: the scene in which it resides
    :return: nothing
    """

    if obj.type == "MESH":
        if obj.data.tm_active:
            global accepted_modifiers

            # check vertex groups and vertex colors existence, add them otherwise
            index_squeeze = get_or_create_vertex_group(obj, "tm_stretch")
            index_stretch = get_or_create_vertex_group(obj, "tm_squeeze")
            index_tension = get_or_create_vertex_colors(obj, "tm_tension")

            # save modifier viewport show state
            # temporarily hide modifiers to copy mesh data
            show_original_state = [False] * len(obj.modifiers)
            for i in range(len(obj.modifiers)):
                show_original_state[i] = obj.modifiers[i].show_viewport

                # TODO: clear the next statement out
                if obj.modifiers[i].type not in accepted_modifiers:
                    obj.modifiers[i].show_viewport = False

            mesh = obj.to_mesh(scene=scene, apply_modifiers=True, settings="PREVIEW")

            # restore modifiers viewport show state
            for i in range(len(obj.modifiers)):
                obj.modifiers[i].show_viewport = show_original_state[i]

            # array to store new weight for each vertices
            weights = [0.0] * len(obj.data.vertices)

            # calculating the new weights
            for edge in obj.data.edges:
                first_vertex = edge.vertices[0]
                second_vertex = edge.vertices[1]

                deformed_edge_length = (obj.data.vertices[first_vertex].co - obj.data.vertices[second_vertex].co).length
                original_edge_length = (mesh.vertices[first_vertex].co - mesh.vertices[second_vertex].co).length

                factor = (deformed_edge_length - original_edge_length) * obj.data.tm_multiply
                weights[first_vertex] -= factor
                weights[second_vertex] -= factor

            # delete the temporary non-deformed mesh
            bpy.data.meshes.remove(mesh)

            # we put the new values in the vertex groups
            # if the weight value is positive, it is stretched
            # otherwise, it is squeezed
            for i in range(len(obj.data.vertices)):
                if weights[i] >= 0:
                    obj.vertex_groups[index_stretch].add([i], weights[i], "REPLACE")
                    obj.vertex_groups[index_squeeze].add([i], 0.0, "REPLACE")
                else:
                    obj.vertex_groups[index_stretch].add([i], 0.0, "REPLACE")
                    obj.vertex_groups[index_squeeze].add([i], -weights[i], "REPLACE")

            # we put the new values in the vertex colors
            # red channel is stretched
            # green channel is squeezed
            # blue channel is not used
            for i in range(len(obj.data.polygons)):
                # k v -> key value
                for k, v in enumerate(obj.data.polygons[i].loop_indices):
                    vertex = obj.data.polygons[i].vertices[k]
                    obj.data.vertex_colors[index_tension].data[v].color.r = \
                        obj.vertex_groups[index_stretch].weight(vertex)
                    obj.data.vertex_colors[index_tension].data[v].color.g = \
                        obj.vertex_groups[index_squeeze].weight(vertex)
                    obj.data.vertex_colors[index_tension].data[v].color.b = 0.0


def tm_update_handler(scene):
    """
    Updates the tension map for all objects in the scene
    This function will be called by Blender every frame
    :param scene: the scene to operate on
    :return: nothing
    """

    global last_processed_frame

    # avoid executing the operations if the frame hasn't really changed
    if last_processed_frame != scene.frame_current:
        last_processed_frame = scene.frame_current
        for obj in scene.objects:
            tm_update(obj, scene)


def tm_update_selected(context):
    """
    Updates the tension map for the selected object
    :param context: the context in which the selected object is
    :return: nothing
    """
    tm_update(context.object, context.scene)


class TmUpdateSelected(bpy.types.Operator):
    """
    Update tension map for selected object
    """

    # this operator is simply a wrapper for the tm_update_selected function
    bl_label = "Update tension map"
    bl_idname = "tm.update_selected"
    bl_options = {"REGISTER"}

    def execute(self, context):
        tm_update_selected(context)
        return {"FINISHED"}

    def invoke(self, context, event):
        return self.execute(context)


class TmPanel(bpy.types.Panel):
    """
    Creates a Panel in the Object properties window
    """

    bl_label = "Tension Map Script"
    bl_idname = "OBJECT_PT_tm"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    def draw_header(self, context):
        if context.object.type == "MESH":
            row = self.layout.row()
            row.prop(context.object.data, "tm_active", text="")

    def draw(self, context):
        if context.object.type == "MESH":
            row = self.layout.row()
            row.active = context.object.data.tm_active
            row.prop(context.object.data, "tm_multiply", text="Multiplier")
            row.operator("tm.update_selected")


def add_props():
    """
    Method responsible for adding properties to the mesh type
    :return: nothing
    """
    bpy.types.Mesh.tm_active = \
        bpy.props.BoolProperty(name="tm_active", description="Activate tension map", default=False)
    bpy.types.Mesh.tm_multiply = \
        bpy.props.FloatProperty(name="tm_multiply", description="Map intensity multiplier", min=-100, max=100,
                                default=1.0)


def remove_props():
    """
    Method responsible for removing properties from the mesh type
    :return: nothing
    """
    del bpy.types.Mesh.tm_active
    del bpy.types.Mesh.tm_multiply


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
    bpy.utils.register_class(TmPanel)
    bpy.utils.register_class(TmUpdateSelected)
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
