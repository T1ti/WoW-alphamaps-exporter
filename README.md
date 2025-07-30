# WoW-alphamaps-exporter
Python script to export Alphamaps from ADTs per texture(meaning one alphamap per texture in the ADT), instead of per layer like Noggit red does.
This is used to export to Unreal Engine. The output image format is 8bit grayscale png.
Only tested for WoW 3.3.5, should support 1.x and 2.x since format is the same, but not newer versions.

Usage : Drop ADT files or a folder on the .py script, it will generate images in an output directory.
You may specify the ADT alpha format(4bit or 8bit) either by providing the map's WDT file, or adding the -bigalpha argument.

Output preview :

<img width="747" height="170" alt="image" src="https://github.com/user-attachments/assets/496185cb-9639-4d80-8f26-1f59fb333c8c" />
