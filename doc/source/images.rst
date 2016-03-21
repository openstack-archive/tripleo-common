===========
Disk images
===========

.. toctree::
   :glob:
   :maxdepth: 2

   image/*


YAML file format
----------------
::

    disk_images:
      -
         imagename: overcloud-compute
         builder: dib
         arch: amd64
         type: qcow2
         distro: centos7
         elements:
           - overcloud-compute
           - other-element
         packages:
           - vim
         options:

