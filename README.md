# Tension Map Script

This is a blender add-on which give you stretch and squeeze information for any mesh object.

This add-on has been created by Jean-Francois Gallant aka [Pyroevil](https://pyroevil.com/) and his version is available to download at [this link](https://pyroevil.com/tensionmap-download/).

It was released under the GPL2 or later licence.

This repository contains my version of the add-on, which has been made [PEP8](https://www.python.org/dev/peps/pep-0008/) compliant (mostly), has been optimized and commented. I also fixed the errors and warning I could find.
Since then, it has also been updated for Blender 2.8 and has seen a few new features.

I do not know if PyroEvil is planning on continuing development of this add-on, but I am.


## Installation

Go to the [releases page](https://github.com/ScottishCyclops/tensionmap/releases) on github and under *Downloads*, choose the latest *tensionmap-x.x.x.zip* for your blender version.

> If you want the latest in-developpment version, which is not recommanded, you can go on the [master branch](https://github.com/ScottishCyclops/tensionmap/tree/master) on github, then click the button that says *Clone or download*, then *Download ZIP*.

Once downloaded, extract the ZIP file to find `tensionmap.py`.

Open Blender, go into *Edit*, *Preferences...*, *Add-ons*, and click on *Install...* at the top of the window.

Navigate to the folder where `tensionmap.py` is, then double click on the file, or select it and click *Install Add-on from File...*

You should see the add-on in the list. If not, search for *tension* in the search box and it should pop up.

Click on the checkbox to enable it.


## Usage

If you now select any Object of type *MESH* and go into the *Properties* panel, under the *Data* tab, you should see a new section called *Tension Map Script*.

Enable it.

Tension Map has two modes of operation that can be enabled or disabled separatly to improve playback performance depending on your needs.

If you check *Enable Vertex Groups*, two new groups should be added to your *Vertex Groups*: `tm_squeeze` and `tm_stretch`.<br />
Once you disable the option, you can safely remove the two groups if not needed anymore.

If you check *Enable Vertex Colors*, one *Vertex Colors* entry will also be added: `tm_tension`.<br />
Again, once you disable the option, you can safely remove the color if not needed anymore.


Use the vertex groups to drive things such as modifiers, and vertex colors to drive materials.

You can access the vertex colors though the *Attribute* node, by simply witting **tm_tension** in the *Name* field.

You then want to plug the color output to a *Separate RGB* node, to get stretch values from the Red channel and squeeze values from the Green channel. Note that the Blue channel is not used (for now).

> Each mode of operation is quite computationaly intensive in realtime. Enabling, one, the other or both modes will make your framerate at least 2.7 times slower.<br />
> As such, you should globally disable Tension Map on your objects while you are working on other things.

As of now, you have the following parameters:
- Multiplier: multiplies the output by a certain factor
- Minimum: sets a minimum squeeze and stretch value for every vertex
- Maximum: sets a maximum squeeze and stretch value for every vertex

> Note that vertex groups can only contain values between 0 and 1

> Also note that theses parameters are linked to the Mesh data, not the Object data. A second object with the same mesh might create unwanted results


## Bugs and suggestions

Please report any bugs or suggestions in the appropriated tab on the [Github page](https://github.com/ScottishCyclops/tensionmap/issues).


## TODO

- Support for shape key deformation
- Manually choosing which modifiers affect the computation
- A global "disable" option to work faster


## Conclusion

I hope you'll find this add-on useful and I am open to suggestions (regarding this addon, or ideas for addons)!

Scott
