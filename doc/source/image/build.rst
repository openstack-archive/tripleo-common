===============
Building images
===============

Call the image build manager::

    manager = ImageBuildManager(['path/to/config.yaml'])
    manager.build()


.. autoclass:: tripleo_common.image.build.ImageBuildManager
   :members:

Multiple config files
---------------------

Multiple config files can be passed to the ImageBuildManager. Certain attributes
will be merged (currently, 'elements', 'options', and 'packages'), while other
attributes will only be set by the first encountered. The 'imagename' attribute
will be the primary key.