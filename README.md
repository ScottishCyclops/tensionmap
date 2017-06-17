# Tension Map Script

This is a blender add-on which give you stretch and squeeze information for any mesh object.

This add-on has been created by Jean-Francois Gallant aka [Pyroevil](https://pyroevil.com/) and his version is available to download at [this link](https://pyroevil.com/tensionmap-download/).

It was released under the GPL2 or later licence.

This repository contains my version of the add-on, which has been made [PEP8](https://www.python.org/dev/peps/pep-0008/) compliant, has been optimized and commented. I also fixed the errors and warning I could find.

I do not know if PyroEvil is planning on continuing development of this add-on, but I am.


## Installation

Go to the [releases page](https://github.com/ScottishCyclops/tensionmap/releases) on github and under *Downloads*, choose *Source code (zip)*.

> If you want the latest in-developpment version, which is not recommanded, you can go on the [master branch](https://github.com/ScottishCyclops/tensionmap/tree/master) on github, then click the button that says *Clone or download*, then *Download ZIP*.

Once downloaded, **Do not extract the ZIP file**.

Open Blender, go into *File*, *User Preferences*, *Add-ons*, and click on *Install from File...* at the bottom of the window.

Navigate to the folder you downloaded the ZIP file into, then double click on the file, or select it and click *Install from File...*

You should see the add-on in the list. If not, search for *tension* in the search box and it should pop up.

Click on the checkbox to enable it.


If you wish the add-on to stay enable by default, click on *Save User Settings* at the bottom of the screen before closing the preferences.

## Usage

If you now select any Object of type *MESH* and go into the *Properties* panel, under the *Data* tab, you should see a new section called *Tension Map Script*.

Enable it then click on the *Update tension map* button.

Two new groups should have been added to your *Vertex Groups*, as well as one *Vertex Colors* entry.


Use the vertex groups to drive things such as modifiers, and vertex colors to drive materials.


You can access the vertex colors though the *Attribute* node, by simply witting **tm_tension** in the *Name* field.

You then want to plug the color output to a *Separate RGB* node, to get stretch values from the Red channel and squeezed values from the Green channel. Note that the Blue channel is not used.


## Bugs and suggestions

Please report any bugs or suggestions in the appropriated tab on the [github page](https://github.com/ScottishCyclops/tensionmap).


## TODO

Support for shape key deformation


## Conclusion

I hope you'll find this add-on useful!

Scott
