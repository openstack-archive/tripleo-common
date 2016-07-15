================
Uploading images
================

Call the image upload manager::

    manager = ImageUploadManager(['path/to/config.yaml'])
    manager.upload()


.. autoclass:: tripleo_common.image.image_uploader.ImageUploadManager
   :members:

Multiple config files
---------------------

Multiple config files can be passed to the ImageUploadManager.
Attributes are set by the first encountered with the 'imagename' attribute
being the primary key.
